"""Databaseforbindelse. Fire adskilte MariaDB-databaser (schemas):

qa_identity  – admins, sessioner, adgangskoder, rate-limit
qa_data      – organisation, spørgeskemaer og pseudonyme besvarelser
qa_analysis  – analysekørsler
qa_audit     – append-only auditlog
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

SCHEMAS = ("qa_identity", "qa_data", "qa_analysis", "qa_audit")


def schema_map() -> dict[str, str]:
    s = get_settings()
    return {name: s.schema(name) for name in SCHEMAS}


def make_url(database: str | None = None) -> URL:
    s = get_settings()
    return URL.create(
        "mysql+pymysql",
        username=s.db_user,
        password=s.db_password.get_secret_value(),
        host=s.db_host,
        port=s.db_port,
        database=database,
        query={"charset": "utf8mb4"},
    )


@lru_cache
def get_engine() -> Engine:
    engine = create_engine(
        make_url(),
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=10,
        isolation_level="READ COMMITTED",
        execution_options={"schema_translate_map": schema_map()},
    )
    return engine


@lru_cache
def _sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI-dependency: én transaktion pr. request."""
    db = _sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = _sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def qualified(schema: str, table: str) -> str:
    """Fuldt kvalificeret tabelnavn til rå SQL (respekterer test-præfiks)."""
    return f"`{schema_map()[schema]}`.`{table}`"


def ping() -> bool:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
