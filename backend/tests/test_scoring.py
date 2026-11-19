"""Golden tests for scoring (spec §8, §16)."""
import math

import pytest

from app.services.scoring import QuestionMeta, describe, item_score, respondent_scores, winsorize_rt


def test_item_score_and_reverse():
    assert item_score(2, None, 1, 6, False) == 2.0
    assert item_score(2, None, 1, 6, True) == 5.0  # max + min - raw
    assert item_score(6, None, 1, 6, True) == 1.0
    assert item_score(3, None, 0, 4, True) == 1.0


def test_missing_is_never_midpoint_or_zero():
    assert item_score(None, None, 1, 6, False) is None
    assert item_score(4, "CANNOT_ASSESS", 1, 6, False) is None


def test_out_of_range_rejected():
    with pytest.raises(ValueError):
        item_score(7, None, 1, 6, False)


QS = [QuestionMeta(f"q{i}", "self", "OA" if i < 5 else "ER", False) for i in range(10)]


def test_subscale_threshold_80_percent():
    answers = {f"q{i}": 4.0 for i in range(8)}  # 8/10 = 80 %
    r = respondent_scores(answers, QS)
    assert r["subscales"]["self"] == 4.0
    answers = {f"q{i}": 4.0 for i in range(7)}  # 70 %
    r = respondent_scores(answers, QS)
    assert r["subscales"]["self"] is None


def test_subscale_mean_uses_only_valid():
    answers = {f"q{i}": float(v) for i, v in enumerate([1, 2, 3, 4, 5, 6, 1, 2, 3])}
    answers["q9"] = None
    r = respondent_scores(answers, QS)
    assert r["subscales"]["self"] == pytest.approx(27 / 9)


def test_domain_scores_per_subscale_with_threshold():
    answers = {"q0": 2.0, "q1": 4.0, "q2": None, "q3": 6.0, "q4": 4.0,  # OA 4/5
               "q5": 1.0, "q6": None, "q7": None, "q8": None, "q9": None}  # ER 1/5
    r = respondent_scores(answers, QS, subscale_threshold=0.5, domain_threshold=0.75)
    assert r["domains"][("self", "OA")] == 4.0
    assert r["domains"][("self", "ER")] is None


def test_describe_golden():
    d = describe([1, 2, 3, 4, 5, None], n_total=6)
    assert d["n"] == 6 and d["nValid"] == 5
    assert d["missingPct"] == pytest.approx(16.7)
    assert d["mean"] == 3 and d["median"] == 3
    assert d["sd"] == pytest.approx(math.sqrt(2.5))
    assert d["iqr"] == pytest.approx(2.0)
    # t(0.975, 4) = 2.776445
    half = 2.776445105 * math.sqrt(2.5) / math.sqrt(5)
    assert d["ci95"][0] == pytest.approx(3 - half, abs=1e-6)
    assert d["ci95"][1] == pytest.approx(3 + half, abs=1e-6)


def test_describe_empty():
    d = describe([None, None], 2)
    assert d["nValid"] == 0 and d["mean"] is None and d["missingPct"] == 100.0


def test_winsorize():
    vals = list(range(1, 101))
    w = winsorize_rt([float(v) for v in vals], 0.9)
    assert max(w) == pytest.approx(90.1)
