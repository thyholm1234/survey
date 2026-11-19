"""Kryptografiske primitiver: Argon2id, HMAC-opslag, tokens, TOTP-kryptering."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

# OWASP-anbefalet Argon2id-profil (m=64 MiB, t=3, p=1)
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)

# Uden tvetydige tegn: ingen 0/O, 1/I/L
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 12  # ≈ 59 bit entropi

_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))


def argon2_hash(secret: str) -> str:
    return _ph.hash(secret)


def argon2_verify(hash_: str | None, secret: str) -> bool:
    """Konstant-ish tid: verificér mod dummy-hash hvis ingen hash findes."""
    try:
        return _ph.verify(hash_ or _DUMMY_HASH, secret) and hash_ is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def argon2_needs_rehash(hash_: str) -> bool:
    return _ph.check_needs_rehash(hash_)


def generate_code(length: int = CODE_LENGTH) -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
    return "-".join(raw[i : i + 4] for i in range(0, length, 4))


_NORMALIZE_RE = re.compile(r"[^A-Z0-9]")


def normalize_code(code: str) -> str:
    return _NORMALIZE_RE.sub("", code.upper())[:64]


def code_lookup(code: str, purpose: str = "code") -> str:
    """Peppered HMAC til indekseret opslag; selve verifikationen sker med Argon2id."""
    key = base64.b64decode(get_settings().code_lookup_pepper.get_secret_value())
    msg = f"{purpose}:{normalize_code(code)}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ip_pseudonym(ip: str | None) -> str:
    """Dagligt roterende HMAC af IP – rå IP gemmes aldrig."""
    if not ip:
        return "none"
    key = base64.b64decode(get_settings().ip_hash_key.get_secret_value())
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return hmac.new(key, f"{day}|{ip}".encode(), hashlib.sha256).hexdigest()[:32]


def consteq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _fernet() -> Fernet:
    return Fernet(get_settings().totp_enc_key.get_secret_value().encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


PASSWORD_MIN = 14


def password_problems(pw: str, username: str = "") -> list[str]:
    """NIST 800-63B-inspireret: længde frem for kompleksitetsregler."""
    problems = []
    if len(pw) < PASSWORD_MIN:
        problems.append(f"Adgangskoden skal være mindst {PASSWORD_MIN} tegn.")
    if len(pw) > 256:
        problems.append("Adgangskoden er for lang.")
    if username and username.lower() in pw.lower():
        problems.append("Adgangskoden må ikke indeholde brugernavnet.")
    if len(set(pw)) < 6:
        problems.append("Adgangskoden har for få forskellige tegn.")
    return problems
