"""Admin-login: adgangskode (Argon2id) + obligatorisk TOTP.

Sessionstoken roteres efter MFA (beskytter mod session fixation).
Klar til senere udskiftning/supplement med Entra ID/OIDC.
"""
from __future__ import annotations

import secrets
import time
from datetime import timedelta

import pyotp
import segno
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit, ratelimit
from ..config import get_settings
from ..db import get_db
from ..deps import ADMIN_COOKIE, Principal, admin, admin_partial, clear_cookie, set_cookie
from ..models import AdminSession, User, utcnow
from ..security import (
    argon2_hash,
    argon2_needs_rehash,
    argon2_verify,
    decrypt_secret,
    encrypt_secret,
    new_token,
    password_problems,
    token_digest,
)

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])

LOCK_AFTER = 10
LOCK_MINUTES = 15


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(Strict):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class TotpIn(Strict):
    code: str = Field(pattern=r"^\d{6}$")


class PasswordIn(Strict):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=1, max_length=256)


def _issue_session(db: Session, response: Response, user: User, mfa: bool) -> AdminSession:
    s = get_settings()
    token = new_token()
    now = utcnow()
    sess = AdminSession(
        id=token_digest(token), user_id=user.id, csrf_token=secrets.token_urlsafe(32),
        mfa_passed=mfa, created_at=now, last_seen_at=now,
        absolute_expires_at=now + timedelta(seconds=s.admin_session_max),
    )
    db.add(sess)
    set_cookie(response, ADMIN_COOKIE, token, s.admin_session_max)
    return sess


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    username = body.username.strip().lower()
    ip_bucket = ratelimit.bucket_for(request, "login")
    user_bucket = f"login-user:{token_digest(username)[:40]}"
    ratelimit.check_blocked(ip_bucket, s.rl_login_attempts)
    ratelimit.check_blocked(user_bucket, s.rl_login_attempts * 2)
    user = db.scalar(select(User).where(User.username == username))
    ok = argon2_verify(user.password_hash if user else None, body.password)
    now = utcnow()
    locked = user is not None and user.locked_until is not None and user.locked_until > now
    if not ok or user is None or user.status != "active" or locked:
        ratelimit.hit(ip_bucket, s.rl_login_attempts, s.rl_login_window)
        ratelimit.hit(user_bucket, s.rl_login_attempts * 2, s.rl_login_window)
        if user is not None and not locked:
            user.failed_logins += 1
            if user.failed_logins >= LOCK_AFTER:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_logins = 0
            db.commit()
        audit.record("auth.login_failed", actor_type="anonymous",
                     details={"userKnown": user is not None, "locked": locked})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Forkert brugernavn eller adgangskode.")
    user.failed_logins = 0
    if argon2_needs_rehash(user.password_hash):
        user.password_hash = argon2_hash(body.password)
    sess = _issue_session(db, response, user, mfa=False)
    audit.record("auth.password_ok", actor_type="user", actor_id=user.id)
    return {"mfaEnrolled": user.totp_enabled, "mustChangePassword": user.must_change_password,
            "csrfToken": sess.csrf_token}


@router.post("/mfa/setup")
def mfa_setup(ctx=Depends(admin_partial), db: Session = Depends(get_db)):
    user, _sess = ctx
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "To-faktor er allerede opsat.")
    secret = pyotp.random_base32(length=32)
    user.totp_secret_enc = encrypt_secret(secret)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name="Spørgeskema-admin")
    qr = segno.make(uri, error="m").svg_data_uri(scale=5, dark="#000", light="#fff")
    return {"secret": secret, "otpauthUri": uri, "qrSvgDataUri": qr}


@router.post("/mfa/verify")
def mfa_verify(body: TotpIn, request: Request, response: Response, ctx=Depends(admin_partial),
               db: Session = Depends(get_db)):
    s = get_settings()
    user, sess = ctx
    bucket = f"mfa:{user.id}"
    ratelimit.check_blocked(bucket, s.rl_login_attempts)
    secret = decrypt_secret(user.totp_secret_enc) if user.totp_secret_enc else None
    if not secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "To-faktor er ikke opsat.")
    totp = pyotp.TOTP(secret)
    now_step = int(time.time()) // 30
    matched = None
    for offset in (-1, 0, 1):
        step = now_step + offset
        if secrets.compare_digest(totp.at(step * 30), body.code):
            matched = step
    # Replay-beskyttelse: samme eller ældre tidstrin kan ikke genbruges
    if matched is None or (user.totp_last_step is not None and matched <= user.totp_last_step):
        ratelimit.hit(bucket, s.rl_login_attempts, s.rl_login_window)
        audit.record("auth.mfa_failed", actor_type="user", actor_id=user.id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ugyldig kode.")
    user.totp_last_step = matched
    first = not user.totp_enabled
    user.totp_enabled = True
    user.last_login_at = utcnow()
    ratelimit.reset(bucket)
    db.delete(sess)  # rotér session
    new = _issue_session(db, response, user, mfa=True)
    audit.record("auth.mfa_enrolled" if first else "auth.login", actor_type="user", actor_id=user.id)
    return {"csrfToken": new.csrf_token, "mustChangePassword": user.must_change_password}


@router.post("/password")
def change_password(body: PasswordIn, ctx=Depends(admin_partial), db: Session = Depends(get_db)):
    user, sess = ctx
    if not sess.mfa_passed:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "To-faktor-godkendelse mangler.")
    if not argon2_verify(user.password_hash, body.current):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nuværende adgangskode er forkert.")
    problems = password_problems(body.new, user.username)
    if body.new == body.current:
        problems.append("Den nye adgangskode skal være forskellig fra den nuværende.")
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, " ".join(problems))
    user.password_hash = argon2_hash(body.new)
    user.must_change_password = False
    # Log alle andre sessioner ud
    db.execute(delete(AdminSession).where(AdminSession.user_id == user.id, AdminSession.id != sess.id))
    audit.record("auth.password_changed", actor_type="user", actor_id=user.id)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(ADMIN_COOKIE)
    if token:
        sess = db.get(AdminSession, token_digest(token))
        if sess:
            db.delete(sess)
            audit.record("auth.logout", actor_type="user", actor_id=sess.user_id)
    clear_cookie(response, ADMIN_COOKIE)
    response.headers["Clear-Site-Data"] = '"cookies", "storage", "cache"'
    return {"ok": True}


@router.get("/me")
def me(ctx=Depends(admin_partial), db: Session = Depends(get_db)):
    user, sess = ctx
    return {
        "username": user.username,
        "mfaPassed": sess.mfa_passed,
        "mfaEnrolled": user.totp_enabled,
        "mustChangePassword": user.must_change_password,
        "csrfToken": sess.csrf_token,
        "scopes": [
            {"role": sc.role_code, "tenantId": sc.tenant_id, "unitId": sc.unit_id, "canExport": sc.can_export}
            for sc in user.scopes
        ],
    }


@router.get("/whoami")
def whoami(p: Principal = Depends(admin)):
    return {"username": p.user.username, "systemAdmin": p.system_admin,
            "tenants": sorted(p.tenants()), "orgTenants": sorted(p.org_tenants)}
