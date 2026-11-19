"""Systemadministration: auditlog, kædeverifikation, datalivscyklus, CSP-rapporter."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, ratelimit
from ..db import get_db
from ..deps import Principal, admin, system_admin
from ..models import AuditEvent
from ..services.retention import run_retention

router = APIRouter(prefix="/api", tags=["system"])
log = logging.getLogger("csp")


@router.get("/admin/audit")
def list_audit(tenantId: str | None = None, limit: int = 200, p: Principal = Depends(admin),
               db: Session = Depends(get_db)):
    """Systemadmin ser alt; organisationsadmin ser egen tenant."""
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(max(1, min(limit, 1000)))
    if not p.system_admin:
        if not tenantId:
            return []
        p.require_tenant(tenantId, org=True)
        q = q.where(AuditEvent.tenant_id == tenantId)
    elif tenantId:
        q = q.where(AuditEvent.tenant_id == tenantId)
    audit.record("audit.view", actor_type="user", actor_id=p.id, tenant_id=tenantId)
    return [{"id": e.id, "at": e.at.isoformat() + "Z", "actorType": e.actor_type, "actorId": e.actor_id,
             "tenantId": e.tenant_id, "action": e.action, "targetType": e.target_type,
             "targetId": e.target_id, "details": e.details} for e in db.scalars(q)]


@router.get("/admin/audit/verify")
def verify_audit(p: Principal = Depends(system_admin)):
    return audit.verify_chain()


@router.post("/admin/system/retention")
def retention_now(body: dict, p: Principal = Depends(system_admin)):
    result = run_retention()
    audit.record("retention.run", actor_type="user", actor_id=p.id, details=result)
    return result


@router.post("/csp-report", include_in_schema=False)
async def csp_report(request: Request):
    # Rate-limit og log kun minimal, ikke-personhenførbar info
    ok, _ = ratelimit.hit(ratelimit.bucket_for(request, "csp"), 50, 3600)
    if ok:
        body = (await request.body())[:2000]
        log.warning("CSP-rapport modtaget (%d bytes)", len(body))
    return Response(status_code=204)
