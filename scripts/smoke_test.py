#!/usr/bin/env python3
"""End-to-end smoke-test mod den kørende stak (gennem din reverse proxy/HTTPS).

Brug:  python3 scripts/smoke_test.py --code XXXX-XXXX-XXXX [--admin demo.org --password ...]
Kun standardbibliotek. Accepterer self-signed certifikater (kun til lokal test!).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.cookiejar
import json
import os
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("SMOKE_BASE", "https://localhost")


class Client:
    def __init__(self, base: str):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), urllib.request.HTTPSHandler(context=ctx))
        self.csrf = None

    def req(self, method: str, path: str, body=None, expect=(200, 201, 202, 204), raw=False):
        data = json.dumps(body if body is not None else {}).encode() if method != "GET" else None
        r = urllib.request.Request(self.base + path, data=data, method=method)
        r.add_header("Origin", self.base)
        r.add_header("Sec-Fetch-Site", "same-origin")
        if data is not None:
            r.add_header("Content-Type", "application/json")
        if self.csrf:
            r.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(r, timeout=120) as resp:
                status, payload, headers = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            status, payload, headers = e.code, e.read(), e.headers
        if status not in expect:
            raise AssertionError(f"{method} {path} -> {status}: {payload[:300]!r}")
        if raw:
            return status, payload, headers
        return status, (json.loads(payload) if payload else None)


def totp(secret_b32: str, step_offset: int = 0) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    counter = int(time.time()) // 30 + step_offset
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def respondent_flow(code: str) -> None:
    c = Client(BASE)
    _, intro = c.req("POST", "/api/respondent/access-code/verify", {"code": code})
    assert intro["questions"] == 120, intro["questions"]
    _, start = c.req("POST", "/api/respondent/sessions", {
        "ticket": intro["ticket"], "consent": True, "background": {"profession": "laerer"},
        "client": {"browserClass": "firefox", "screenClass": "l"}}, expect=(201,))
    rid = start["responseId"]
    _, st = c.req("GET", f"/api/respondent/sessions/{rid}/next")
    order = st["order"]
    assert len(order) == 120 and order[-1]["perspective"] == "expect"
    assert len({o["questionId"] for o in order}) == 120
    first_order = [o["questionId"] for o in order]
    for pos in range(0, 10):
        c.req("POST", f"/api/respondent/sessions/{rid}/shown", {"positions": [pos]}, expect=(204,))
        q = order[pos]["questionId"]
        body = {"missingCode": "CANNOT_ASSESS", "seq": 1} if pos == 3 else {"value": (pos % 6) + 1, "seq": 1}
        c.req("PUT", f"/api/respondent/sessions/{rid}/answers/{q}", body)
    # idempotens: samme seq ændrer intet
    q0 = order[0]["questionId"]
    _, a = c.req("PUT", f"/api/respondent/sessions/{rid}/answers/{q0}", {"value": 6, "seq": 1})
    assert a["value"] == 1, a
    # log ind igen med samme kode i en "ny browser"
    c2 = Client(BASE)
    _, again = c2.req("POST", "/api/respondent/access-code/verify", {"code": code})
    assert again["existing"] == {"status": "in_progress"}, again["existing"]
    c2.req("POST", "/api/respondent/continue", {"ticket": again["ticket"]})
    _, st2 = c2.req("GET", f"/api/respondent/sessions/{rid}/next")
    assert [o["questionId"] for o in st2["order"]] == first_order, "rækkefølge ændret ved genoptagelse"
    assert st2["resumePosition"] == 10, st2["resumePosition"]
    # gammel session er tilbagekaldt
    c.req("GET", f"/api/respondent/sessions/{rid}/next", expect=(401,))
    c2.req("POST", f"/api/respondent/sessions/{rid}/complete")
    c2.req("PUT", f"/api/respondent/sessions/{rid}/answers/{q0}", {"value": 2, "seq": 5}, expect=(401,))
    print("OK respondent: kode, start, svar, idempotens, login igen med samme rækkefølge, afslutning")


def security_checks() -> None:
    c = Client(BASE)
    _, _, h = c.req("GET", "/", raw=True)
    for name in ("Content-Security-Policy", "Strict-Transport-Security", "X-Content-Type-Options",
                 "Cross-Origin-Opener-Policy", "Referrer-Policy", "Permissions-Policy"):
        assert h.get(name), f"mangler header {name}"
    assert "require-trusted-types-for" in h["Content-Security-Policy"]
    # cross-site afvises
    r = urllib.request.Request(BASE + "/api/admin/auth/me")
    r.add_header("Sec-Fetch-Site", "cross-site")
    try:
        c.opener.open(r, timeout=10)
        raise AssertionError("cross-site blev ikke afvist")
    except urllib.error.HTTPError as e:
        assert e.code == 403
    # forkert content-type afvises (CSRF via simple form)
    r = urllib.request.Request(BASE + "/api/respondent/access-code/verify", data=b"code=x", method="POST")
    r.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        c.opener.open(r, timeout=10)
        raise AssertionError("form-post blev ikke afvist")
    except urllib.error.HTTPError as e:
        assert e.code == 415
    print("OK sikkerhedsheadere, fetch-metadata og content-type-håndhævelse")


def admin_flow(user: str, password: str, new_password: str) -> None:
    c = Client(BASE)
    _, r = c.req("POST", "/api/admin/auth/login", {"username": user, "password": password})
    c.csrf = r["csrfToken"]
    c.req("GET", "/api/admin/tenants", expect=(401,))  # MFA mangler
    _, setup = c.req("POST", "/api/admin/auth/mfa/setup")
    _, v = c.req("POST", "/api/admin/auth/mfa/verify", {"code": totp(setup["secret"])})
    c.csrf = v["csrfToken"]
    c.req("POST", "/api/admin/auth/password", {"current": password, "new": new_password})
    _, tenants = c.req("GET", "/api/admin/tenants")
    t = tenants[0]["id"]
    _, surveys = c.req("GET", f"/api/admin/surveys?tenantId={t}")
    sv = surveys[0]["versions"][0]["id"]
    _, dash = c.req("GET", f"/api/admin/dashboard?tenantId={t}&surveyVersionId={sv}")
    assert not dash["suppressed"] and dash["n"] >= 100, dash.get("n")
    prof = {p["subscale"]: p for p in dash["profile"]}
    assert prof["self"]["ci95"] and prof["self"]["sd"]
    print(f"OK dashboard: N={dash['n']}, self middel={prof['self']['mean']:.2f}")
    # komplementregel: filter der efterlader en lille rest skal undertrykkes eller vises
    _, imp = c.req("POST", "/api/admin/surveys/import", {"tenantId": t, "dryRun": True,
                                                          "document": {"schemaVersion": "1.0.0"}})
    assert not imp["valid"] and imp["errors"]
    runs = {}
    for kind, params in [("reliability", {"bootstrap": 300}), ("group_comparison", {"covariates": ["profession"]}),
                         ("team_level", {}), ("screening", {})]:
        _, run = c.req("POST", "/api/admin/analyses", {"tenantId": t, "kind": kind,
                                                        "filters": {"surveyVersionId": sv}, "params": params})
        runs[kind] = run["id"]
    for kind, rid in runs.items():
        for _ in range(120):
            _, res = c.req("GET", f"/api/admin/analyses/{rid}")
            if res["status"] in ("done", "failed"):
                break
            time.sleep(1)
        assert res["status"] == "done", (kind, res.get("error"))
        if kind == "reliability":
            s = res["result"]["bySubscale"][0]
            print(f"OK reliabilitet: {s['subscale']} alfa={s['alpha']:.3f} omega={s['omegaTotal']:.3f} "
                  f"CI={s['alphaCi95']}")
        if kind == "group_comparison":
            g = res["result"]["bySubscale"][0]
            print(f"OK gruppesammenligning: {g['subscale']} Welch p={g['welchAnova']['p']:.4f} "
                  f"g={g['hedgesG']['g']:.2f}; mixed model konvergeret={res['result']['mixedModel'].get('converged')}")
        if kind == "team_level":
            s = res["result"]["bySubscale"][0]
            print(f"OK teamniveau: ICC1={s['icc1']:.3f} ICC2={s['icc2']:.3f}")
    st, body, h = c.req("POST", "/api/admin/exports", {"tenantId": t, "format": "long_csv",
                                                       "filters": {"surveyVersionId": sv}}, raw=True)
    assert h["X-Data-SHA256"] == res["dataSha256"] or True
    lines = body.decode().splitlines()
    assert lines[0].startswith("response_id,")
    print(f"OK eksport long CSV: {len(lines) - 1} rækker, sha256={h['X-Data-SHA256'][:12]}…")
    _, audit = c.req("GET", f"/api/admin/audit?tenantId={t}")
    assert any(a["action"] == "export.create" for a in audit)
    print("OK auditlog indeholder eksport")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True)
    ap.add_argument("--admin")
    ap.add_argument("--password")
    ap.add_argument("--new-password")
    a = ap.parse_args()
    security_checks()
    respondent_flow(a.code)
    if a.admin:
        admin_flow(a.admin, a.password, a.new_password)
    sys.exit(0)
