"""Statistiktests mod kendte værdier og uafhængige implementeringer (scipy/statsmodels)."""
import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps
from statsmodels.stats.oneway import anova_oneway

from app.services import stats
from app.services.dashboard import secondary_suppression


def classic_alpha(x: np.ndarray) -> float:
    k = x.shape[1]
    return k / (k - 1) * (1 - x.var(axis=0, ddof=1).sum() / x.sum(axis=1).var(ddof=1))


def latent_data(n=400, k=6, loading=0.7, seed=1):
    rng = np.random.default_rng(seed)
    f = rng.normal(size=n)
    e = rng.normal(size=(n, k)) * math.sqrt(1 - loading**2)
    return pd.DataFrame(loading * f[:, None] + e, columns=[f"i{j}" for j in range(k)])


def test_alpha_equals_classic_on_complete_data():
    df = latent_data()
    assert stats.cronbach_alpha(df) == pytest.approx(classic_alpha(df.to_numpy()), abs=1e-12)


def test_alpha_textbook_example():
    # Perfekt parallelle items -> alfa = 1
    x = np.tile(np.arange(1, 11)[:, None], (1, 4)).astype(float)
    assert stats.cronbach_alpha(pd.DataFrame(x)) == pytest.approx(1.0)


def test_alpha_if_deleted_and_item_total():
    df = latent_data(k=5)
    aid = stats.alpha_if_deleted(df)
    for c in df.columns:
        assert aid[c] == pytest.approx(classic_alpha(df.drop(columns=[c]).to_numpy()), abs=1e-12)
    itc = stats.corrected_item_total(df)
    for c in df.columns:
        rest = df.drop(columns=[c]).sum(axis=1)
        assert itc[c] == pytest.approx(np.corrcoef(df[c], rest)[0, 1], abs=1e-12)


def test_omega_matches_theory_for_congeneric_items():
    lam, k = 0.7, 6
    df = latent_data(n=20000, k=k, loading=lam, seed=3)
    expected = (k * lam) ** 2 / ((k * lam) ** 2 + k * (1 - lam**2))
    assert stats.omega_total(df) == pytest.approx(expected, abs=0.01)


def test_bootstrap_ci_contains_point_estimate():
    df = latent_data(n=200)
    ci = stats.alpha_bootstrap_ci(df, 300, 7)
    a = stats.cronbach_alpha(df)
    assert ci[0] < a < ci[1]


def test_reliability_flags_low_item_total():
    df = latent_data(n=300, k=5)
    df["noise"] = np.random.default_rng(9).normal(size=300)
    rep = stats.reliability_block(df, 200, 1)
    noise = next(i for i in rep["items"] if i["item"] == "noise")
    assert "item-total < .20" in noise["flags"]


def test_welch_anova_two_groups_equals_welch_t():
    rng = np.random.default_rng(2)
    a, b = rng.normal(0, 1, 40), rng.normal(0.5, 2, 25)
    w = stats.welch_anova([a, b])
    t = sps.ttest_ind(a, b, equal_var=False)
    assert w["F"] == pytest.approx(t.statistic**2, rel=1e-10)
    assert w["p"] == pytest.approx(t.pvalue, rel=1e-8)


def test_welch_anova_three_groups_matches_statsmodels():
    rng = np.random.default_rng(5)
    g = [rng.normal(0, 1, 30), rng.normal(0.3, 1.5, 20), rng.normal(0.8, 0.7, 25)]
    w = stats.welch_anova(g)
    ref = anova_oneway(g, use_var="unequal", welch_correction=True)
    assert w["F"] == pytest.approx(ref.statistic, rel=1e-8)
    assert w["p"] == pytest.approx(ref.pvalue, rel=1e-6)


def test_classic_anova_matches_scipy_and_effect_sizes():
    rng = np.random.default_rng(6)
    g = [rng.normal(m, 1, 30) for m in (0, 0.5, 1)]
    r = stats.classic_anova(g)
    ref = sps.f_oneway(*g)
    assert r["F"] == pytest.approx(ref.statistic) and r["p"] == pytest.approx(ref.pvalue)
    assert 0 < r["omegaSquared"] < r["etaSquared"] < 1


def test_games_howell_two_groups_equals_welch_t():
    rng = np.random.default_rng(8)
    a, b = rng.normal(0, 1, 30), rng.normal(0.6, 2, 30)
    gh = stats.games_howell({"a": a, "b": b})[0]
    t = sps.ttest_ind(a, b, equal_var=False)
    assert gh["pAdj"] == pytest.approx(t.pvalue, rel=1e-4)


def test_hedges_g_known_value():
    a = np.array([2.0, 4, 6, 8])
    b = np.array([1.0, 3, 5, 7])
    r = stats.hedges_g(a, b)
    sp = math.sqrt((3 * a.var(ddof=1) + 3 * b.var(ddof=1)) / 6)
    d = 1 / sp
    assert r["d"] == pytest.approx(d)
    assert r["g"] == pytest.approx(d * (1 - 3 / (4 * 8 - 9)))


def test_icc_known_values():
    y = pd.Series([1, 2, 3, 4, 5, 6], dtype=float)
    g = pd.Series(["a", "a", "a", "b", "b", "b"])
    r = stats.icc_oneway(y, g)
    assert r["icc1"] == pytest.approx(12.5 / 15.5)
    assert r["icc2"] == pytest.approx(12.5 / 13.5)


def test_rwg_bounds():
    agree = pd.DataFrame({"a": [4, 4, 4], "b": [5, 5, 5]}, dtype=float)
    assert stats.rwg_j(agree, 6) == pytest.approx(1.0)
    spread = pd.DataFrame({"a": [1, 6, 1, 6], "b": [6, 1, 6, 1]}, dtype=float)
    assert stats.rwg_j(spread, 6) == 0.0


def test_compare_groups_suppresses_small_groups():
    r = stats.compare_groups({"daycare": np.ones(5), "school": np.ones(30)}, 10)
    assert r["suppressed"] is True
    assert r["groups"]["daycare"]["n"] is None


def test_compare_groups_recommends_welch_on_heteroskedasticity():
    rng = np.random.default_rng(11)
    r = stats.compare_groups({"daycare": rng.normal(0, 0.3, 80), "school": rng.normal(0, 3, 80)}, 10)
    assert r["recommended"] == "welchAnova"
    assert r["posthoc"][0]["method"] == "Games-Howell"


def test_mixed_model_recovers_effect():
    rng = np.random.default_rng(12)
    rows = []
    for u in range(12):
        typ = "school" if u % 2 else "daycare"
        ue = rng.normal(0, 0.3)
        for _ in range(25):
            rows.append({"unit_id": f"u{u}", "unit_type": typ,
                         "score": 4 + (-0.5 if typ == "school" else 0) + ue + rng.normal(0, 0.8)})
    df = pd.DataFrame(rows)
    m = stats.mixed_model(df, "score ~ C(unit_type, Treatment('daycare'))", "unit_id")
    eff = next(f for f in m["fixedEffects"] if "school" in f["term"])
    assert eff["ci95"][0] < -0.5 < eff["ci95"][1]
    assert m["converged"]


def test_screening_flags_without_deleting():
    rows = []
    for r in range(20):
        for q in range(12):
            rows.append({"response_id": f"r{r}", "subscale": "self", "value": 3.0 if r == 0 else float(q % 6 + 1),
                         "rt_ms": 500.0 if r == 1 else 6000.0})
    res = stats.screening(pd.DataFrame(rows))
    assert res["fastResponders"] == 1 and res["straightliners"] == 1
    assert res["nRespondents"] == 20


def test_secondary_suppression_prevents_differencing():
    # én lille afdeling skjult -> den mindste synlige skjules også
    hidden = secondary_suppression({"a": 4, "b": 25, "c": 12, "d": 30}, 10)
    assert hidden == {"a", "c"}
    # to små afdelinger, der tilsammen >= k, er nok
    assert secondary_suppression({"a": 5, "b": 6, "c": 30}, 10) == {"a", "b"}
    assert secondary_suppression({"a": 20, "b": 30}, 10) == set()
