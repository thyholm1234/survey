"""Tenants, afdelinger, brugere og adgangskoder."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import ROLE_ORG, ROLE_SYSTEM, ROLE_UNIT, Principal, admin, system_admin
from ..models import (
    AccessCode,
    AnalysisRun,
    Domain,
    OrganizationUnit,
    Question,
    Response,
    ResponseScale,
    Scenario,
    Subscale,
    Survey,
    SurveyVersion,
    Tenant,
    User,
    UserScope,
    utcnow,
)
from ..security import argon2_hash, code_lookup, generate_code, normalize_code

router = APIRouter(prefix="/api/admin", tags=["admin-org"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Name = Field(min_length=1, max_length=200)


# ---------------------------------------------------------------------------
# Tenants (systemadmin)
# ---------------------------------------------------------------------------


class TenantIn(Strict):
    name: str = Name
    minCellSize: int = Field(10, ge=5, le=100)
    retentionMonths: int = Field(24, ge=1, le=120)
    dataController: str | None = Field(None, max_length=500)
    contact: str | None = Field(None, max_length=500)


def _tenant_out(t: Tenant) -> dict:
    return {"id": t.id, "name": t.name, "minCellSize": t.min_cell_size,
            "retentionMonths": t.retention_months, "dataController": t.data_controller,
            "contact": t.contact, "status": t.status}


@router.get("/tenants")
def list_tenants(p: Principal = Depends(admin), db: Session = Depends(get_db)):
    q = select(Tenant).order_by(Tenant.name)
    if not p.system_admin:
        q = q.where(Tenant.id.in_(p.tenants() or {""}))
    return [_tenant_out(t) for t in db.scalars(q)]


@router.post("/tenants", status_code=201)
def create_tenant(body: TenantIn, p: Principal = Depends(system_admin), db: Session = Depends(get_db)):
    t = Tenant(name=body.name, min_cell_size=body.minCellSize, retention_months=body.retentionMonths,
               data_controller=body.dataController, contact=body.contact)
    db.add(t)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Navnet findes allerede.") from None
    audit.record("tenant.create", actor_type="user", actor_id=p.id, tenant_id=t.id, target_type="tenant",
                 target_id=t.id)
    return _tenant_out(t)


@router.put("/tenants/{tenant_id}")
def update_tenant(tenant_id: str, body: TenantIn, p: Principal = Depends(system_admin),
                  db: Session = Depends(get_db)):
    t = db.get(Tenant, tenant_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    t.name, t.min_cell_size, t.retention_months = body.name, body.minCellSize, body.retentionMonths
    t.data_controller, t.contact = body.dataController, body.contact
    audit.record("tenant.update", actor_type="user", actor_id=p.id, tenant_id=t.id, target_type="tenant",
                 target_id=t.id, details={"minCellSize": t.min_cell_size, "retentionMonths": t.retention_months})
    return _tenant_out(t)


class TenantDeleteIn(Strict):
    confirmName: str = Name


@router.post("/tenants/{tenant_id}/delete")
def delete_tenant(tenant_id: str, body: TenantDeleteIn, p: Principal = Depends(system_admin),
                  db: Session = Depends(get_db)):
    """Sletter en tenant og AL tilhørende data permanent. Auditloggen bevares (append-only)."""
    t = db.get(Tenant, tenant_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    if body.confirmName != t.name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Navnet matcher ikke tenantens navn.")
    name = t.name
    sv_ids = select(SurveyVersion.id).where(SurveyVersion.tenant_id == tenant_id).scalar_subquery()
    counts: dict[str, int] = {}

    def run(key: str, stmt) -> None:
        counts[key] = db.execute(stmt.execution_options(synchronize_session=False)).rowcount or 0

    # Brugere der KUN har roller i denne tenant fjernes sammen med den
    tenant_users = set(db.scalars(select(UserScope.user_id).where(UserScope.tenant_id == tenant_id)))
    other_users = set(db.scalars(select(UserScope.user_id).where(
        UserScope.user_id.in_(tenant_users or {""}),
        (UserScope.tenant_id != tenant_id) | UserScope.tenant_id.is_(None))))
    orphan_users = tenant_users - other_users
    if p.id in orphan_users:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Du kan ikke slette din egen konto.")

    # Markér tenanten; DB-triggerne tillader først da sletning af publicerede spørgeskemaversioner
    t.status = "deleting"
    db.flush()
    run("analysisRuns", delete(AnalysisRun).where(AnalysisRun.tenant_id == tenant_id))
    # Svar, præsentationshændelser, sessioner og genoptagelsesnøgler slettes via ON DELETE CASCADE
    run("responses", delete(Response).where(Response.tenant_id == tenant_id))
    run("accessCodes", delete(AccessCode).where(AccessCode.tenant_id == tenant_id))
    run("userScopes", delete(UserScope).where(UserScope.tenant_id == tenant_id))
    if orphan_users:
        run("users", delete(User).where(User.id.in_(orphan_users)))
    run("questions", delete(Question).where(Question.survey_version_id.in_(sv_ids)))
    run("scenarios", delete(Scenario).where(Scenario.survey_version_id.in_(sv_ids)))
    run("domains", delete(Domain).where(Domain.survey_version_id.in_(sv_ids)))
    run("subscales", delete(Subscale).where(Subscale.survey_version_id.in_(sv_ids)))
    run("responseScales", delete(ResponseScale).where(ResponseScale.survey_version_id.in_(sv_ids)))
    run("surveyVersions", delete(SurveyVersion).where(SurveyVersion.tenant_id == tenant_id))
    run("surveys", delete(Survey).where(Survey.tenant_id == tenant_id))
    db.execute(update(OrganizationUnit).where(OrganizationUnit.tenant_id == tenant_id).values(parent_id=None)
               .execution_options(synchronize_session=False))
    run("units", delete(OrganizationUnit).where(OrganizationUnit.tenant_id == tenant_id))
    db.expunge(t)
    db.execute(delete(Tenant).where(Tenant.id == tenant_id))
    audit.record("tenant.delete", actor_type="user", actor_id=p.id, tenant_id=tenant_id, target_type="tenant",
                 target_id=tenant_id, details={"name": name, "deleted": counts})
    return {"ok": True, "deleted": counts}


# ---------------------------------------------------------------------------
# Afdelinger
# ---------------------------------------------------------------------------


class StatusIn(Strict):
    status: Literal["active", "disabled"]


class EmptyIn(Strict):
    pass


class UnitIn(Strict):
    name: str = Name
    unitType: Literal["daycare", "school", "other"]
    parentId: str | None = Field(None, max_length=32)


def _unit_out(u: OrganizationUnit) -> dict:
    return {"id": u.id, "name": u.name, "unitType": u.unit_type, "parentId": u.parent_id, "status": u.status}


@router.get("/tenants/{tenant_id}/units")
def list_units(tenant_id: str, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    allowed = p.allowed_units(db, tenant_id)
    units = db.scalars(select(OrganizationUnit).where(OrganizationUnit.tenant_id == tenant_id)
                       .order_by(OrganizationUnit.name))
    return [_unit_out(u) for u in units if u.id in allowed]


@router.post("/tenants/{tenant_id}/units", status_code=201)
def create_unit(tenant_id: str, body: UnitIn, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    p.require_tenant(tenant_id, org=True)
    if body.parentId:
        parent = db.get(OrganizationUnit, body.parentId)
        if parent is None or parent.tenant_id != tenant_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldig overordnet afdeling.")
    u = OrganizationUnit(tenant_id=tenant_id, name=body.name, unit_type=body.unitType, parent_id=body.parentId)
    db.add(u)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Afdelingsnavnet findes allerede.") from None
    audit.record("unit.create", actor_type="user", actor_id=p.id, tenant_id=tenant_id, target_type="unit",
                 target_id=u.id, details={"unitType": u.unit_type})
    return _unit_out(u)


@router.post("/tenants/{tenant_id}/units/{unit_id}/status")
def set_unit_status(tenant_id: str, unit_id: str, body: StatusIn, p: Principal = Depends(admin),
                    db: Session = Depends(get_db)):
    p.require_tenant(tenant_id, org=True)
    u = db.get(OrganizationUnit, unit_id)
    if u is None or u.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    u.status = body.status
    audit.record("unit.status", actor_type="user", actor_id=p.id, tenant_id=tenant_id, target_type="unit",
                 target_id=u.id, details={"status": u.status})
    return _unit_out(u)


# ---------------------------------------------------------------------------
# Brugere
# ---------------------------------------------------------------------------


class UserIn(Strict):
    username: str = Field(pattern=r"^[a-z0-9._@-]{3,100}$")
    role: Literal["org_admin", "unit_admin", "system_admin"]
    tenantId: str | None = Field(None, max_length=32)
    unitIds: list[str] = Field(default_factory=list, max_length=50)
    canExport: bool = False


@router.get("/tenants/{tenant_id}/users")
def list_users(tenant_id: str, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    p.require_tenant(tenant_id, org=True)
    rows = db.execute(select(User, UserScope).join(UserScope, UserScope.user_id == User.id)
                      .where(UserScope.tenant_id == tenant_id)).all()
    out: dict[str, dict] = {}
    for u, sc in rows:
        e = out.setdefault(u.id, {"id": u.id, "username": u.username, "status": u.status,
                                  "mfaEnrolled": u.totp_enabled, "scopes": []})
        e["scopes"].append({"role": sc.role_code, "unitId": sc.unit_id, "canExport": sc.can_export})
    return list(out.values())


@router.post("/users", status_code=201)
def create_user(body: UserIn, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    if body.role == ROLE_SYSTEM:
        if not p.system_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Kræver systemadministrator.")
    else:
        if not body.tenantId:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tenantId mangler.")
        if body.role == ROLE_ORG and not p.system_admin:
            p.require_tenant(body.tenantId, org=True)
        elif body.role == ROLE_UNIT:
            if not p.system_admin:
                p.require_tenant(body.tenantId, org=True)
            if not body.unitIds:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Vælg mindst én afdeling.")
            for uid in body.unitIds:
                u = db.get(OrganizationUnit, uid)
                if u is None or u.tenant_id != body.tenantId:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldig afdeling.")
        if db.get(Tenant, body.tenantId) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldig tenant.")
    initial = secrets.token_urlsafe(18)
    user = User(username=body.username, password_hash=argon2_hash(initial), must_change_password=True)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Brugernavnet findes allerede.") from None
    if body.role == ROLE_SYSTEM:
        db.add(UserScope(user_id=user.id, role_code=ROLE_SYSTEM))
    elif body.role == ROLE_ORG:
        db.add(UserScope(user_id=user.id, role_code=ROLE_ORG, tenant_id=body.tenantId, can_export=body.canExport))
    else:
        for uid in body.unitIds:
            db.add(UserScope(user_id=user.id, role_code=ROLE_UNIT, tenant_id=body.tenantId, unit_id=uid,
                             can_export=body.canExport))
    audit.record("user.create", actor_type="user", actor_id=p.id, tenant_id=body.tenantId, target_type="user",
                 target_id=user.id, details={"role": body.role, "canExport": body.canExport})
    # Initial adgangskode vises én gang og skal skiftes ved første login (efter MFA-opsætning)
    return {"id": user.id, "username": user.username, "initialPassword": initial}


@router.post("/users/{user_id}/disable")
def disable_user(user_id: str, body: EmptyIn, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    tenants = {sc.tenant_id for sc in u.scopes if sc.tenant_id}
    if not p.system_admin and (not tenants or not tenants <= p.org_tenants):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    if u.id == p.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Du kan ikke deaktivere dig selv.")
    u.status = "disabled"
    audit.record("user.disable", actor_type="user", actor_id=p.id, target_type="user", target_id=u.id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Adgangskoder
# ---------------------------------------------------------------------------


class CodeIn(Strict):
    unitId: str = Field(max_length=32)
    surveyVersionId: str = Field(max_length=32)
    label: str | None = Field(None, max_length=200)
    validFrom: datetime | None = None
    validTo: datetime | None = None
    maxStarts: int | None = Field(None, ge=1, le=100000)
    maxCompletions: int | None = Field(None, ge=1, le=100000)
    groupTags: list[str] = Field(default_factory=list, max_length=10)
    count: int = Field(1, ge=1, le=500)
    oneTime: bool = False


def _code_out(c: AccessCode) -> dict:
    return {"id": c.id, "unitId": c.unit_id, "surveyVersionId": c.survey_version_id, "label": c.label,
            "validFrom": c.valid_from.isoformat() + "Z", "validTo": c.valid_to.isoformat() + "Z",
            "maxStarts": c.max_starts, "maxCompletions": c.max_completions, "starts": c.starts_count,
            "completions": c.completions_count, "status": c.status, "groupTags": c.group_tags,
            "oneTime": c.one_time}


def _naive_utc(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    if d.tzinfo is not None:
        from datetime import timezone

        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d


@router.post("/access-codes", status_code=201)
def create_codes(body: CodeIn, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    unit = db.get(OrganizationUnit, body.unitId)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    p.require_unit(db, unit.tenant_id, unit.id)
    sv = db.get(SurveyVersion, body.surveyVersionId)
    if sv is None or sv.tenant_id != unit.tenant_id or sv.status != "published":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Spørgeskemaversionen er ikke publiceret.")
    for t in body.groupTags:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", t):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldigt gruppe-tag.")
    now = utcnow()
    vf = _naive_utc(body.validFrom) or now
    vt = _naive_utc(body.validTo) or (now + timedelta(days=60))
    if vt <= vf:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Slutdato skal være efter startdato.")
    max_starts = 1 if body.oneTime else body.maxStarts
    max_comp = 1 if body.oneTime else body.maxCompletions
    created = []
    for _ in range(body.count):
        plain = generate_code()
        norm = normalize_code(plain)
        c = AccessCode(
            tenant_id=unit.tenant_id, unit_id=unit.id, survey_version_id=sv.id,
            lookup_hmac=code_lookup(norm), code_hash=argon2_hash(norm), label=body.label,
            group_tags=body.groupTags, valid_from=vf, valid_to=vt, max_starts=max_starts,
            max_completions=max_comp, one_time=body.oneTime, created_by=p.id,
        )
        db.add(c)
        db.flush()
        created.append({**_code_out(c), "code": plain})
    audit.record("access_code.create", actor_type="user", actor_id=p.id, tenant_id=unit.tenant_id,
                 target_type="unit", target_id=unit.id,
                 details={"count": body.count, "oneTime": body.oneTime, "surveyVersionId": sv.id})
    # Klartekst returneres KUN her, én gang. Kun Argon2id-hash gemmes.
    return {"codes": created, "notice": "Koderne vises kun én gang. Gem dem sikkert nu."}


@router.get("/access-codes")
def list_codes(tenantId: str, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    allowed = p.allowed_units(db, tenantId)
    codes = db.scalars(select(AccessCode).where(AccessCode.tenant_id == tenantId)
                       .order_by(AccessCode.created_at.desc()).limit(1000))
    return [_code_out(c) for c in codes if c.unit_id in allowed]


@router.post("/access-codes/{code_id}/disable")
def disable_code(code_id: str, body: EmptyIn, p: Principal = Depends(admin), db: Session = Depends(get_db)):
    c = db.get(AccessCode, code_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    p.require_unit(db, c.tenant_id, c.unit_id)
    c.status = "disabled"
    audit.record("access_code.disable", actor_type="user", actor_id=p.id, tenant_id=c.tenant_id,
                 target_type="access_code", target_id=c.id)
    return _code_out(c)
