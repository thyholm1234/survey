"""Opbygning af analysedatasæt (tidy long) fra qa_data.

Bruges af dashboard, worker og eksport, så alle bygger på samme kode og
samme filtre (reproducerbarhed, spec §15.10).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Answer,
    Domain,
    OrganizationUnit,
    Question,
    Response,
    ResponseScale,
    Scenario,
    Subscale,
    SurveyVersion,
)

MISSING_CANNOT = "CANNOT_ASSESS"
MISSING_SKIPPED = "NOT_ANSWERED"  # vist, men ikke besvaret
MISSING_NOT_REACHED = "NOT_REACHED"  # aldrig vist


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surveyVersionId: str = Field(max_length=32)
    unitIds: list[str] | None = Field(None, max_length=500)
    unitType: str | None = Field(None, pattern=r"^(daycare|school|other)$")
    dateFrom: date | None = None
    dateTo: date | None = None
    background: dict[str, str] = Field(default_factory=dict, max_length=10)
    groupTag: str | None = Field(None, pattern=r"^[A-Za-z0-9_.-]{1,40}$")
    includeIncomplete: bool = False

    def optional_active(self) -> bool:
        return bool(self.background or self.dateFrom or self.dateTo or self.groupTag or self.includeIncomplete)


@dataclass
class Dataset:
    long: pd.DataFrame
    responses: pd.DataFrame
    questions: pd.DataFrame
    units: dict[str, dict]
    scale: dict
    doc: dict
    base_n: int  # N uden valgfrie filtre (til komplementregel)
    meta: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return int(len(self.responses))


def question_frame(db: Session, sv_id: str) -> pd.DataFrame:
    rows = db.execute(
        select(Question.id, Question.question_key, Question.reverse_scored, Question.position,
               Subscale.code, Subscale.position, Domain.code, Domain.position, Scenario.scenario_key)
        .join(Subscale, Subscale.id == Question.subscale_id)
        .join(Scenario, Scenario.id == Question.scenario_id)
        .join(Domain, Domain.id == Scenario.domain_id)
        .where(Question.survey_version_id == sv_id)
        .order_by(Question.position)
    ).all()
    return pd.DataFrame(rows, columns=["qid", "question_key", "reverse", "qpos", "subscale", "subpos",
                                       "domain", "dompos", "scenario_key"])


def load(db: Session, tenant_id: str, allowed_unit_ids: set[str], f: Filters) -> Dataset:
    sv = db.get(SurveyVersion, f.surveyVersionId)
    if sv is None or sv.tenant_id != tenant_id:
        raise LookupError("survey version")
    doc = json.loads(sv.source_json)
    scale_row = db.scalar(select(ResponseScale).where(ResponseScale.survey_version_id == sv.id))
    scale = {"min": scale_row.min_value, "max": scale_row.max_value}

    all_units = list(db.scalars(select(OrganizationUnit).where(OrganizationUnit.tenant_id == tenant_id)))
    unit_ids = set(allowed_unit_ids)
    if f.unitIds:
        # Valg af en institution omfatter dens afdelinger/klasser
        wanted = set(f.unitIds) | {u.id for u in all_units if u.parent_id in f.unitIds}
        unit_ids &= wanted
    names = {u.id: u.name for u in all_units}
    units = {
        u.id: {"name": u.name, "unitType": u.unit_type, "parentId": u.parent_id,
               "institutionId": u.parent_id or u.id, "institutionName": names.get(u.parent_id or u.id, u.name)}
        for u in all_units if u.id in unit_ids
    }
    base_q = select(Response).where(
        Response.tenant_id == tenant_id,
        Response.survey_version_id == sv.id,
        Response.unit_id.in_(list(units) or [""]),
    )
    if f.unitType:
        base_q = base_q.where(Response.unit_type == f.unitType)
    base_n = len(db.scalars(base_q.where(Response.status == "completed")).all())

    q = base_q
    if not f.includeIncomplete:
        q = q.where(Response.status == "completed")
    if f.dateFrom:
        q = q.where(Response.started_at >= datetime.combine(f.dateFrom, time.min))
    if f.dateTo:
        q = q.where(Response.started_at <= datetime.combine(f.dateTo, time.max))
    resps = []
    for r in db.scalars(q):
        bg = r.background or {}
        if any(bg.get(k) != v for k, v in f.background.items()):
            continue
        if f.groupTag and f.groupTag not in (r.group_tags or []):
            continue
        resps.append({
            "response_id": r.id, "unit_id": r.unit_id, "institution_id": units[r.unit_id]["institutionId"],
            "unit_type": r.unit_type, "status": r.status, "started_at": r.started_at, "completed_at": r.completed_at,
            "seed": r.seed, "block_order": "|".join(r.block_order), "is_synthetic": r.is_synthetic,
            "browser_class": r.browser_class, "screen_class": r.screen_class,
            **{f"bg_{k}": v for k, v in bg.items()},
        })
    responses = pd.DataFrame(resps)
    qf = question_frame(db, sv.id)
    if responses.empty:
        empty = pd.DataFrame(columns=["response_id", "question_key", "subscale", "domain", "value"])
        return Dataset(empty, responses, qf, units, scale, doc, base_n)

    ids = responses["response_id"].tolist()
    ans_rows = []
    for chunk in range(0, len(ids), 500):
        ans_rows += db.execute(
            select(Answer.response_id, Answer.question_id, Answer.value, Answer.missing_code,
                   Answer.global_position, Answer.block_index, Answer.block_position,
                   Answer.first_shown_at, Answer.answered_at, Answer.rt_ms, Answer.change_count,
                   Answer.changed_after_back)
            .where(Answer.response_id.in_(ids[chunk:chunk + 500]))
        ).all()
    ans = pd.DataFrame(ans_rows, columns=["response_id", "qid", "raw", "missing_code", "global_position",
                                          "block_index", "block_position", "first_shown_at",
                                          "answered_at", "rt_ms", "change_count", "changed_after_back"])
    grid = responses[["response_id", "unit_id", "institution_id", "unit_type"]].merge(qf, how="cross")
    long = grid.merge(ans, on=["response_id", "qid"], how="left")
    shown = long["first_shown_at"].notna()
    long["missing"] = None
    long.loc[~shown, "missing"] = MISSING_NOT_REACHED
    long.loc[shown & long["raw"].isna() & long["missing_code"].isna(), "missing"] = MISSING_SKIPPED
    long.loc[long["missing_code"] == MISSING_CANNOT, "missing"] = MISSING_CANNOT
    lo, hi = scale["min"], scale["max"]
    long["value"] = long["raw"].astype("float")
    rev = long["reverse"].astype(bool) & long["value"].notna()
    long.loc[rev, "value"] = hi + lo - long.loc[rev, "value"]
    long.loc[long["missing"].notna(), "value"] = float("nan")
    long = long.sort_values(["response_id", "qpos"]).reset_index(drop=True)
    return Dataset(long, responses, qf, units, scale, doc, base_n)


def data_hash(ds: Dataset) -> str:
    cols = ["response_id", "question_key", "raw", "missing"]
    if ds.long.empty:
        return hashlib.sha256(b"").hexdigest()
    csv = ds.long[cols].to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(csv.encode()).hexdigest()


def respondent_scores(ds: Dataset, sub_thr: float, dom_thr: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returnerer (subskalascorer, domæne×subskala-scorer) pr. respondent."""
    if ds.long.empty:
        return pd.DataFrame(), pd.DataFrame()
    g = ds.long.groupby(["response_id", "subscale"])
    sub = g["value"].agg(["mean", "count", "size"]).reset_index()
    sub["score"] = sub["mean"].where(sub["count"] / sub["size"] + 1e-12 >= sub_thr)
    gd = ds.long.groupby(["response_id", "subscale", "domain"])
    dom = gd["value"].agg(["mean", "count", "size"]).reset_index()
    dom["score"] = dom["mean"].where(dom["count"] / dom["size"] + 1e-12 >= dom_thr)
    meta = ds.responses.set_index("response_id")
    for df in (sub, dom):
        df["unit_id"] = df["response_id"].map(meta["unit_id"])
        df["institution_id"] = df["response_id"].map(meta["institution_id"])
        df["unit_type"] = df["response_id"].map(meta["unit_type"])
    return sub, dom


def protocol(ds: Dataset, f: Filters, extra: dict[str, Any]) -> dict:
    from ..config import get_settings
    from .scoring import SCORING_VERSION
    from .stats import software_versions

    return {
        "surveyVersionId": f.surveyVersionId,
        "surveyId": ds.doc.get("surveyId"),
        "filters": json.loads(f.model_dump_json()),
        "nRespondents": ds.n,
        "dataSha256": data_hash(ds),
        "scoringVersion": SCORING_VERSION,
        "appVersion": get_settings().app_version,
        "software": software_versions(),
        "missingCodes": {
            MISSING_CANNOT: "Respondenten valgte 'kan ikke vurdere'",
            MISSING_SKIPPED: "Vist men ikke besvaret",
            MISSING_NOT_REACHED: "Ikke vist (besvarelsen stoppede før)",
        },
        **extra,
    }
