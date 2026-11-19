"""Import, preview og publicering af spørgeskemaer."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import Principal, admin
from ..models import Survey, SurveyVersion
from ..services import survey_import

router = APIRouter(prefix="/api/admin/surveys", tags=["admin-surveys"])


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenantId: str = Field(max_length=32)
    document: dict[str, Any]
    dryRun: bool = True


class EmptyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/import")
def import_survey(body: ImportIn, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    p.require_tenant(body.tenantId, org=True)
    errors = survey_import.validate(body.document)
    prev = survey_import.preview(body.document) if not errors else None
    if errors or body.dryRun:
        return {"valid": not errors, "errors": errors, "preview": prev, "stored": False}
    sv = survey_import.store_draft(db, body.tenantId, p.id, body.document)
    audit.record("survey.import", actor_type="user", actor_id=p.id, tenant_id=body.tenantId,
                 target_type="survey_version", target_id=sv.id,
                 details={"sha256": sv.source_sha256, "versionNo": sv.version_no})
    return {"valid": True, "errors": [], "preview": prev, "stored": True,
            "surveyVersionId": sv.id, "versionNo": sv.version_no}


def _version(db: Session, p: Principal, version_id: str, org: bool = False) -> SurveyVersion:
    sv = db.get(SurveyVersion, version_id)
    if sv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    p.require_tenant(sv.tenant_id, org=org)
    return sv


@router.post("/{version_id}/publish")
def publish(version_id: str, body: EmptyIn, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    sv = _version(db, p, version_id, org=True)
    try:
        survey_import.publish(db, sv, p.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    audit.record("survey.publish", actor_type="user", actor_id=p.id, tenant_id=sv.tenant_id,
                 target_type="survey_version", target_id=sv.id, details={"sha256": sv.source_sha256})
    return {"surveyVersionId": sv.id, "status": sv.status}


@router.post("/{version_id}/retire")
def retire(version_id: str, body: EmptyIn, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    sv = _version(db, p, version_id, org=True)
    if sv.status != "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Kun publicerede versioner kan udfases.")
    sv.status = "retired"
    audit.record("survey.retire", actor_type="user", actor_id=p.id, tenant_id=sv.tenant_id,
                 target_type="survey_version", target_id=sv.id)
    return {"surveyVersionId": sv.id, "status": sv.status}


@router.get("")
def list_surveys(tenantId: str, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    p.require_tenant(tenantId)
    out = []
    for s in db.scalars(select(Survey).where(Survey.tenant_id == tenantId).order_by(Survey.title)):
        versions = db.scalars(select(SurveyVersion).where(SurveyVersion.survey_id == s.id)
                              .order_by(SurveyVersion.version_no.desc()))
        out.append({"id": s.id, "surveyId": s.survey_key, "title": s.title, "versions": [
            {"id": v.id, "versionNo": v.version_no, "status": v.status,
             "importedAt": v.imported_at.isoformat() + "Z",
             "publishedAt": v.published_at.isoformat() + "Z" if v.published_at else None,
             "sha256": v.source_sha256}
            for v in versions
        ]})
    return out


@router.get("/versions/{version_id}")
def version_detail(version_id: str, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    sv = _version(db, p, version_id)
    doc = json.loads(sv.source_json)
    return {
        "id": sv.id, "status": sv.status, "versionNo": sv.version_no, "title": doc["title"],
        "perspectives": doc["perspectives"], "domains": doc["domains"],
        "backgroundVariables": doc.get("backgroundVariables", []),
        "preview": survey_import.preview(doc),
    }
