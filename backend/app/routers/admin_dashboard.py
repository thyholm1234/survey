"""Aggregeret dashboard (spec §10)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import Principal, admin
from ..models import Tenant
from ..services import analysis_data, dashboard
from ..services.scoring import DEFAULT_DOMAIN_THRESHOLD, DEFAULT_SUBSCALE_THRESHOLD

router = APIRouter(prefix="/api/admin", tags=["admin-dashboard"])


def parse_filters(
    surveyVersionId: str,
    unitIds: str | None,
    unitType: str | None,
    dateFrom: date | None,
    dateTo: date | None,
    bg: list[str],
    groupTag: str | None,
    includeIncomplete: bool,
) -> analysis_data.Filters:
    background = {}
    for item in bg[:10]:
        if ":" not in item:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldigt baggrundsfilter.")
        k, v = item.split(":", 1)
        background[k[:64]] = v[:64]
    try:
        return analysis_data.Filters(
            surveyVersionId=surveyVersionId,
            unitIds=[u for u in unitIds.split(",") if u][:500] if unitIds else None,
            unitType=unitType or None, dateFrom=dateFrom, dateTo=dateTo, background=background,
            groupTag=groupTag or None, includeIncomplete=includeIncomplete,
        )
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldige filtre.") from None


def tenant_k(db: Session, tenant_id: str) -> int:
    t = db.get(Tenant, tenant_id)
    return max(get_settings().min_cell_size, t.min_cell_size if t else 0)


@router.get("/dashboard")
def get_dashboard(
    tenantId: str,
    surveyVersionId: str,
    unitIds: str | None = None,
    unitType: str | None = None,
    dateFrom: date | None = None,
    dateTo: date | None = None,
    bg: list[str] = Query(default_factory=list),
    groupTag: str | None = None,
    includeIncomplete: bool = False,
    subscaleThreshold: float = Query(DEFAULT_SUBSCALE_THRESHOLD, ge=0.5, le=1.0),
    domainThreshold: float = Query(DEFAULT_DOMAIN_THRESHOLD, ge=0.25, le=1.0),
    p: Principal = Depends(admin),
    db: Session = Depends(get_db, scope="function"),
):
    allowed = p.allowed_units(db, tenantId)
    f = parse_filters(surveyVersionId, unitIds, unitType, dateFrom, dateTo, bg, groupTag, includeIncomplete)
    try:
        ds = analysis_data.load(db, tenantId, allowed, f)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.") from None
    k = tenant_k(db, tenantId)
    result = dashboard.build(ds, f, k, subscaleThreshold, domainThreshold)
    result["protocol"] = analysis_data.protocol(ds, f, {
        "thresholds": {"subscale": subscaleThreshold, "domain": domainThreshold},
        "minCellSize": k, "suppression": dashboard.SUPPRESSION_VERSION,
    })
    if result.get("suppressed"):
        result["protocol"].pop("nRespondents", None)
        result["protocol"].pop("dataSha256", None)
    audit.record("dashboard.view", actor_type="user", actor_id=p.id, tenant_id=tenantId,
                 target_type="survey_version", target_id=surveyVersionId,
                 details={"filters": result["protocol"]["filters"], "suppressed": result.get("suppressed")})
    return result
