"""Analysekørsler (spec §9, §14)."""
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import Principal, admin
from ..models import AnalysisRun, SurveyVersion
from ..services.analysis_data import Filters
from ..services.analysis_runner import PROTOCOL_VERSION

router = APIRouter(prefix="/api/admin/analyses", tags=["admin-analyses"])


class AnalysisIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenantId: str = Field(max_length=32)
    kind: Literal["reliability", "group_comparison", "team_level", "screening"]
    filters: Filters
    params: dict[str, Any] = Field(default_factory=dict)


ALLOWED_PARAMS = {"bootstrap", "seed", "subscaleThreshold", "covariates"}


def _clean_params(params: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in params.items():
        if k not in ALLOWED_PARAMS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Ukendt parameter: {k[:40]}")
    if "bootstrap" in params:
        out["bootstrap"] = max(200, min(int(params["bootstrap"]), 5000))
    if "seed" in params:
        out["seed"] = int(params["seed"]) % (2**31)
    if "subscaleThreshold" in params:
        out["subscaleThreshold"] = max(0.5, min(float(params["subscaleThreshold"]), 1.0))
    if "covariates" in params:
        cov = params["covariates"]
        if not isinstance(cov, list) or not all(isinstance(c, str) and len(c) <= 64 for c in cov):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldige kovariater.")
        out["covariates"] = cov[:4]
    return out


def _out(r: AnalysisRun, full: bool = False) -> dict:
    d = {"id": r.id, "kind": r.kind, "status": r.status, "requestedAt": r.requested_at.isoformat() + "Z",
         "finishedAt": r.finished_at.isoformat() + "Z" if r.finished_at else None,
         "surveyVersionId": r.survey_version_id, "filters": r.filters, "params": r.params,
         "error": r.error, "dataSha256": r.data_sha256, "protocolVersion": r.protocol_version}
    if full:
        d["result"] = json.loads(r.result) if r.result else None
        d["software"] = r.software
    return d


@router.post("", status_code=202)
def create(body: AnalysisIn, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    allowed = p.allowed_units(db, body.tenantId)
    sv = db.get(SurveyVersion, body.filters.surveyVersionId)
    if sv is None or sv.tenant_id != body.tenantId:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    params = _clean_params(body.params)
    run = AnalysisRun(
        tenant_id=body.tenantId, survey_version_id=sv.id, kind=body.kind, params=params,
        filters=json.loads(body.filters.model_dump_json()), allowed_unit_ids=sorted(allowed),
        requested_by=p.id, protocol_version=PROTOCOL_VERSION,
    )
    db.add(run)
    db.flush()
    audit.record("analysis.request", actor_type="user", actor_id=p.id, tenant_id=body.tenantId,
                 target_type="analysis_run", target_id=run.id, details={"kind": body.kind})
    return _out(run)


def _get(db: Session, p: Principal, run_id: str) -> AnalysisRun:
    r = db.get(AnalysisRun, run_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    allowed = p.allowed_units(db, r.tenant_id)
    # Man må kun se kørsler, hvis datagrundlag ligger inden for egne afdelinger
    if not set(r.allowed_unit_ids or []) <= allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    return r


@router.get("/{run_id}")
def get_run(run_id: str, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    r = _get(db, p, run_id)
    audit.record("analysis.view", actor_type="user", actor_id=p.id, tenant_id=r.tenant_id,
                 target_type="analysis_run", target_id=r.id)
    return _out(r, full=True)


@router.get("")
def list_runs(tenantId: str, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    allowed = p.allowed_units(db, tenantId)
    runs = db.scalars(select(AnalysisRun).where(AnalysisRun.tenant_id == tenantId)
                      .order_by(AnalysisRun.requested_at.desc()).limit(100))
    return [_out(r) for r in runs if set(r.allowed_unit_ids or []) <= allowed]
