"""Psykometriske og inferentielle analyser (spec §9).

Implementeret i Python (numpy/scipy/statsmodels). Alle funktioner er rene
og testes mod kendte værdier (se tests/test_stats.py). Fortolkningsflag er
heuristikker – ikke facit.
"""
from __future__ import annotations

import itertools
import math
import warnings
from typing import Any

import numpy as np
import pandas as pd
import scipy
import statsmodels
from scipy import stats

ANALYSIS_VERSION = "1.0.0"


def software_versions() -> dict[str, str]:
    import sys

    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pandas": pd.__version__,
        "statsmodels": statsmodels.__version__,
        "analysisModule": ANALYSIS_VERSION,
    }


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


# ---------------------------------------------------------------------------
# Reliabilitet
# ---------------------------------------------------------------------------


MIN_PAIRWISE = 10


def _cov(df: pd.DataFrame) -> np.ndarray | None:
    """Parvis-komplet kovariansmatrix (robust over for spredt missing)."""
    if df.shape[1] < 2:
        return None
    c = df.cov(min_periods=MIN_PAIRWISE).to_numpy(dtype=float)
    if np.isnan(c).any():
        return None
    return c


def alpha_from_cov(c: np.ndarray) -> float | None:
    k = c.shape[0]
    total = c.sum()
    if k < 2 or total <= 0:
        return None
    return float(k / (k - 1) * (1 - np.trace(c) / total))


def cronbach_alpha(df: pd.DataFrame) -> float | None:
    c = _cov(df)
    return alpha_from_cov(c) if c is not None else None


def alpha_bootstrap_ci(df: pd.DataFrame, n_boot: int = 1000, seed: int = 20240601) -> list[float] | None:
    x = df.to_numpy(dtype=float)
    n = x.shape[0]
    if n < 20 or x.shape[1] < 2:
        return None
    rng = np.random.default_rng(seed)
    alphas = []
    cols = list(df.columns)
    for _ in range(n_boot):
        sample = pd.DataFrame(x[rng.integers(0, n, n)], columns=cols)
        a = cronbach_alpha(sample)
        if a is not None:
            alphas.append(a)
    if len(alphas) < n_boot * 0.9:
        return None
    lo, hi = np.percentile(alphas, [2.5, 97.5])
    return [float(lo), float(hi)]


def corrected_item_total(df: pd.DataFrame) -> dict[str, float | None]:
    c = _cov(df)
    out: dict[str, float | None] = {}
    if c is None:
        return {col: None for col in df.columns}
    for i, col in enumerate(df.columns):
        rest = [j for j in range(c.shape[0]) if j != i]
        cov_ir = c[i, rest].sum()
        var_rest = c[np.ix_(rest, rest)].sum()
        out[col] = _f(cov_ir / math.sqrt(c[i, i] * var_rest)) if c[i, i] > 0 and var_rest > 0 else None
    return out


def alpha_if_deleted(df: pd.DataFrame) -> dict[str, float | None]:
    c = _cov(df)
    if c is None or c.shape[0] < 3:
        return {col: None for col in df.columns}
    out = {}
    for i, col in enumerate(df.columns):
        rest = [j for j in range(c.shape[0]) if j != i]
        out[col] = alpha_from_cov(c[np.ix_(rest, rest)])
    return out


def _corr(df: pd.DataFrame) -> np.ndarray | None:
    if df.shape[1] < 2:
        return None
    r = df.corr(min_periods=MIN_PAIRWISE).to_numpy(dtype=float)
    return None if np.isnan(r).any() else r


def mean_inter_item_r(df: pd.DataFrame) -> float | None:
    r = _corr(df)
    if r is None:
        return None
    iu = np.triu_indices_from(r, k=1)
    return _f(r[iu].mean())


def one_factor_loadings(df: pd.DataFrame, max_iter: int = 500, tol: float = 1e-6) -> np.ndarray | None:
    """Principal axis factoring (iterativ), én faktor, på parvise Pearson-korrelationer."""
    r = _corr(df)
    if r is None or r.shape[0] < 3:
        return None
    try:
        h2 = 1 - 1 / np.diag(np.linalg.pinv(r))  # SMC som startkommunaliteter
    except np.linalg.LinAlgError:
        return None
    h2 = np.clip(h2, 0.005, 0.995)
    lam = None
    for _ in range(max_iter):
        rr = r.copy()
        np.fill_diagonal(rr, h2)
        w, v = np.linalg.eigh(rr)
        lam = v[:, -1] * math.sqrt(max(w[-1], 0))
        new_h2 = np.clip(lam**2, 0.005, 0.995)
        if np.max(np.abs(new_h2 - h2)) < tol:
            break
        h2 = new_h2
    if lam is None:
        return None
    if lam.sum() < 0:
        lam = -lam
    return lam


def omega_total(df: pd.DataFrame) -> float | None:
    """McDonalds omega total for en én-faktor-model (standardiserede items)."""
    lam = one_factor_loadings(df)
    if lam is None:
        return None
    s = lam.sum() ** 2
    e = (1 - lam**2).sum()
    return _f(s / (s + e))


def reliability_block(df: pd.DataFrame, bootstrap: int = 1000, seed: int = 20240601) -> dict:
    """Komplet reliabilitetsrapport for et sæt items (kolonner) – parvis-komplet kovarians."""
    df = df.dropna(how="all")
    k = df.shape[1]
    pair_n = df.notna().astype(int).T.dot(df.notna().astype(int)).to_numpy() if k else np.zeros((0, 0))
    res: dict[str, Any] = {
        "nItems": k,
        "nRespondents": int(df.shape[0]),
        "nComplete": int(df.dropna().shape[0]),
        "minPairwiseN": int(pair_n.min()) if pair_n.size else 0,
        "alpha": None, "alphaCi95": None, "omegaTotal": None, "meanInterItemR": None,
        "items": [], "flags": [],
    }
    if k < 3:
        res["flags"].append("Færre end 3 items – alfa beregnes ikke.")
        return res
    if res["minPairwiseN"] < MIN_PAIRWISE:
        res["flags"].append(f"Færre end {MIN_PAIRWISE} parvise observationer – for usikkert til beregning.")
        return res
    res["alpha"] = cronbach_alpha(df)
    res["alphaCi95"] = alpha_bootstrap_ci(df, bootstrap, seed)
    res["omegaTotal"] = omega_total(df)
    res["meanInterItemR"] = mean_inter_item_r(df)
    itc = corrected_item_total(df)
    aid = alpha_if_deleted(df)
    for c in df.columns:
        flags = []
        if itc[c] is not None and itc[c] < 0.20:
            flags.append("item-total < .20")
        if aid[c] is not None and res["alpha"] is not None and aid[c] > res["alpha"] + 0.01:
            flags.append("alfa stiger hvis item fjernes")
        res["items"].append(
            {"item": c, "itemTotalR": itc[c], "alphaIfDeleted": aid[c], "flags": flags,
             "n": int(df[c].notna().sum()), "mean": _f(df[c].mean()), "sd": _f(df[c].std(ddof=1))}
        )
    a = res["alpha"]
    if a is not None and a > 0.95:
        res["flags"].append("Alfa > .95 kan tyde på redundante items (heuristik).")
    mir = res["meanInterItemR"]
    if mir is not None and not (0.15 <= mir <= 0.50):
        res["flags"].append("Gennemsnitlig inter-item-korrelation uden for ca. .15–.50 (heuristik).")
    res["flags"].append("Alfa er ikke et mål for endimensionalitet.")
    return res


# ---------------------------------------------------------------------------
# Gruppeforskelle
# ---------------------------------------------------------------------------


def hedges_g(a: np.ndarray, b: np.ndarray) -> dict:
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return {"g": None, "ci95": None}
    sp = math.sqrt(((n1 - 1) * a.var(ddof=1) + (n2 - 1) * b.var(ddof=1)) / (n1 + n2 - 2))
    if sp == 0:
        return {"g": None, "ci95": None}
    d = (a.mean() - b.mean()) / sp
    j = 1 - 3 / (4 * (n1 + n2) - 9)
    g = j * d
    se = math.sqrt((n1 + n2) / (n1 * n2) + g**2 / (2 * (n1 + n2)))
    return {"g": _f(g), "d": _f(d), "ci95": [_f(g - 1.96 * se), _f(g + 1.96 * se)]}


def welch_anova(groups: list[np.ndarray]) -> dict:
    k = len(groups)
    n = np.array([len(g) for g in groups], dtype=float)
    m = np.array([g.mean() for g in groups])
    v = np.array([g.var(ddof=1) for g in groups])
    if k < 2 or (n < 2).any() or (v == 0).any():
        return {"F": None, "df1": None, "df2": None, "p": None}
    w = n / v
    W = w.sum()
    mw = (w * m).sum() / W
    a = (w * (m - mw) ** 2).sum() / (k - 1)
    tmp = ((1 - w / W) ** 2 / (n - 1)).sum()
    b = 1 + 2 * (k - 2) / (k**2 - 1) * tmp
    F = a / b
    df1 = k - 1
    df2 = (k**2 - 1) / (3 * tmp)
    p = stats.f.sf(F, df1, df2)
    return {"F": _f(F), "df1": float(df1), "df2": _f(df2), "p": _f(p)}


def classic_anova(groups: list[np.ndarray]) -> dict:
    allv = np.concatenate(groups)
    grand = allv.mean()
    k = len(groups)
    N = len(allv)
    ssb = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
    ssw = sum(((g - g.mean()) ** 2).sum() for g in groups)
    sst = ssb + ssw
    dfb, dfw = k - 1, N - k
    if dfw <= 0 or ssw == 0:
        return {"F": None}
    msw = ssw / dfw
    F = (ssb / dfb) / msw
    p = stats.f.sf(F, dfb, dfw)
    return {
        "F": _f(F), "df1": float(dfb), "df2": float(dfw), "p": _f(p),
        "etaSquared": _f(ssb / sst) if sst else None,
        "omegaSquared": _f((ssb - dfb * msw) / (sst + msw)) if sst else None,
    }


def games_howell(groups: dict[str, np.ndarray]) -> list[dict]:
    names = list(groups)
    k = len(names)
    out = []
    for a, b in itertools.combinations(names, 2):
        x, y = groups[a], groups[b]
        n1, n2 = len(x), len(y)
        v1, v2 = x.var(ddof=1) / n1, y.var(ddof=1) / n2
        se = math.sqrt(v1 + v2)
        if se == 0:
            continue
        diff = x.mean() - y.mean()
        df = (v1 + v2) ** 2 / (v1**2 / (n1 - 1) + v2**2 / (n2 - 1))
        q = abs(diff) / se * math.sqrt(2)
        p = stats.studentized_range.sf(q, k, df)
        qcrit = stats.studentized_range.ppf(0.95, k, df)
        half = qcrit / math.sqrt(2) * se
        out.append({
            "a": a, "b": b, "diff": _f(diff), "ci95": [_f(diff - half), _f(diff + half)],
            "df": _f(df), "pAdj": _f(min(p, 1.0)), "hedgesG": hedges_g(x, y),
            "method": "Games-Howell",
        })
    return out


def tukey(groups: dict[str, np.ndarray]) -> list[dict]:
    names = list(groups)
    if len(names) < 2:
        return []
    res = stats.tukey_hsd(*[groups[n] for n in names])
    ci = res.confidence_interval(0.95)
    out = []
    for i, j in itertools.combinations(range(len(names)), 2):
        out.append({
            "a": names[i], "b": names[j],
            "diff": _f(groups[names[i]].mean() - groups[names[j]].mean()),
            "ci95": [_f(ci.low[i, j]), _f(ci.high[i, j])],
            "pAdj": _f(res.pvalue[i, j]),
            "hedgesG": hedges_g(groups[names[i]], groups[names[j]]),
            "method": "Tukey HSD",
        })
    return out


def compare_groups(groups: dict[str, np.ndarray], min_n: int) -> dict:
    """Én-vejs sammenligning med antagelsestjek og effektstørrelser."""
    groups = {k: np.asarray(v, dtype=float) for k, v in groups.items()}
    groups = {k: v[~np.isnan(v)] for k, v in groups.items()}
    summary = {
        k: {"n": int(len(v)), "mean": _f(v.mean()) if len(v) else None,
            "sd": _f(v.std(ddof=1)) if len(v) > 1 else None}
        for k, v in groups.items()
    }
    small = [k for k, v in groups.items() if len(v) < min_n]
    if small or len(groups) < 2:
        return {"groups": {k: {"n": None if k in small else summary[k]["n"]} for k in groups},
                "suppressed": True,
                "reason": f"Mindst én gruppe har n < {min_n}; sammenligning vises ikke."}
    arrs = list(groups.values())
    res: dict[str, Any] = {"groups": summary, "suppressed": False}
    lev = stats.levene(*arrs, center="median")
    res["levene"] = {"W": _f(lev.statistic), "p": _f(lev.pvalue), "center": "median (Brown-Forsythe)"}
    resid = np.concatenate([g - g.mean() for g in arrs])
    if 3 <= len(resid) <= 5000:
        sh = stats.shapiro(resid)
        res["shapiroResiduals"] = {"W": _f(sh.statistic), "p": _f(sh.pvalue)}
    skew = _f(stats.skew(resid))
    res["residualSkew"] = skew
    res["classicAnova"] = classic_anova(arrs)
    res["welchAnova"] = welch_anova(arrs)
    kw = stats.kruskal(*arrs)
    n_all = sum(len(a) for a in arrs)
    res["kruskalWallis"] = {
        "H": _f(kw.statistic), "p": _f(kw.pvalue),
        "epsilonSquared": _f(kw.statistic / ((n_all**2 - 1) / (n_all + 1))),
    }
    hetero = res["levene"]["p"] is not None and res["levene"]["p"] < 0.05
    res["recommended"] = "welchAnova" if hetero else "classicAnova"
    if skew is not None and abs(skew) > 1:
        res["recommendedNote"] = "Stærkt skæve residualer – overvej Kruskal-Wallis eller ordinal model."
    res["posthoc"] = games_howell(groups) if hetero else tukey(groups)
    if len(groups) == 2:
        a, b = arrs
        res["hedgesG"] = hedges_g(a, b)
        names = list(groups)
        res["hedgesGDirection"] = f"{names[0]} minus {names[1]}"
    res["assumptions"] = [
        "Uafhængighed er ikke opfyldt når medarbejdere er grupperet i afdelinger – brug mixed model som primær analyse.",
        "Welch-ANOVA anbefales ved heteroskedasticitet (Levene p < .05).",
    ]
    return res


def mixed_model(df: pd.DataFrame, formula: str, group_col: str) -> dict:
    """Lineær mixed model med random intercept for afdeling (statsmodels MixedLM, REML)."""
    import statsmodels.formula.api as smf

    n_groups = df[group_col].nunique()
    out: dict[str, Any] = {"formula": formula, "groupCol": group_col, "nGroups": int(n_groups),
                           "nObs": int(len(df)), "warnings": []}
    if n_groups < 3:
        out["warnings"].append("Færre end 3 afdelinger – random effects kan ikke estimeres stabilt.")
        return out
    if n_groups < 10:
        out["warnings"].append(
            f"Kun {n_groups} afdelinger: varianskomponent for afdeling er usikker; fortolk forsigtigt."
        )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            model = smf.mixedlm(formula, df, groups=df[group_col])
            fit = model.fit(reml=True, method=["lbfgs", "powell"])
        except Exception as exc:  # noqa: BLE001 - rapporteres til bruger
            out["error"] = f"Modellen kunne ikke estimeres: {type(exc).__name__}"
            return out
    out["warnings"] += sorted({str(w.message)[:200] for w in caught})
    ci = fit.conf_int()
    fe = []
    for name in fit.fe_params.index:
        fe.append({
            "term": name, "estimate": _f(fit.fe_params[name]), "se": _f(fit.bse_fe[name]),
            "z": _f(fit.tvalues[name]), "p": _f(fit.pvalues[name]),
            "ci95": [_f(ci.loc[name, 0]), _f(ci.loc[name, 1])],
        })
    out["fixedEffects"] = fe
    out["groupVariance"] = _f(fit.cov_re.iloc[0, 0])
    out["residualVariance"] = _f(fit.scale)
    out["converged"] = bool(fit.converged)
    out["logLik"] = _f(fit.llf)
    out["method"] = "REML"
    return out


# ---------------------------------------------------------------------------
# Teamniveau
# ---------------------------------------------------------------------------


def icc_oneway(values: pd.Series, groups: pd.Series) -> dict:
    d = pd.DataFrame({"y": values, "g": groups}).dropna()
    if d.empty:
        return {"icc1": None, "icc2": None}
    sizes = d.groupby("g")["y"].size()
    J, N = len(sizes), len(d)
    if J < 2 or N - J < 1:
        return {"icc1": None, "icc2": None, "nGroups": int(J), "n": int(N)}
    grand = d["y"].mean()
    means = d.groupby("g")["y"].mean()
    ssb = float((sizes * (means - grand) ** 2).sum())
    ssw = float(((d["y"] - d["g"].map(means)) ** 2).sum())
    msb, msw = ssb / (J - 1), ssw / (N - J)
    k0 = (N - (sizes**2).sum() / N) / (J - 1)
    icc1 = (msb - msw) / (msb + (k0 - 1) * msw) if (msb + (k0 - 1) * msw) else None
    icc2 = (msb - msw) / msb if msb else None
    return {"icc1": _f(icc1), "icc2": _f(icc2), "k0": _f(k0), "nGroups": int(J), "n": int(N),
            "msb": _f(msb), "msw": _f(msw)}


def rwg_j(items: pd.DataFrame, scale_points: int) -> float | None:
    """rwg(j) (James, Demaree & Wolf 1984) med uniform nulfordeling."""
    d = items.dropna(axis=1, how="all")
    J = d.shape[1]
    if J == 0 or d.shape[0] < 2:
        return None
    s2 = float(d.var(ddof=1).mean())
    sigma_eu = (scale_points**2 - 1) / 12
    ratio = s2 / sigma_eu
    if ratio >= 1:
        return 0.0
    val = J * (1 - ratio) / (J * (1 - ratio) + ratio)
    return _f(val)


# ---------------------------------------------------------------------------
# Datascreening
# ---------------------------------------------------------------------------


def screening(long: pd.DataFrame, fast_fraction: float = 1 / 3, straight_min: int = 10) -> dict:
    """Flag – sletter aldrig. long skal have response_id, subscale, value, rt_ms."""
    out: dict[str, Any] = {"rules": {
        "fastResponder": f"median svartid < {fast_fraction:.3f} × stikprøvens median",
        "straightlining": f"alle besvarede items i en blok har samme værdi (mindst {straight_min} svar)",
        "version": "screening/1.0.0",
    }}
    rt = long.dropna(subset=["rt_ms"])
    per_resp = rt.groupby("response_id")["rt_ms"].median()
    sample_med = float(per_resp.median()) if len(per_resp) else None
    fast = per_resp[per_resp < sample_med * fast_fraction].index.tolist() if sample_med else []
    straight = set()
    ans = long.dropna(subset=["value"])
    for (rid, _sub), g in ans.groupby(["response_id", "subscale"]):
        if len(g) >= straight_min and g["value"].nunique() == 1:
            straight.add(rid)
    out["sampleMedianRtMs"] = sample_med
    out["nRespondents"] = int(long["response_id"].nunique())
    out["fastResponders"] = len(fast)
    out["straightliners"] = len(straight)
    out["flaggedIds"] = {"fast": fast, "straight": sorted(straight)}
    return out
