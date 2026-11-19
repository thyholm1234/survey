"""Append-only auditlog med hash-kæde (manipulationsevidens).

DB-brugerne qa_api/qa_worker har kun SELECT/INSERT på qa_audit, så hændelser
kan ikke ændres eller slettes af applikationen. Kæden serialiseres med
GET_LOCK, så den er konsistent på tværs af workers.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text

from .db import get_engine, qualified, schema_map
from .models import utcnow

GENESIS = "0" * 64


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def record(
    action: str,
    *,
    actor_type: str,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    table = qualified("qa_audit", "audit_events")
    lock_name = f"{schema_map()['qa_audit']}.audit_chain"
    now = utcnow()
    with get_engine().begin() as conn:
        got = conn.execute(text("SELECT GET_LOCK(:n, 10)"), {"n": lock_name}).scalar()
        if got != 1:
            raise RuntimeError("audit lock timeout")
        try:
            prev = conn.execute(text(f"SELECT hash FROM {table} ORDER BY id DESC LIMIT 1")).scalar()
            prev = prev or GENESIS
            body = {
                "at": now.isoformat(timespec="milliseconds"),
                "actor_type": actor_type,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "details": details or {},
            }
            digest = hashlib.sha256((prev + _canonical(body)).encode()).hexdigest()
            conn.execute(
                text(
                    f"INSERT INTO {table} (at, actor_type, actor_id, tenant_id, action, target_type, "
                    "target_id, details, prev_hash, hash) VALUES (:at, :actor_type, :actor_id, "
                    ":tenant_id, :action, :target_type, :target_id, :details, :prev, :hash)"
                ),
                {**body, "at": now, "details": _canonical(body["details"]), "prev": prev, "hash": digest},
            )
        finally:
            conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": lock_name})


def verify_chain(limit: int | None = None) -> dict[str, Any]:
    """Genberegn kæden; returnerer første brud, hvis et findes."""
    table = qualified("qa_audit", "audit_events")
    prev = GENESIS
    n = 0
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT id, at, actor_type, actor_id, tenant_id, action, target_type, target_id, "
                f"details, prev_hash, hash FROM {table} ORDER BY id"
                + (f" LIMIT {int(limit)}" if limit else "")
            )
        )
        for r in rows:
            details = r.details if isinstance(r.details, dict) else json.loads(r.details or "{}")
            body = {
                "at": r.at.isoformat(timespec="milliseconds"),
                "actor_type": r.actor_type,
                "actor_id": r.actor_id,
                "tenant_id": r.tenant_id,
                "action": r.action,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "details": details,
            }
            expect = hashlib.sha256((prev + _canonical(body)).encode()).hexdigest()
            if r.prev_hash != prev or r.hash != expect:
                return {"ok": False, "brokenAt": r.id, "checked": n}
            prev = r.hash
            n += 1
    return {"ok": True, "checked": n}
