"""Syntetiske demosvar: generér, optæl og slet (kun organisationsadmin i tenanten)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import Principal, admin
from ..models import OrganizationUnit, Response, SurveyVersion
from ..services import synthetic

router = APIRouter(prefix="/api/admin/demo-responses", tags=["admin-demo"])

MAX_DEMO = 3000


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoIn(Strict):
    tenantId: str = Field(max_length=32)
    surveyVersionId: str = Field(max_length=32)
    unitIds: list[str] = Field(default_factory=list, max_length=500)  # tom = alle »blade«
    perUnit: int = Field(15, ge=1, le=200)


class DemoDeleteIn(Strict):
    tenantId: str = Field(max_length=32)
    surveyVersionId: str | None = Field(None, max_length=32)


@router.get("")
def count_demo(tenantId: str, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    p.require_tenant(tenantId, org=True)
    rows = db.execute(select(Response.survey_version_id, func.count()).where(
        Response.tenant_id == tenantId, Response.is_synthetic.is_(True)).group_by(Response.survey_version_id)).all()
    return {"total": sum(n for _, n in rows), "bySurveyVersion": {sv: n for sv, n in rows}}


@router.post("", status_code=201)
def create_demo(body: DemoIn, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    p.require_tenant(body.tenantId, org=True)
    sv = db.get(SurveyVersion, body.surveyVersionId)
    if sv is None or sv.tenant_id != body.tenantId or sv.status != "published":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Spørgeskemaversionen er ikke publiceret.")
    all_units = list(db.scalars(select(OrganizationUnit).where(OrganizationUnit.tenant_id == body.tenantId,
                                                               OrganizationUnit.status == "active")))
    if body.unitIds:
        by_id = {u.id: u for u in all_units}
        if not set(body.unitIds) <= set(by_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldig afdeling.")
        chosen = [by_id[u] for u in dict.fromkeys(body.unitIds)]
    else:
        # Alle afdelinger/klasser + institutioner uden afdelinger
        parents = {u.parent_id for u in all_units if u.parent_id}
        chosen = [u for u in all_units if u.parent_id or u.id not in parents]
    if not chosen:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Opret først institutioner og afdelinger.")
    total = len(chosen) * body.perUnit
    if total > MAX_DEMO:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Højst {MAX_DEMO} demosvar ad gangen (du bad om {total}).")
    n = synthetic.generate(db, sv, [(u, body.perUnit) for u in chosen])
    audit.record("demo.generate", actor_type="user", actor_id=p.id, tenant_id=body.tenantId,
                 target_type="survey_version", target_id=sv.id,
                 details={"synthetic": True, "responses": n, "units": len(chosen), "perUnit": body.perUnit})
    return {"created": n, "units": len(chosen)}


@router.post("/delete")
def delete_demo(body: DemoDeleteIn, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    """Sletter syntetiske besvarelser (svar og hændelser følger med via ON DELETE CASCADE). Rigtige svar røres ikke."""
    p.require_tenant(body.tenantId, org=True)
    q = delete(Response).where(Response.tenant_id == body.tenantId, Response.is_synthetic.is_(True))
    if body.surveyVersionId:
        q = q.where(Response.survey_version_id == body.surveyVersionId)
    n = db.execute(q.execution_options(synchronize_session=False)).rowcount or 0
    audit.record("demo.delete", actor_type="user", actor_id=p.id, tenant_id=body.tenantId,
                 target_type="tenant", target_id=body.tenantId,
                 details={"synthetic": True, "deleted": n, "surveyVersionId": body.surveyVersionId})
    return {"deleted": n}
