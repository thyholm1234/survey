"""Autentifikation og autorisation (admins og respondenter).

MariaDB har ikke row-level security. Tenant-isolation håndhæves derfor i ét
centralt lag (Principal) som alle admin-endpoints SKAL bruge, og dækkes af
isolationstests. Derudover er DB-privilegier adskilt pr. service.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AdminSession, OrganizationUnit, ResponseSession, User, utcnow
from .security import consteq, token_digest

ADMIN_COOKIE = "__Host-qa_admin"
RESP_COOKIE = "__Host-qa_resp"
CSRF_HEADER = "x-csrf-token"

ROLE_SYSTEM = "system_admin"
ROLE_ORG = "org_admin"
ROLE_UNIT = "unit_admin"


def set_cookie(response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name, value, max_age=max_age, path="/", secure=True, httponly=True, samesite="strict"
    )


def clear_cookie(response, name: str) -> None:
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="strict")


@dataclass
class Principal:
    user: User
    session: AdminSession
    system_admin: bool = False
    org_tenants: set[str] = field(default_factory=set)
    unit_scopes: dict[str, set[str]] = field(default_factory=dict)  # tenant -> units
    export_tenants: set[str] = field(default_factory=set)
    export_units: set[str] = field(default_factory=set)

    @property
    def id(self) -> str:
        return self.user.id

    def tenants(self) -> set[str]:
        return self.org_tenants | set(self.unit_scopes)

    def require_tenant(self, tenant_id: str, *, org: bool = False) -> None:
        """Adgang til tenantens data. org=True kræver organisationsadmin."""
        if tenant_id in self.org_tenants:
            return
        if not org and tenant_id in self.unit_scopes:
            return
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")

    def allowed_units(self, db: Session, tenant_id: str) -> set[str]:
        self.require_tenant(tenant_id)
        if tenant_id in self.org_tenants:
            return set(
                db.scalars(select(OrganizationUnit.id).where(OrganizationUnit.tenant_id == tenant_id))
            )
        return set(self.unit_scopes.get(tenant_id, set()))

    def require_unit(self, db: Session, tenant_id: str, unit_id: str) -> None:
        if unit_id not in self.allowed_units(db, tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")

    def can_export(self, tenant_id: str, unit_ids: set[str]) -> bool:
        if tenant_id in self.export_tenants:
            return True
        return bool(unit_ids) and unit_ids <= self.export_units


def _load_principal(db: Session, user: User, sess: AdminSession) -> Principal:
    p = Principal(user=user, session=sess)
    for sc in user.scopes:
        if sc.role_code == ROLE_SYSTEM:
            p.system_admin = True
        elif sc.role_code == ROLE_ORG and sc.tenant_id:
            p.org_tenants.add(sc.tenant_id)
            if sc.can_export:
                p.export_tenants.add(sc.tenant_id)
        elif sc.role_code == ROLE_UNIT and sc.tenant_id and sc.unit_id:
            p.unit_scopes.setdefault(sc.tenant_id, set()).add(sc.unit_id)
            if sc.can_export:
                p.export_units.add(sc.unit_id)
    if p.unit_scopes:
        # Adgang til en institution omfatter dens afdelinger/klasser (ét niveau)
        scoped = set().union(*p.unit_scopes.values())
        for cid, parent, tid in db.execute(
            select(OrganizationUnit.id, OrganizationUnit.parent_id, OrganizationUnit.tenant_id)
            .where(OrganizationUnit.parent_id.in_(scoped))
        ):
            if parent in p.unit_scopes.get(tid, set()):
                p.unit_scopes[tid].add(cid)
                if parent in p.export_units:
                    p.export_units.add(cid)
    return p


def _admin_session(request: Request, db: Session) -> tuple[User, AdminSession]:
    token = request.cookies.get(ADMIN_COOKIE)
    if not token or len(token) > 128:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ikke logget ind.")
    sess = db.get(AdminSession, token_digest(token))
    s = get_settings()
    now = utcnow()
    if (
        sess is None
        or sess.absolute_expires_at <= now
        or sess.last_seen_at + timedelta(seconds=s.admin_session_ttl) <= now
    ):
        if sess is not None:
            db.delete(sess)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessionen er udløbet.")
    user = db.get(User, sess.user_id)
    if user is None or user.status != "active":
        db.delete(sess)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ikke logget ind.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not consteq(sent, sess.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF-validering fejlede.")
    sess.last_seen_at = now
    return user, sess


def admin_partial(request: Request, db: Session = Depends(get_db, scope="function")) -> tuple[User, AdminSession]:
    """Session uden krav om gennemført MFA (bruges kun til MFA-opsætning/-verifikation)."""
    return _admin_session(request, db)


def admin(request: Request, db: Session = Depends(get_db, scope="function")) -> Principal:
    user, sess = _admin_session(request, db)
    if not sess.mfa_passed:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "To-faktor-godkendelse mangler.")
    if user.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du skal skifte adgangskode.")
    return _load_principal(db, user, sess)


def system_admin(p: Principal = Depends(admin)) -> Principal:
    if not p.system_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kræver systemadministrator.")
    return p


# ---------------------------------------------------------------------------
# Respondent
# ---------------------------------------------------------------------------


def respondent(request: Request, db: Session = Depends(get_db, scope="function")) -> ResponseSession:
    token = request.cookies.get(RESP_COOKIE)
    if not token or len(token) > 128:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ingen aktiv besvarelse.")
    sess = db.get(ResponseSession, token_digest(token))
    s = get_settings()
    now = utcnow()
    if (
        sess is None
        or sess.revoked
        or sess.absolute_expires_at <= now
        or sess.last_seen_at + timedelta(seconds=s.respondent_session_ttl) <= now
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessionen er udløbet. Brug din genoptagelseskode.")
    sess.last_seen_at = now
    return sess
