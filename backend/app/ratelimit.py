"""Databasebaseret rate limiting (fungerer på tværs af uvicorn-workers).

Tællinger skrives i en selvstændig, straks committet transaktion, så et
fejlet request ikke ruller tællingen tilbage. Buckets indeholder kun
pseudonymiserede nøgler (dagligt roterende HMAC af IP).
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import text

from .db import get_engine, qualified
from .models import utcnow
from .security import ip_pseudonym


def client_ip(request: Request) -> str | None:
    # uvicorn --proxy-headers med --forwarded-allow-ips=<proxy-IP> sætter request.client korrekt
    return request.client.host if request.client else None


def hit(bucket: str, limit: int, window_s: int) -> tuple[bool, int]:
    """Registrér ét forsøg. Returnerer (tilladt, sekunder til reset)."""
    now = utcnow()
    exp = now + timedelta(seconds=window_s)
    table = qualified("qa_identity", "rate_limits")
    with get_engine().begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {table} (bucket, window_start, count, expires_at) "
                "VALUES (:b, :now, 1, :exp) ON DUPLICATE KEY UPDATE "
                "count = IF(expires_at <= :now, 1, count + 1), "
                "window_start = IF(expires_at <= :now, :now, window_start), "
                "expires_at = IF(expires_at <= :now, :exp, expires_at)"
            ),
            {"b": bucket[:100], "now": now, "exp": exp},
        )
        row = conn.execute(
            text(f"SELECT count, expires_at FROM {table} WHERE bucket = :b"), {"b": bucket[:100]}
        ).one()
    retry = max(1, int((row.expires_at - now).total_seconds()))
    return row.count <= limit, retry


def reset(bucket: str) -> None:
    table = qualified("qa_identity", "rate_limits")
    with get_engine().begin() as conn:
        conn.execute(text(f"DELETE FROM {table} WHERE bucket = :b"), {"b": bucket[:100]})


def enforce(request: Request, scope: str, limit: int, window_s: int, extra: str = "") -> str:
    bucket = f"{scope}:{ip_pseudonym(client_ip(request))}{(':' + extra) if extra else ''}"
    ok, retry = hit(bucket, limit, window_s)
    if not ok:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "For mange forsøg. Prøv igen senere.",
            headers={"Retry-After": str(retry)},
        )
    return bucket


def bucket_for(request: Request, scope: str, extra: str = "") -> str:
    return f"{scope}:{ip_pseudonym(client_ip(request))}{(':' + extra) if extra else ''}"


def check_blocked(bucket: str, limit: int) -> None:
    """Afvis hvis grænsen for FEJLEDE forsøg er nået (tæller ikke selv).

    Kun fejl tæller, så kolleger bag samme NAT-IP ikke blokeres af gyldige logins.
    """
    table = qualified("qa_identity", "rate_limits")
    now = utcnow()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT count, expires_at FROM {table} WHERE bucket = :b"), {"b": bucket[:100]}
        ).first()
    if row and row.expires_at > now and row.count >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "For mange mislykkede forsøg. Prøv igen senere.",
            headers={"Retry-After": str(max(1, int((row.expires_at - now).total_seconds())))},
        )


def purge_expired() -> int:
    table = qualified("qa_identity", "rate_limits")
    with get_engine().begin() as conn:
        res = conn.execute(text(f"DELETE FROM {table} WHERE expires_at < :now"), {"now": utcnow()})
    return res.rowcount or 0
