"""Scoring (spec §8). Ren, deterministisk og uden DB-afhængighed.

* CANNOT_ASSESS og ubesvaret er missing – aldrig midtpunkt eller 0.
* Reverse scoring: max + min - raw.
* Subskalascore: middel af gyldige items, hvis andelen besvarede >= tærskel (default 0.8).
* Domænescore pr. subskala: middel af gyldige items, hvis andel >= domænetærskel.
* Totalscore beregnes bevidst ikke.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
from scipy import stats

SCORING_VERSION = "1.0.0"
DEFAULT_SUBSCALE_THRESHOLD = 0.8
DEFAULT_DOMAIN_THRESHOLD = 0.66  # 2 af 3 items pr. domæne x perspektiv


@dataclass(frozen=True)
class QuestionMeta:
    question_id: str
    subscale: str
    domain: str
    reverse: bool


def item_score(raw: int | None, missing_code: str | None, lo: int, hi: int, reverse: bool) -> float | None:
    if raw is None or missing_code is not None:
        return None
    if raw < lo or raw > hi:
        raise ValueError(f"svarværdi {raw} uden for skala {lo}-{hi}")
    return float(hi + lo - raw) if reverse else float(raw)


def _mean_if(values: list[float | None], n_items: int, threshold: float) -> float | None:
    valid = [v for v in values if v is not None]
    if n_items == 0 or not valid:
        return None
    if len(valid) / n_items + 1e-12 < threshold:
        return None
    return float(sum(valid) / len(valid))


def respondent_scores(
    answers: Mapping[str, float | None],
    questions: Iterable[QuestionMeta],
    subscale_threshold: float = DEFAULT_SUBSCALE_THRESHOLD,
    domain_threshold: float = DEFAULT_DOMAIN_THRESHOLD,
) -> dict:
    """answers: question_id -> allerede reverse-justeret itemscore eller None."""
    by_sub: dict[str, list[float | None]] = {}
    by_dom: dict[tuple[str, str], list[float | None]] = {}
    for q in questions:
        v = answers.get(q.question_id)
        by_sub.setdefault(q.subscale, []).append(v)
        by_dom.setdefault((q.subscale, q.domain), []).append(v)
    return {
        "subscales": {s: _mean_if(v, len(v), subscale_threshold) for s, v in by_sub.items()},
        "domains": {k: _mean_if(v, len(v), domain_threshold) for k, v in by_dom.items()},
    }


def describe(values: Iterable[float | None], n_total: int | None = None) -> dict:
    """N, gyldige, missing %, middel, SD, median, IQR og 95 % t-CI."""
    vals = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    n_valid = len(vals)
    n_total = n_total if n_total is not None else n_valid
    out: dict = {
        "n": n_total,
        "nValid": n_valid,
        "missingPct": round(100.0 * (n_total - n_valid) / n_total, 1) if n_total else None,
        "mean": None,
        "sd": None,
        "median": None,
        "q1": None,
        "q3": None,
        "iqr": None,
        "ci95": None,
    }
    if n_valid == 0:
        return out
    arr = np.asarray(vals)
    mean = float(arr.mean())
    out["mean"] = mean
    out["median"] = float(np.median(arr))
    q1, q3 = np.percentile(arr, [25, 75])
    out["q1"], out["q3"], out["iqr"] = float(q1), float(q3), float(q3 - q1)
    if n_valid >= 2:
        sd = float(arr.std(ddof=1))
        out["sd"] = sd
        half = float(stats.t.ppf(0.975, n_valid - 1) * sd / math.sqrt(n_valid))
        out["ci95"] = [mean - half, mean + half]
    return out


def winsorize_rt(values: list[float], upper_quantile: float = 0.99) -> list[float]:
    """Øvre winsorisering af svartider (spec §6) – kun i analyse."""
    if not values:
        return values
    cap = float(np.quantile(np.asarray(values), upper_quantile))
    return [min(v, cap) for v in values]
