"""Udfører analysekørsler (kaldes af worker-processen)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ..models import Tenant
from . import analysis_data, stats
from .scoring import DEFAULT_DOMAIN_THRESHOLD, DEFAULT_SUBSCALE_THRESHOLD

PROTOCOL_VERSION = "1.0.0"
KINDS = ("reliability", "group_comparison", "team_level", "screening")


def _wide(long: pd.DataFrame, subscale: str, domain: str | None = None) -> pd.DataFrame:
    d = long[long.subscale == subscale]
    if domain:
        d = d[d.domain == domain]
    return d.pivot_table(index="response_id", columns="question_key", values="value", aggfunc="first",
                         dropna=False)


def run_reliability(ds: analysis_data.Dataset, params: dict, k: int) -> dict:
    boot = int(params.get("bootstrap", 1000))
    seed = int(params.get("seed", 20240601))
    subs = [p["code"] for p in ds.doc["perspectives"]]
    doms = [d["code"] for d in ds.doc["domains"]]
    out: dict[str, Any] = {"bySubscale": [], "bySubscaleDomain": []}
    for s in subs:
        w = _wide(ds.long, s)
        out["bySubscale"].append({"subscale": s, **stats.reliability_block(w, boot, seed)})
        for d in doms:
            wd = _wide(ds.long, s, d)
            if wd.shape[1] >= 3:
                r = stats.reliability_block(wd, boot, seed)
                out["bySubscaleDomain"].append({"subscale": s, "domain": d, **r})
    out["method"] = {
        "missing": "Parvis-komplet kovarians-/korrelationsmatrix (min. 10 par pr. itempar); "
                   "'kan ikke vurdere' og ubesvaret er missing. nComplete rapporteres til sammenligning.",
        "alphaCi": f"Percentil-bootstrap, {boot} resamples, seed {seed}.",
        "omega": "McDonalds omega total fra én-faktor principal axis på Pearson-korrelationer. "
                 "Polychoriske korrelationer/ordinal CFA er fase 2.",
    }
    return out


def _score_frame(ds: analysis_data.Dataset, thr: float) -> pd.DataFrame:
    sub, _ = analysis_data.respondent_scores(ds, thr, DEFAULT_DOMAIN_THRESHOLD)
    bg_cols = [c for c in ds.responses.columns if c.startswith("bg_")]
    meta = ds.responses.set_index("response_id")[bg_cols]
    return sub.join(meta, on="response_id")


def run_group_comparison(ds: analysis_data.Dataset, params: dict, k: int) -> dict:
    thr = float(params.get("subscaleThreshold", DEFAULT_SUBSCALE_THRESHOLD))
    covars = [c for c in params.get("covariates", []) if isinstance(c, str)][:4]
    df = _score_frame(ds, thr)
    subs = [p["code"] for p in ds.doc["perspectives"]]
    out: dict[str, Any] = {"factor": "unit_type", "levels": ["daycare", "school"], "bySubscale": []}
    for s in subs:
        d = df[(df.subscale == s) & df.unit_type.isin(["daycare", "school"])]
        groups = {t: d.loc[d.unit_type == t, "score"].to_numpy(dtype=float) for t in ("daycare", "school")}
        out["bySubscale"].append({"subscale": s, **stats.compare_groups(groups, max(k, 10))})

    # Primær model: score ~ unit_type * subscale + kovariater + (1|afdeling)
    long = df.dropna(subset=["score"])
    long = long[long.unit_type.isin(["daycare", "school"])].copy()
    sizes = long.groupby("unit_type")["response_id"].nunique()
    if (sizes.reindex(["daycare", "school"]).fillna(0) < max(k, 10)).any():
        out["mixedModel"] = {"suppressed": True, "reason": f"Mindst én gruppe har n < {max(k, 10)}."}
        return out
    terms = ["C(unit_type, Treatment('daycare')) * C(subscale)"]
    used_covars = []
    for c in covars:
        col = f"bg_{c}"
        if col in long.columns and long[col].notna().mean() > 0.8 and long[col].nunique() > 1:
            long[col] = long[col].fillna("missing")
            terms.append(f"C({col})")
            used_covars.append(c)
    formula = "score ~ " + " + ".join(terms)
    out["mixedModel"] = stats.mixed_model(long, formula, "unit_id")
    out["mixedModel"]["covariatesUsed"] = used_covars
    out["mixedModel"]["note"] = (
        "Gentagne målinger (fire subskalaer pr. respondent) modelleres her kun via afdelings-intercept; "
        "en respondent-intercept kræver krydsede/nestede random effects (R lme4) – fase 2."
    )
    per = []
    for s in subs:
        d = long[long.subscale == s]
        f2 = "score ~ C(unit_type, Treatment('daycare'))" + "".join(f" + C(bg_{c})" for c in used_covars)
        m = stats.mixed_model(d, f2, "unit_id")
        per.append({"subscale": s, **m})
    out["mixedModelPerSubscale"] = per
    return out


def run_team_level(ds: analysis_data.Dataset, params: dict, k: int) -> dict:
    thr = float(params.get("subscaleThreshold", DEFAULT_SUBSCALE_THRESHOLD))
    df = _score_frame(ds, thr)
    subs = [p["code"] for p in ds.doc["perspectives"]]
    sizes = ds.responses.groupby("unit_id").size()
    ok_units = set(sizes[sizes >= k].index)
    out: dict[str, Any] = {"bySubscale": [], "excludedUnits": int((sizes < k).sum())}
    pts = ds.scale["max"] - ds.scale["min"] + 1
    for s in subs:
        d = df[(df.subscale == s) & df.unit_id.isin(ok_units)]
        icc = stats.icc_oneway(d["score"], d["unit_id"])
        rwgs = []
        for uid in sorted(ok_units, key=lambda u: ds.units.get(u, {}).get("name", "")):
            w = _wide(ds.long[ds.long.unit_id == uid], s)
            rwgs.append({"unitId": uid, "name": ds.units.get(uid, {}).get("name"), "n": int(sizes[uid]),
                         "rwgJ": stats.rwg_j(w, pts)})
        vals = [r["rwgJ"] for r in rwgs if r["rwgJ"] is not None]
        out["bySubscale"].append({
            "subscale": s, **icc, "rwgJ": rwgs,
            "rwgJMedian": float(np.median(vals)) if vals else None,
            "aggregationAdvice": (
                "Afdelingsgennemsnit kan fortolkes som fælles niveau (median rwg(j) >= .70)."
                if vals and float(np.median(vals)) >= 0.70
                else "Vis afdelingsgennemsnit som 'individuelle svar samlet' (utilstrækkelig enighed)."
            ),
        })
    out["method"] = "ICC(1)/ICC(2) fra envejs-ANOVA (k0-justeret); rwg(j) med uniform nulfordeling."
    return out


def run_screening(ds: analysis_data.Dataset, params: dict, k: int) -> dict:
    res = stats.screening(ds.long)
    res.pop("flaggedIds", None)  # ingen respondent-id'er i resultatet
    res["note"] = "Flag bruges til følsomhedsanalyse. Ingen respondenter ekskluderes automatisk."
    return res


RUNNERS = {
    "reliability": run_reliability,
    "group_comparison": run_group_comparison,
    "team_level": run_team_level,
    "screening": run_screening,
}


def execute(db: Session, tenant_id: str, kind: str, filters: dict, allowed_units: list[str],
            params: dict, global_k: int) -> tuple[dict, str]:
    f = analysis_data.Filters(**filters)
    ds = analysis_data.load(db, tenant_id, set(allowed_units), f)
    t = db.get(Tenant, tenant_id)
    k = max(global_k, t.min_cell_size if t else 0)
    if ds.n < k:
        return {"suppressed": True, "reason": f"Færre end {k} besvarelser i udvalget."}, analysis_data.data_hash(ds)
    if f.optional_active() and 0 < ds.base_n - ds.n < k:
        return {"suppressed": True, "reason": "Filtreringen kunne afsløre en lille gruppe."}, analysis_data.data_hash(ds)
    result = RUNNERS[kind](ds, params, k)
    result["protocol"] = analysis_data.protocol(ds, f, {
        "kind": kind, "params": params, "minCellSize": k, "protocolVersion": PROTOCOL_VERSION,
    })
    return result, analysis_data.data_hash(ds)
