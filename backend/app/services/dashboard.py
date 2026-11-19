"""Aggregerede dashboardvisninger med celleundertrykkelse (spec §10, §12).

Undertrykkelsesregler (versioneret: suppression/1.0.0):
1. Primær: celler med n < k (tenantens minimumscellestørrelse) vises ikke.
2. Sekundær (afdelingssammenligning): hvis de undertrykte afdelingers samlede
   n < k, undertrykkes yderligere den mindste synlige afdeling, indtil summen
   >= k eller alt er undertrykt. Forhindrer differencing mod totalen.
3. Komplementregel: når valgfrie filtre (baggrund, dato, gruppe) er aktive, og
   0 < N(uden filtre) - N(med filtre) < k, undertrykkes hele visningen, så
   "alle minus filtreret" ikke afslører en lille gruppe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .analysis_data import (
    MISSING_CANNOT,
    MISSING_NOT_REACHED,
    MISSING_SKIPPED,
    Dataset,
    Filters,
    respondent_scores,
)
from .scoring import describe
from .stats import hedges_g

SUPPRESSION_VERSION = "suppression/1.0.0"


def _desc(values: pd.Series, n_total: int, k: int) -> dict:
    d = describe(values.tolist(), n_total)
    if d["nValid"] < k:
        return {"suppressed": True, "n": None}
    d["suppressed"] = False
    return d


def secondary_suppression(sizes: dict[str, int], k: int) -> set[str]:
    suppressed = {u for u, n in sizes.items() if n < k}
    visible = sorted((n, u) for u, n in sizes.items() if u not in suppressed)
    while suppressed and sum(sizes[u] for u in suppressed) < k and visible:
        _, u = visible.pop(0)
        suppressed.add(u)
    return suppressed


def build(ds: Dataset, f: Filters, k: int, sub_thr: float, dom_thr: float) -> dict:
    subs = [p["code"] for p in ds.doc["perspectives"]]
    sub_names = {p["code"]: p["name"] for p in ds.doc["perspectives"]}
    doms = [d["code"] for d in ds.doc["domains"]]
    dom_names = {d["code"]: d["name"] for d in ds.doc["domains"]}
    out: dict = {
        "minCellSize": k,
        "suppressionRules": SUPPRESSION_VERSION,
        "thresholds": {"subscale": sub_thr, "domain": dom_thr},
        "subscales": [{"code": s, "name": sub_names[s]} for s in subs],
        "domains": [{"code": d, "name": dom_names[d]} for d in doms],
        "n": None,
        "suppressed": False,
    }
    n = ds.n
    if n < k:
        out.update(suppressed=True, reason=f"Færre end {k} besvarelser i udvalget.")
        return out
    if f.optional_active() and 0 < ds.base_n - n < k:
        out.update(suppressed=True,
                   reason="Filtreringen ville gøre det muligt at udlede resultater for en lille gruppe.")
        return out
    out["n"] = n
    sub, dom = respondent_scores(ds, sub_thr, dom_thr)

    # 1. Subskalaprofil
    out["profile"] = [
        {"subscale": s, **_desc(sub.loc[sub.subscale == s, "score"], n, k)} for s in subs
    ]
    # 2. Heatmap domæne × subskala
    out["heatmap"] = [
        {"domain": d, "subscale": s,
         **_desc(dom.loc[(dom.subscale == s) & (dom.domain == d), "score"], n, k)}
        for d in doms for s in subs
    ]
    # 3. Sammenligning (alfabetisk, ikke rangliste).
    #    Intet valg / flere institutioner → sammenlign institutioner (inkl. deres afdelinger/klasser).
    #    Præcis én institution valgt → sammenlign dens afdelinger/klasser.
    #    Konkret udvalg (flere enheder) → hver valgt enhed er en gruppe. Grupperne overlapper aldrig: er både
    #    en institution og nogle af dens afdelinger valgt, dækker institutionen kun de øvrige ("øvrige").
    institutions = ds.responses["institution_id"].unique().tolist()
    selected = set(f.unitIds or []) & set(ds.units)
    inst_only = len(selected) == 1 and ds.units[next(iter(selected))]["parentId"] is None
    if selected and not inst_only:
        level = "custom"
        split = {ds.units[u]["parentId"] for u in selected if ds.units[u]["parentId"] in selected}

        def group_of(unit_id: str) -> str:
            if unit_id in selected:
                return unit_id
            return ds.units[unit_id]["institutionId"]

        resp = ds.responses.assign(group_id=ds.responses["unit_id"].map(group_of))
        for df in (sub, dom):
            df["group_id"] = df["unit_id"].map(group_of)
        key = "group_id"
    else:
        level = "institution" if len(institutions) > 1 else "subunit"
        key = "institution_id" if level == "institution" else "unit_id"
        resp = ds.responses
        split = set()
    sizes = resp.groupby(key).size().to_dict()
    hidden = secondary_suppression(sizes, k)

    def label(gid: str) -> tuple[str, str]:
        info = ds.units.get(gid)
        if info is None:  # institution uden for udvalget (kun dens afdelinger er med)
            info = next(v for v in ds.units.values() if v["institutionId"] == gid)
            return info["institutionName"], info["unitType"]
        if level == "custom":
            if info["parentId"] is None:
                return (f"{info['name']} (øvrige)" if gid in split else info["name"]), info["unitType"]
            return f"{info['institutionName']} › {info['name']}", info["unitType"]
        if level == "subunit" and info["parentId"] is None and len(sizes) > 1:
            return f"{info['name']} (uden afdeling/klasse)", info["unitType"]
        return (info["institutionName"] if level == "institution" else info["name"]), info["unitType"]

    units_out = []
    for gid in sorted(sizes, key=lambda g: label(g)[0].casefold()):
        name, utype = label(gid)
        if gid in hidden:
            units_out.append({"unitId": gid, "name": name, "unitType": utype, "suppressed": True})
            continue
        units_out.append({
            "unitId": gid, "name": name, "unitType": utype, "suppressed": False,
            "n": int(sizes[gid]),
            "subscales": [{"subscale": s, **_desc(sub.loc[(sub[key] == gid) & (sub.subscale == s), "score"],
                                                  int(sizes[gid]), k)} for s in subs],
        })
    out["comparisonLevel"] = level
    if level == "subunit" and institutions:
        out["institution"] = {"id": institutions[0],
                              "name": next(v["institutionName"] for v in ds.units.values()
                                           if v["institutionId"] == institutions[0])}
    out["units"] = units_out

    # 4. Skole vs dagtilbud (deskriptivt + Hedges g; inferens via analysekørsel)
    type_sizes = ds.responses.groupby("unit_type").size().to_dict()
    settings = []
    for s in subs:
        row = {"subscale": s}
        for t in ("daycare", "school"):
            vals = sub.loc[(sub.unit_type == t) & (sub.subscale == s), "score"]
            row[t] = _desc(vals, int(type_sizes.get(t, 0)), k)
        a = sub.loc[(sub.unit_type == "school") & (sub.subscale == s), "score"].dropna().to_numpy()
        b = sub.loc[(sub.unit_type == "daycare") & (sub.subscale == s), "score"].dropna().to_numpy()
        row["hedgesG_school_minus_daycare"] = hedges_g(a, b) if len(a) >= k and len(b) >= k else None
        settings.append(row)
    out["setting"] = settings

    # 5. Missing / kan ikke vurdere
    long = ds.long
    def miss(df: pd.DataFrame) -> dict:
        total = len(df)
        if total == 0:
            return {}
        vc = df["missing"].value_counts()
        return {
            "cells": total,
            "validPct": round(100 * df["value"].notna().sum() / total, 1),
            "cannotAssessPct": round(100 * vc.get(MISSING_CANNOT, 0) / total, 1),
            "notAnsweredPct": round(100 * vc.get(MISSING_SKIPPED, 0) / total, 1),
            "notReachedPct": round(100 * vc.get(MISSING_NOT_REACHED, 0) / total, 1),
        }
    out["missing"] = {
        "bySubscale": [{"subscale": s, **miss(long[long.subscale == s])} for s in subs],
        "byDomain": [{"domain": d, **miss(long[long.domain == d])} for d in doms],
        "byUnitType": [{"unitType": t, **miss(long[long.unit_type == t])}
                       for t in sorted(long.unit_type.unique()) if type_sizes.get(t, 0) >= k],
    }

    # 6. Itemanalyse og svarfordeling
    lo, hi = ds.scale["min"], ds.scale["max"]
    items = []
    for qk, g in long.groupby("question_key", sort=False):
        valid = g["value"].dropna()
        dist = {str(v): int((g["raw"] == v).sum()) for v in range(lo, hi + 1)}
        items.append({
            "questionId": qk, "subscale": g["subscale"].iloc[0], "domain": g["domain"].iloc[0],
            "n": int(len(valid)), "mean": float(valid.mean()) if len(valid) else None,
            "sd": float(valid.std(ddof=1)) if len(valid) > 1 else None,
            "distribution": dist if len(valid) >= k else None,
            "cannotAssess": int((g["missing"] == MISSING_CANNOT).sum()),
            "missingPct": round(100 * (1 - len(valid) / len(g)), 1),
            "medianRtMs": float(np.nanmedian(g["rt_ms"].astype(float))) if g["rt_ms"].notna().any() else None,
        })
    out["items"] = items
    return out
