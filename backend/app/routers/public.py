"""Offentlige, ikke-personlige oplysninger til de juridiske sider (privatliv, cookies, databehandling)."""
from fastapi import APIRouter

from ..config import get_settings
from ..deps import ADMIN_COOKIE, RESP_COOKIE

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/legal-info")
def legal_info():
    s = get_settings()
    return {
        "operator": {
            "name": s.operator_name, "cvr": s.operator_cvr, "address": s.operator_address,
            "contact": s.operator_contact, "dpo": s.dpo_contact, "security": s.security_contact,
        },
        "hosting": {"provider": s.hosting_provider, "location": s.hosting_location},
        "retention": {"defaultMonths": s.default_retention_months},
        "cookies": [
            {"name": RESP_COOKIE, "purpose": "Holder din besvarelse sammen, mens du svarer.",
             "idleMinutes": s.respondent_session_ttl // 60, "maxHours": s.respondent_session_max // 3600},
            {"name": ADMIN_COOKIE, "purpose": "Login for administratorer (kun admin-siden).",
             "idleMinutes": s.admin_session_ttl // 60, "maxHours": s.admin_session_max // 3600},
        ],
        "minCellSize": s.min_cell_size,
    }
