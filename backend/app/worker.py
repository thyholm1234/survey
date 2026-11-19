"""Analyse-worker: henter køede analysekørsler fra qa_analysis og udfører dem.

Kører som DB-brugeren qa_worker: kun SELECT på qa_data, SELECT/UPDATE på
qa_analysis og INSERT på qa_audit – ingen adgang til identitetsdata.
"""
from __future__ import annotations

import json
import logging
import signal
import threading
import traceback

from sqlalchemy import text

from . import audit
from .config import get_settings
from .db import get_engine, qualified, session_scope
from .models import utcnow
from .services import analysis_runner
from .services.stats import software_versions

log = logging.getLogger("worker")
stop = threading.Event()


def claim_one() -> dict | None:
    table = qualified("qa_analysis", "analysis_runs")
    with get_engine().begin() as conn:
        row = conn.execute(text(
            f"SELECT id, tenant_id, kind, params, filters, allowed_unit_ids FROM {table} "
            "WHERE status = 'queued' ORDER BY requested_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )).mappings().first()
        if row is None:
            return None
        conn.execute(text(f"UPDATE {table} SET status='running', started_at=:now WHERE id=:id"),
                     {"now": utcnow(), "id": row["id"]})
    return dict(row)


def _j(v):
    return json.loads(v) if isinstance(v, str) else (v or {})


def process(run: dict) -> None:
    table = qualified("qa_analysis", "analysis_runs")
    try:
        with session_scope() as db:
            result, digest = analysis_runner.execute(
                db, run["tenant_id"], run["kind"], _j(run["filters"]), _j(run["allowed_unit_ids"]) or [],
                _j(run["params"]), get_settings().min_cell_size,
            )
        payload = json.dumps(result, ensure_ascii=False, default=str, allow_nan=False)
        with get_engine().begin() as conn:
            conn.execute(text(
                f"UPDATE {table} SET status='done', finished_at=:now, result=:r, software=:sw, "
                "data_sha256=:h WHERE id=:id"),
                {"now": utcnow(), "r": payload, "sw": json.dumps(software_versions()), "h": digest,
                 "id": run["id"]})
        audit.record("analysis.done", actor_type="system", tenant_id=run["tenant_id"],
                     target_type="analysis_run", target_id=run["id"], details={"kind": run["kind"]})
    except Exception as exc:  # noqa: BLE001
        log.error("analyse %s fejlede: %s", run["id"], traceback.format_exc(limit=5))
        with get_engine().begin() as conn:
            conn.execute(text(f"UPDATE {table} SET status='failed', finished_at=:now, error=:e WHERE id=:id"),
                         {"now": utcnow(), "e": f"{type(exc).__name__}: analysen kunne ikke gennemføres"[:1000],
                          "id": run["id"]})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    log.info("worker startet")
    while not stop.is_set():
        try:
            run = claim_one()
        except Exception:  # noqa: BLE001
            log.exception("kunne ikke hente job")
            stop.wait(5)
            continue
        if run is None:
            stop.wait(2)
            continue
        process(run)


if __name__ == "__main__":
    main()
