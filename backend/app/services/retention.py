"""Datalivscyklus: slet rå besvarelser efter tenantens opbevaringsperiode og
ryd udløbne sessioner, billetter og rate-limit-poster.

Køres hver time af API'et (serialiseret med GET_LOCK på tværs af workers)
og kan startes manuelt af systemadmin.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from .. import audit, ratelimit
from ..config import get_settings
from ..db import get_engine, qualified, schema_map
from ..models import utcnow


def run_retention() -> dict:
    s = get_settings()
    now = utcnow()
    lock = f"{schema_map()['qa_data']}.retention"
    out: dict = {"responsesDeleted": 0}
    with get_engine().begin() as conn:
        if conn.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": lock}).scalar() != 1:
            return {"skipped": "kører allerede"}
        try:
            tenants = conn.execute(text(f"SELECT id, retention_months FROM {qualified('qa_data', 'tenants')}")).all()
            for t in tenants:
                cutoff = now - timedelta(days=30 * int(t.retention_months or s.default_retention_months))
                res = conn.execute(
                    text(f"DELETE FROM {qualified('qa_data', 'responses')} WHERE tenant_id=:t AND started_at < :c"),
                    {"t": t.id, "c": cutoff},
                )
                if res.rowcount:
                    out["responsesDeleted"] += res.rowcount
                    audit.record("retention.responses_deleted", actor_type="system", tenant_id=t.id,
                                 details={"count": res.rowcount, "cutoff": cutoff.isoformat()})
            # Påbegyndte, forladte besvarelser markeres efter 30 dage uden aktivitet
            conn.execute(text(
                f"UPDATE {qualified('qa_data', 'responses')} SET status='abandoned' "
                "WHERE status='in_progress' AND last_activity_at < :c"), {"c": now - timedelta(days=30)})
            out["adminSessions"] = conn.execute(text(
                f"DELETE FROM {qualified('qa_identity', 'admin_sessions')} WHERE absolute_expires_at < :n "
                "OR last_seen_at < :idle"), {"n": now, "idle": now - timedelta(seconds=s.admin_session_ttl)}).rowcount
            out["respondentSessions"] = conn.execute(text(
                f"DELETE FROM {qualified('qa_identity', 'response_sessions')} WHERE absolute_expires_at < :n "
                "OR revoked = 1"), {"n": now}).rowcount
            out["tickets"] = conn.execute(text(
                f"DELETE FROM {qualified('qa_identity', 'code_tickets')} WHERE expires_at < :n OR used = 1"),
                {"n": now - timedelta(minutes=1)}).rowcount
            out["resumeKeys"] = conn.execute(text(
                f"DELETE FROM {qualified('qa_identity', 'resume_keys')} WHERE expires_at < :n"), {"n": now}).rowcount
        finally:
            conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": lock})
    out["rateLimits"] = ratelimit.purge_expired()
    return out
