"""Fælles fixtures. Integrationstests kører mod MariaDB i test_qa_*-databaser
(DB_SCHEMA_PREFIX=test_) via `docker compose --profile test run --rm test`."""
from __future__ import annotations

import json
import os
import pathlib
import random
import time

import pyotp
import pytest
from hypothesis import settings as hyp_settings
from sqlalchemy import create_engine, text

hyp_settings.register_profile("ci", database=None, deadline=None)
hyp_settings.load_profile("ci")

SAMPLE = pathlib.Path("/app/data/sample_almenramme_survey.json")


def _db_available() -> bool:
    if os.environ.get("DB_SCHEMA_PREFIX") != "test_":
        return False
    try:
        from app.db import make_url

        create_engine(make_url()).connect().close()
        return True
    except Exception:  # noqa: BLE001
        return False


def pytest_collection_modifyitems(config, items):
    if _db_available():
        return
    skip = pytest.mark.skip(reason="Ingen test-database (kør via docker compose --profile test)")
    for it in items:
        if "integration" in it.keywords:
            it.add_marker(skip)


def reset_databases() -> None:
    from app.db import SCHEMAS, get_engine, make_url, schema_map

    eng = create_engine(make_url())
    with eng.begin() as c:
        for sname in SCHEMAS:
            name = schema_map()[sname]
            assert name.startswith("test_"), "nægter at røre ikke-test-databaser"
            c.execute(text(f"DROP DATABASE IF EXISTS `{name}`"))
            c.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    get_engine.cache_clear()


def alembic_cfg():
    from alembic.config import Config

    return Config("/app/alembic.ini")


@pytest.fixture(scope="session")
def migrated():
    from alembic import command

    reset_databases()
    command.upgrade(alembic_cfg(), "head")
    yield


@pytest.fixture()
def client(migrated):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_rate_limits(request):
    if "integration" in request.keywords and _db_available():
        request.getfixturevalue("migrated")
        from app.db import get_engine, qualified

        with get_engine().begin() as c:
            c.execute(text(f"DELETE FROM {qualified('qa_identity', 'rate_limits')}"))
    yield


# ---------------------------------------------------------------- helpers


def make_admin(username: str, scopes: list[dict], password: str = "korrekt-hest-batteri-hæfteklamme"):
    """Opretter en aktiv admin med kendt TOTP-hemmelighed (springer MFA-opsætning over)."""
    from app.db import session_scope
    from app.models import User, UserScope
    from app.security import argon2_hash, encrypt_secret

    secret = pyotp.random_base32()
    with session_scope() as db:
        u = User(username=username, password_hash=argon2_hash(password), totp_secret_enc=encrypt_secret(secret),
                 totp_enabled=True, must_change_password=False)
        db.add(u)
        db.flush()
        for sc in scopes:
            db.add(UserScope(user_id=u.id, **sc))
        uid = u.id
    return {"id": uid, "username": username, "password": password, "secret": secret}


def login(client, admin) -> str:
    from app.db import session_scope
    from app.models import User

    with session_scope() as db:  # tillad flere logins i samme 30-sek-vindue i tests
        db.get(User, admin["id"]).totp_last_step = None
    r = client.post("/api/admin/auth/login", json={"username": admin["username"], "password": admin["password"]})
    assert r.status_code == 200, r.text
    csrf = r.json()["csrfToken"]
    r = client.post("/api/admin/auth/mfa/verify", json={"code": pyotp.TOTP(admin["secret"]).now()},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    return r.json()["csrfToken"]


def make_tenant(name: str, k: int = 10) -> str:
    from app.db import session_scope
    from app.models import Tenant

    with session_scope() as db:
        t = Tenant(name=name, min_cell_size=k)
        db.add(t)
        db.flush()
        return t.id


def sample_doc() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def insert_responses(tenant_id: str, unit_id: str, sv_id: str, n: int, seed: int = 1, shift: float = 0.0):
    """Indsætter n fuldførte SYNTETISKE besvarelser direkte (hurtigt)."""
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import Answer, OrganizationUnit, Question, Response, Subscale

    rng = random.Random(seed)
    with session_scope() as db:
        unit = db.get(OrganizationUnit, unit_id)
        qs = db.execute(select(Question.id, Question.question_key, Subscale.code)
                        .join(Subscale, Subscale.id == Question.subscale_id)
                        .where(Question.survey_version_id == sv_id)).all()
        from app.models import utcnow
        now = utcnow()
        for _ in range(n):
            theta = 3.5 + shift + rng.gauss(0, 0.8)
            r = Response(tenant_id=tenant_id, unit_id=unit_id, unit_type=unit.unit_type, survey_version_id=sv_id,
                         seed=rng.getrandbits(32), block_order=["self", "team", "frame", "expect"],
                         presentation_order=[q[1] for q in qs], app_version="test", status="completed",
                         completed_at=now, background={"profession": rng.choice(["paedagog", "laerer"])},
                         is_synthetic=True)
            db.add(r)
            db.flush()
            for pos, (qid, _key, _sub) in enumerate(qs):
                v = int(min(6, max(1, round(theta + rng.gauss(0, 0.7)))))
                db.add(Answer(response_id=r.id, question_id=qid, value=v, global_position=pos, block_index=0,
                              block_position=pos, first_shown_at=now, answered_at=now, rt_ms=rng.randint(2000, 9000)))


def wait(sec: float) -> None:
    time.sleep(sec)
