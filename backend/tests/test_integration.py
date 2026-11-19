"""Integrationstests: MVP-acceptkriterier, tenant-isolation, autorisation, rate limiting,
auditlog, immutabilitet og celleundertrykkelse (spec §15–16)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app import audit
from app.db import get_engine, qualified

from .conftest import insert_responses, login, make_admin, make_tenant, sample_doc

pytestmark = pytest.mark.integration


def H(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def org(client):
    """Tenant med org-admin (eksportret), publiceret survey og to afdelinger."""
    import uuid

    t = make_tenant(f"Kommune {uuid.uuid4().hex[:6]}")
    adm = make_admin(f"org.{uuid.uuid4().hex[:6]}", [{"role_code": "org_admin", "tenant_id": t, "can_export": True}])
    csrf = login(client, adm)
    r = client.post("/api/admin/surveys/import", json={"tenantId": t, "document": sample_doc(), "dryRun": True},
                    headers=H(csrf))
    assert r.json()["valid"] and r.json()["preview"]["questions"] == 120
    r = client.post("/api/admin/surveys/import", json={"tenantId": t, "document": sample_doc(), "dryRun": False},
                    headers=H(csrf))
    sv = r.json()["surveyVersionId"]
    assert client.post(f"/api/admin/surveys/{sv}/publish", json={}, headers=H(csrf)).status_code == 200
    units = {}
    for name, typ in [("Dagtilbud A", "daycare"), ("Skole B", "school")]:
        r = client.post(f"/api/admin/tenants/{t}/units", json={"name": name, "unitType": typ}, headers=H(csrf))
        assert r.status_code == 201, r.text
        units[typ] = r.json()["id"]
    survey_id = next(x["id"] for x in client.get(f"/api/admin/surveys?tenantId={t}").json())
    r = client.put(f"/api/admin/surveys/{survey_id}/assignments", json={"unitIds": list(units.values())},
                   headers=H(csrf))
    assert r.status_code == 200, r.text
    return {"tenant": t, "admin": adm, "csrf": csrf, "sv": sv, "survey": survey_id, "units": units}


def test_migrations_roundtrip(migrated):
    from alembic import command

    from .conftest import alembic_cfg

    command.downgrade(alembic_cfg(), "base")
    command.upgrade(alembic_cfg(), "head")
    with get_engine().connect() as c:
        assert c.execute(text(f"SELECT COUNT(*) FROM {qualified('qa_identity', 'roles')}")).scalar() == 3


def test_publish_is_immutable(client, org):
    r = client.post(f"/api/admin/surveys/{org['sv']}/publish", json={}, headers=H(org["csrf"]))
    assert r.status_code == 409
    with pytest.raises(Exception, match="immutable"):
        with get_engine().begin() as c:
            c.execute(text(f"UPDATE {qualified('qa_data', 'questions')} SET text='x' "
                           "WHERE survey_version_id=:s LIMIT 1"), {"s": org["sv"]})


def respondent_start(client, code: str) -> dict:
    r = client.post("/api/respondent/access-code/verify", json={"code": code})
    assert r.status_code == 200, r.text
    intro = r.json()
    r = client.post("/api/respondent/sessions", json={"ticket": intro["ticket"], "consent": True,
                                                      "background": {"profession": "laerer"}})
    assert r.status_code == 201, r.text
    return r.json()


def pdf_codes(pdf: bytes) -> list[str]:
    """Klartekstkoderne findes kun i PDF'en – træk dem ud af sidernes tekst."""
    import re
    import zlib

    streams = b"".join(zlib.decompress(m) for m in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.DOTALL))
    return [m.decode() for m in re.findall(rb"/M [0-9.]+ Tf [0-9. ]+ Td \(([A-Z0-9-]+)\) Tj", streams)]


def issue_codes(client, csrf, sv, units: dict[str, int], expect=200):
    r = client.post("/api/admin/access-codes", json={"surveyVersionId": sv,
                                                     "units": [{"unitId": u, "count": n} for u, n in units.items()]},
                    headers=H(csrf))
    assert r.status_code == expect, r.text
    return r


def make_code(client, org, unit="school") -> str:
    return pdf_codes(issue_codes(client, org["csrf"], org["sv"], {org["units"][unit]: 1}).content)[0]


def test_full_respondent_flow_and_resume(client, org):
    code = make_code(client, org)
    # Koden gemmes kun som hash
    with get_engine().connect() as c:
        rows = c.execute(text(f"SELECT code_hash, lookup_hmac FROM {qualified('qa_identity', 'access_codes')}")).all()
    assert all(code not in (r.code_hash + r.lookup_hmac) and r.code_hash.startswith("$argon2id$") for r in rows)

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(), base_url="https://testserver") as resp_client:
        start = respondent_start(resp_client, code)
        rid = start["responseId"]
        st = resp_client.get(f"/api/respondent/sessions/{rid}/next").json()
        order = st["order"]
        assert len(order) == 120 and {o["perspective"] for o in order[-30:]} == {"expect"}
        # ikke vist endnu -> 409
        q = order[0]["questionId"]
        assert resp_client.put(f"/api/respondent/sessions/{rid}/answers/{q}", json={"value": 3, "seq": 1}).status_code == 409
        assert resp_client.post(f"/api/respondent/sessions/{rid}/shown", json={"positions": [0, 1]}).status_code == 204
        assert resp_client.put(f"/api/respondent/sessions/{rid}/answers/{q}", json={"value": 9, "seq": 1}).status_code == 422
        assert resp_client.put(f"/api/respondent/sessions/{rid}/answers/{q}", json={"value": 3, "seq": 1}).json()["value"] == 3
        # ændring efter tilbage-navigation tælles
        resp_client.put(f"/api/respondent/sessions/{rid}/answers/{q}", json={"value": 5, "seq": 2, "viaBack": True})
        q2 = order[1]["questionId"]
        resp_client.put(f"/api/respondent/sessions/{rid}/answers/{q2}", json={"missingCode": "CANNOT_ASSESS", "seq": 1})
        # andre respondenters svar kan ikke tilgås
        assert resp_client.get("/api/respondent/sessions/deadbeefdeadbeefdeadbeefdeadbeef/next").status_code == 404

    with TestClient(create_app(), base_url="https://testserver") as other:  # login igen fra en anden enhed
        v = other.post("/api/respondent/access-code/verify", json={"code": code}).json()
        r = other.post("/api/respondent/continue", json={"ticket": v["ticket"]})
        assert r.status_code == 200
        st2 = other.get(f"/api/respondent/sessions/{rid}/next").json()
        assert [o["questionId"] for o in st2["order"]] == [o["questionId"] for o in order]
        assert st2["resumePosition"] == 2
        assert other.post(f"/api/respondent/sessions/{rid}/complete", json={}).status_code == 200
        v = other.post("/api/respondent/access-code/verify", json={"code": code}).json()
        assert other.post("/api/respondent/continue", json={"ticket": v["ticket"]}).status_code == 409

    with get_engine().connect() as c:
        a = c.execute(text(f"SELECT change_count, changed_after_back, rt_ms, global_position FROM "
                           f"{qualified('qa_data', 'answers')} a JOIN {qualified('qa_data', 'questions')} q "
                           "ON q.id=a.question_id WHERE a.response_id=:r AND q.question_key=:k"),
                      {"r": rid, "k": q}).one()
        assert a.change_count == 1 and a.changed_after_back == 1 and a.rt_ms is not None and a.global_position == 0
        m = c.execute(text(f"SELECT missing_code FROM {qualified('qa_data', 'answers')} a JOIN "
                           f"{qualified('qa_data', 'questions')} q ON q.id=a.question_id WHERE a.response_id=:r "
                           "AND q.question_key=:k"), {"r": rid, "k": q2}).scalar()
        assert m == "CANNOT_ASSESS"
        resp = c.execute(text(f"SELECT seed, block_order, survey_version_id FROM {qualified('qa_data', 'responses')} "
                              "WHERE id=:r"), {"r": rid}).one()
        assert resp.seed and "expect" in resp.block_order and resp.survey_version_id == org["sv"]


def test_personal_code_login_withdraw_and_answer_again(client, org):
    """Personlig kode: én besvarelse ad gangen; log ind igen for at fortsætte, trække tilbage og svare forfra."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    code = make_code(client, org)
    with TestClient(create_app(), base_url="https://testserver") as rc:
        first = respondent_start(rc, code)
        rid = first["responseId"]

        # Ny login med samme kode: påbegyndt besvarelse findes; en ny kan ikke startes
        v = rc.post("/api/respondent/access-code/verify", json={"code": code}).json()
        assert v["existing"] == {"status": "in_progress"}
        r = rc.post("/api/respondent/sessions", json={"ticket": v["ticket"], "consent": True})
        assert r.status_code == 409
        v = rc.post("/api/respondent/access-code/verify", json={"code": code}).json()
        r = rc.post("/api/respondent/continue", json={"ticket": v["ticket"]})
        assert r.status_code == 200 and r.json()["responseId"] == rid
        assert rc.post(f"/api/respondent/sessions/{rid}/complete", json={}).status_code == 200

        # Efter indsendelse: kan ikke fortsætte, men kan trække tilbage og svare forfra med samme billet
        v = rc.post("/api/respondent/access-code/verify", json={"code": code}).json()
        assert v["existing"] == {"status": "completed"}
        assert rc.post("/api/respondent/continue", json={"ticket": v["ticket"]}).status_code == 409
        # Rettigheder kan udøves med selve adgangskoden
        assert rc.post("/api/respondent/rights/export", json={"key": code}).json()["responseId"] == rid
        assert rc.post("/api/respondent/withdraw", json={"ticket": v["ticket"]}).json() == {"withdrawn": True}
        with get_engine().connect() as c:
            n = c.execute(text(f"SELECT COUNT(*) FROM {qualified('qa_data', 'responses')} WHERE id=:r"), {"r": rid}).scalar()
            assert n == 0
        r = rc.post("/api/respondent/sessions", json={"ticket": v["ticket"], "consent": True})
        assert r.status_code == 201 and r.json()["responseId"] != rid
        assert rc.post("/api/respondent/withdraw", json={"ticket": v["ticket"]}).status_code == 400  # brugt

    codes = client.get(f"/api/admin/access-codes?tenantId={org['tenant']}").json()
    c = codes[0]
    assert c["completions"] == 0 and c["starts"] == 2
    with get_engine().connect() as c:
        actions = {a for (a,) in c.execute(text(f"SELECT action FROM {qualified('qa_audit', 'audit_events')}"))}
    assert "respondent.withdrawn" in actions


def test_personal_codes_pdf_per_unit(client, org):
    t, csrf, school = org["tenant"], org["csrf"], org["units"]["school"]
    a = client.post(f"/api/admin/tenants/{t}/units", json={"name": "4.A", "parentId": school},
                    headers=H(csrf)).json()["id"]
    body = {"surveyVersionId": org["sv"], "label": "Forår",
            "units": [{"unitId": a, "count": 3}, {"unitId": org["units"]["daycare"], "count": 2}]}
    r = client.post("/api/admin/access-codes", json=body, headers=H(csrf))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF-1.4")
    assert r.content.count(b"/Type /Page ") == 2 + 5  # forside pr. afdeling + én side pr. kode
    codes = client.get(f"/api/admin/access-codes?tenantId={t}").json()
    assert len(codes) == 5 and sorted(c["label"] for c in codes if c["unitId"] == a) == [
        "Forår · nr. 1 af 3", "Forår · nr. 2 af 3", "Forår · nr. 3 af 3"]

    dup = {**body, "units": [{"unitId": a, "count": 1}, {"unitId": a, "count": 1}]}
    assert client.post("/api/admin/access-codes", json=dup, headers=H(csrf)).status_code == 422
    # Afdelingsadmin kan kun udstede til egne enheder
    ua = make_admin("unit.pdf", [{"role_code": "unit_admin", "tenant_id": t, "unit_id": org["units"]["daycare"]}])
    csrf2 = login(client, ua)
    r = client.post("/api/admin/access-codes", json=body, headers=H(csrf2))
    assert r.status_code == 404


def test_code_sheet_pdf_text_is_readable():
    import re
    import zlib
    from datetime import datetime

    from app.services import code_sheets

    pdf = code_sheets.build([code_sheets.UnitCodes("3.A", "Nordskolen", ["ABCD-EFGH-JKMN"])],
                            "Mestring (forældre)", "https://x.example", datetime(2027, 1, 31))
    joined = b"".join(zlib.decompress(m) for m in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.DOTALL))
    assert b"(ABCD-EFGH-JKMN)" in joined
    assert "(Sådan gør du)".encode("cp1252") in joined
    assert "Mestring \\(forældre\\)".encode("cp1252") in joined  # parenteser escapes
    xref = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert pdf[xref:xref + 4] == b"xref"


def test_rate_limit_on_code_attempts(client, org):
    good = make_code(client, org)
    for _ in range(5):
        assert client.post("/api/respondent/access-code/verify", json={"code": "AAAA-BBBB-CCCC"}).status_code == 400
    r = client.post("/api/respondent/access-code/verify", json={"code": good})
    assert r.status_code == 429 and "Retry-After" in r.headers
    with get_engine().connect() as c:
        buckets = [b for (b,) in c.execute(text(f"SELECT bucket FROM {qualified('qa_identity', 'rate_limits')}"))]
    assert all("testclient" not in b for b in buckets), "rå IP må ikke gemmes"


def test_csrf_and_mfa_enforced(client, org):
    adm = org["admin"]
    assert client.post(f"/api/admin/tenants/{org['tenant']}/units", json={"name": "X", "unitType": "other"}).status_code == 403
    client.post("/api/admin/auth/logout", json={}, headers=H(org["csrf"]))
    r = client.post("/api/admin/auth/login", json={"username": adm["username"], "password": adm["password"]})
    assert r.status_code == 200
    assert client.get("/api/admin/tenants").status_code == 401  # MFA mangler
    r = client.post("/api/admin/auth/mfa/verify", json={"code": "000000"}, headers=H(r.json()["csrfToken"]))
    assert r.status_code == 401


def test_cross_site_and_content_type_rejected(client):
    assert client.get("/api/admin/auth/me", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    r = client.post("/api/respondent/access-code/verify", content="code=x",
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415
    r = client.post("/api/respondent/access-code/verify", json={"code": "ABCDEFGHJK"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_tenant_isolation(client, org):
    other_t = make_tenant("Anden kommune")
    other = make_admin("org.other", [{"role_code": "org_admin", "tenant_id": other_t, "can_export": True}])
    csrf = login(client, other)
    t = org["tenant"]
    assert client.get(f"/api/admin/tenants/{t}/units").status_code == 404
    assert client.get(f"/api/admin/surveys?tenantId={t}").status_code == 404
    assert client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={org['sv']}").status_code == 404
    assert client.get(f"/api/admin/surveys/versions/{org['sv']}").status_code == 404
    issue_codes(client, csrf, org["sv"], {org["units"]["school"]: 1}, expect=404)
    r = client.post("/api/admin/exports", json={"tenantId": t, "format": "long_csv",
                                                "filters": {"surveyVersionId": org["sv"]}}, headers=H(csrf))
    assert r.status_code == 404
    r = client.post("/api/admin/analyses", json={"tenantId": t, "kind": "screening",
                                                 "filters": {"surveyVersionId": org["sv"]}}, headers=H(csrf))
    assert r.status_code == 404
    # andens tenant-id i eget dashboard-kald med egen tenant men fremmed survey version
    assert client.get(f"/api/admin/dashboard?tenantId={other_t}&surveyVersionId={org['sv']}").status_code == 404
    assert [x["id"] for x in client.get("/api/admin/tenants").json()] == [other_t]


def test_unit_admin_scope_and_export_right(client, org):
    ua = make_admin("unit.a", [{"role_code": "unit_admin", "tenant_id": org["tenant"], "unit_id": org["units"]["daycare"]}])
    csrf = login(client, ua)
    units = client.get(f"/api/admin/tenants/{org['tenant']}/units").json()
    assert [u["id"] for u in units] == [org["units"]["daycare"]]
    assert client.post(f"/api/admin/tenants/{org['tenant']}/units", json={"name": "Y", "unitType": "other"},
                       headers=H(csrf)).status_code == 404
    issue_codes(client, csrf, org["sv"], {org["units"]["school"]: 1}, expect=404)
    issue_codes(client, csrf, org["sv"], {org["units"]["daycare"]: 1})
    r = client.post("/api/admin/exports", json={"tenantId": org["tenant"], "format": "report_html",
                                                "filters": {"surveyVersionId": org["sv"]}}, headers=H(csrf))
    assert r.status_code == 403


def test_system_admin_cannot_read_responses(client, org):
    sa = make_admin("sys.admin", [{"role_code": "system_admin"}])
    login(client, sa)
    assert client.get(f"/api/admin/dashboard?tenantId={org['tenant']}&surveyVersionId={org['sv']}").status_code == 404
    assert client.get("/api/admin/audit/verify").json()["ok"] is True


def test_dashboard_suppression_and_stats(client, org):
    t, sv, u = org["tenant"], org["sv"], org["units"]
    insert_responses(t, u["daycare"], sv, 6, seed=1)
    d = client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={sv}").json()
    assert d["suppressed"] is True and d.get("n") is None
    insert_responses(t, u["daycare"], sv, 20, seed=2)
    insert_responses(t, u["school"], sv, 4, seed=3, shift=-0.6)
    d = client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={sv}").json()
    assert d["n"] == 30
    p = {x["subscale"]: x for x in d["profile"]}
    assert p["self"]["nValid"] == 30 and p["self"]["ci95"][0] < p["self"]["mean"] < p["self"]["ci95"][1]
    units = {x["unitId"]: x for x in d["units"]}
    # skolen (n=4) undertrykkes, og dagtilbuddet sekundært (ellers kan skolen udledes af totalen)
    assert units[u["school"]]["suppressed"] and units[u["daycare"]]["suppressed"]
    school = next(r for r in d["setting"] if r["subscale"] == "self")["school"]
    assert school["suppressed"]
    # komplementregel: filter der efterlader en rest < k
    r = client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={sv}&bg=profession:laerer").json()
    assert r["suppressed"] or r["n"] >= 10


def test_export_and_analysis_reproducible(client, org):
    t, sv, u = org["tenant"], org["sv"], org["units"]
    insert_responses(t, u["daycare"], sv, 15, seed=4)
    insert_responses(t, u["school"], sv, 15, seed=5, shift=-0.5)
    body = {"tenantId": t, "format": "long_csv", "filters": {"surveyVersionId": sv}}
    r1 = client.post("/api/admin/exports", json=body, headers=H(org["csrf"]))
    r2 = client.post("/api/admin/exports", json=body, headers=H(org["csrf"]))
    assert r1.status_code == 200 and r1.headers["X-Data-SHA256"] == r2.headers["X-Data-SHA256"]
    csv = r1.text
    assert csv.splitlines()[0].startswith("response_id,unit_id,institution_id,unit_type,question_key")
    assert len(csv.splitlines()) == 30 * 120 + 1
    # analysekørsel på samme filtre -> samme datahash (protokollen reproducerer eksporten)
    r = client.post("/api/admin/analyses", json={"tenantId": t, "kind": "group_comparison",
                                                 "filters": {"surveyVersionId": sv}}, headers=H(org["csrf"]))
    assert r.status_code == 202
    from app.db import session_scope
    from app.worker import claim_one, process

    run = claim_one()
    process(run)
    res = client.get(f"/api/admin/analyses/{r.json()['id']}").json()
    assert res["status"] == "done", res
    assert res["dataSha256"] == r1.headers["X-Data-SHA256"]
    g = res["result"]["bySubscale"][0]
    assert g["welchAnova"]["p"] is not None and g["hedgesG"]["g"] is not None
    for fmt in ("wide_csv", "codebook_json", "protocol_json", "report_html"):
        rr = client.post("/api/admin/exports", json={**body, "format": fmt}, headers=H(org["csrf"]))
        assert rr.status_code == 200, (fmt, rr.text)
    _ = session_scope


def test_audit_chain_records_and_detects_tampering(client, org):
    make_code(client, org)
    with get_engine().connect() as c:
        actions = {a for (a,) in c.execute(text(f"SELECT action FROM {qualified('qa_audit', 'audit_events')}"))}
    assert {"survey.import", "survey.publish", "unit.create", "access_code.create"} <= actions
    assert audit.verify_chain()["ok"]
    with get_engine().begin() as c:  # migreringsbrugeren kan; api-brugeren kan ikke (DB-grants)
        c.execute(text(f"UPDATE {qualified('qa_audit', 'audit_events')} SET action='tampered' ORDER BY id LIMIT 1"))
    assert audit.verify_chain()["ok"] is False


def test_system_admin_deletes_tenant_with_all_data(client, org):
    import uuid

    from app.db import session_scope
    from app.models import AccessCode, OrganizationUnit, Response, SurveyVersion, Tenant, User

    t = org["tenant"]
    insert_responses(t, org["units"]["school"], org["sv"], 5)
    issue_codes(client, org["csrf"], org["sv"], {org["units"]["school"]: 1})
    # Bruger med roller i en anden tenant skal overleve; org-admin uden andre roller fjernes
    keep_t = make_tenant(f"Bliver {uuid.uuid4().hex[:6]}")
    multi = make_admin(f"multi.{uuid.uuid4().hex[:6]}", [{"role_code": "org_admin", "tenant_id": t},
                                                         {"role_code": "org_admin", "tenant_id": keep_t}])
    # Org-admin må ikke slette tenants
    assert client.post(f"/api/admin/tenants/{t}/delete", json={"confirmName": "x"},
                       headers=H(org["csrf"])).status_code == 403

    sa = make_admin(f"sys.{uuid.uuid4().hex[:6]}", [{"role_code": "system_admin"}])
    csrf = login(client, sa)
    with session_scope() as db:
        name = db.get(Tenant, t).name
    assert client.post(f"/api/admin/tenants/{t}/delete", json={"confirmName": "forkert"},
                       headers=H(csrf)).status_code == 422
    r = client.post(f"/api/admin/tenants/{t}/delete", json={"confirmName": name}, headers=H(csrf))
    assert r.status_code == 200, r.text
    assert r.json()["deleted"]["responses"] == 5

    with session_scope() as db:
        assert db.get(Tenant, t) is None
        assert db.query(OrganizationUnit).filter_by(tenant_id=t).count() == 0
        assert db.query(SurveyVersion).filter_by(tenant_id=t).count() == 0
        assert db.query(Response).filter_by(tenant_id=t).count() == 0
        assert db.query(AccessCode).filter_by(tenant_id=t).count() == 0
        assert db.get(User, org["admin"]["id"]) is None
        assert db.get(User, multi["id"]) is not None
        assert db.get(Tenant, keep_t) is not None
    with get_engine().connect() as c:  # auditloggen bevares og registrerer sletningen
        n = c.execute(text(f"SELECT COUNT(*) FROM {qualified('qa_audit', 'audit_events')} "
                           "WHERE action='tenant.delete' AND tenant_id=:t"), {"t": t}).scalar()
    assert n == 1
    assert client.post(f"/api/admin/tenants/{t}/delete", json={"confirmName": name},
                       headers=H(csrf)).status_code == 404


def test_published_version_still_immutable_without_tenant_purge(client, org):
    from app.db import session_scope
    from app.models import Question, SurveyVersion

    with pytest.raises(Exception, match="immutable"):
        with session_scope() as db:
            db.query(Question).filter_by(survey_version_id=org["sv"]).delete()
    with pytest.raises(Exception, match="immutable"):
        with session_scope() as db:
            db.query(SurveyVersion).filter_by(id=org["sv"]).delete()


def test_institution_hierarchy_and_dashboard_levels(client, org):
    t, csrf, school = org["tenant"], org["csrf"], org["units"]["school"]

    def mk(**body):
        return client.post(f"/api/admin/tenants/{t}/units", json=body, headers=H(csrf))

    a = mk(name="3.A", parentId=school)
    assert a.status_code == 201 and a.json()["unitType"] == "school" and a.json()["level"] == "subunit"
    b = mk(name="3.B", parentId=school).json()["id"]
    a = a.json()["id"]
    assert mk(name="3.A", parentId=school).status_code == 409          # unik pr. institution
    other = mk(name="Østskolen", unitType="school").json()["id"]
    assert mk(name="3.A", parentId=other).status_code == 201          # samme klassenavn på anden skole
    assert mk(name="Gruppe 1", parentId=a).status_code == 422          # kun to niveauer
    assert mk(name="Uden type").status_code == 422                     # institution kræver type
    units = {u["id"]: u for u in client.get(f"/api/admin/tenants/{t}/units").json()}
    assert units[a]["parentName"] == units[school]["name"]

    insert_responses(t, a, org["sv"], 12, seed=1)
    insert_responses(t, b, org["sv"], 12, seed=2)
    insert_responses(t, org["units"]["daycare"], org["sv"], 12, seed=3)

    d = client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={org['sv']}").json()
    assert d["comparisonLevel"] == "institution"
    rows = {u["unitId"]: u for u in d["units"]}
    assert set(rows) == {school, org["units"]["daycare"]} and rows[school]["n"] == 24

    d = client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={org['sv']}&unitIds={school}").json()
    assert d["n"] == 24 and d["comparisonLevel"] == "subunit" and d["institution"]["id"] == school
    assert [u["name"] for u in d["units"]] == ["3.A", "3.B"]

    # Afdelingsadmin for institutionen ser dens klasser; admin for én klasse ser kun den
    ua = make_admin("unit.school", [{"role_code": "unit_admin", "tenant_id": t, "unit_id": school}])
    login(client, ua)
    assert {u["id"] for u in client.get(f"/api/admin/tenants/{t}/units").json()} == {school, a, b}
    assert client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={org['sv']}").json()["n"] == 24
    ca = make_admin("unit.class", [{"role_code": "unit_admin", "tenant_id": t, "unit_id": a}])
    login(client, ca)
    assert {u["id"] for u in client.get(f"/api/admin/tenants/{t}/units").json()} == {a}
    d = client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={org['sv']}&unitIds={school}").json()
    assert d["n"] == 12


def test_data_subject_rights_export_and_erase(client, org):
    """GDPR art. 15/17/20: den personlige kode virker også efter afslutning og kan slette alt."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    code = make_code(client, org)
    with TestClient(create_app(), base_url="https://testserver") as rc:
        start = respondent_start(rc, code)
        rid, key = start["responseId"], code
        order = rc.get(f"/api/respondent/sessions/{rid}/next").json()["order"]
        q = order[0]["questionId"]
        rc.post(f"/api/respondent/sessions/{rid}/shown", json={"positions": [0, 1]})
        rc.put(f"/api/respondent/sessions/{rid}/answers/{q}", json={"value": 4, "seq": 1})
        assert rc.post(f"/api/respondent/sessions/{rid}/complete", json={}).status_code == 200

    with TestClient(create_app(), base_url="https://testserver") as other:  # ingen session/cookie
        # forkert kode afvises generisk
        assert other.post("/api/respondent/rights/export", json={"key": "WRONG-WRONG-WRONG"}).status_code == 400
        # afsluttet besvarelse kan ikke fortsættes, men kan eksporteres med adgangskoden
        v = other.post("/api/respondent/access-code/verify", json={"code": key}).json()
        assert other.post("/api/respondent/continue", json={"ticket": v["ticket"]}).status_code == 409
        r = other.post("/api/respondent/rights/export", json={"key": key})
        assert r.status_code == 200
        d = r.json()
        assert d["responseId"] == rid and d["status"] == "completed"
        assert [a["value"] for a in d["answers"]] == [4, None]  # besvaret + vist-men-ubesvaret
        assert not any(k in d for k in ("ip", "email", "name", "seed"))
        # sletning fjerner besvarelsen og koden
        assert other.post("/api/respondent/rights/erase", json={"key": key}).json() == {"erased": True}
        assert other.post("/api/respondent/rights/export", json={"key": key}).status_code == 400

    with get_engine().connect() as c:
        n = c.execute(text(f"SELECT COUNT(*) FROM {qualified('qa_data', 'responses')} WHERE id=:r"), {"r": rid}).scalar()
        a = c.execute(text(f"SELECT COUNT(*) FROM {qualified('qa_data', 'answers')} WHERE response_id=:r"), {"r": rid}).scalar()
        ev = c.execute(text(f"SELECT COUNT(*) FROM {qualified('qa_audit', 'audit_events')} WHERE action='respondent.erased' "
                            "AND target_id=:r"), {"r": rid}).scalar()
    assert n == 0 and a == 0 and ev == 1


def test_public_legal_info_has_no_secrets(client):
    r = client.get("/api/public/legal-info")
    assert r.status_code == 200
    body = r.text.lower()
    assert "pepper" not in body and "password" not in body and "key" not in r.json()
    assert {c["name"] for c in r.json()["cookies"]} == {"__Host-qa_resp", "__Host-qa_admin"}


def test_delete_subunit_keeps_responses_at_institution(client, org):
    t, csrf, school = org["tenant"], org["csrf"], org["units"]["school"]
    a = client.post(f"/api/admin/tenants/{t}/units", json={"name": "9.A", "parentId": school},
                    headers=H(csrf)).json()["id"]
    insert_responses(t, a, org["sv"], 12, seed=7)
    issue_codes(client, csrf, org["sv"], {a: 1})
    code = next(c["id"] for c in client.get(f"/api/admin/access-codes?tenantId={t}").json() if c["unitId"] == a)
    ca = make_admin("unit.9a", [{"role_code": "unit_admin", "tenant_id": t, "unit_id": a}])

    # Institutioner kan ikke fjernes via dette endpoint
    assert client.post(f"/api/admin/tenants/{t}/units/{school}/delete", json={}, headers=H(csrf)).status_code == 422
    r = client.post(f"/api/admin/tenants/{t}/units/{a}/delete", json={}, headers=H(csrf))
    assert r.status_code == 200, r.text
    assert r.json()["responsesMoved"] == 12 and r.json()["accessCodesDisabled"] == 1
    assert r.json()["userScopesRemoved"] == 1
    assert a not in {u["id"] for u in client.get(f"/api/admin/tenants/{t}/units").json()}
    codes = {c["id"]: c for c in client.get(f"/api/admin/access-codes?tenantId={t}").json()}
    assert codes[code]["unitId"] == school and codes[code]["status"] == "disabled"
    d = client.get(f"/api/admin/dashboard?tenantId={t}&surveyVersionId={org['sv']}&unitIds={school}").json()
    assert d["n"] == 12
    assert client.post(f"/api/admin/tenants/{t}/units/{a}/delete", json={}, headers=H(csrf)).status_code == 404
    from app.db import session_scope
    from app.models import UserScope

    with session_scope() as db:
        assert db.query(UserScope).filter_by(user_id=ca["id"]).count() == 0


def test_survey_assignment_controls_code_issuing(client, org):
    t, csrf, school, daycare = org["tenant"], org["csrf"], org["units"]["school"], org["units"]["daycare"]
    url = f"/api/admin/surveys/{org['survey']}/assignments"
    cls = client.post(f"/api/admin/tenants/{t}/units", json={"name": "5.B", "parentId": school},
                      headers=H(csrf)).json()["id"]
    # Fratag skolen: spørgeskemaet bliver i biblioteket, men der kan ikke udstedes koder til skolen/klassen
    assert client.put(url, json={"unitIds": [daycare]}, headers=H(csrf)).json()["assignedUnitIds"] == [daycare]
    surveys = client.get(f"/api/admin/surveys?tenantId={t}").json()
    assert len(surveys) == 1 and surveys[0]["assignedUnitIds"] == [daycare]
    r = issue_codes(client, csrf, org["sv"], {cls: 1}, expect=422)
    assert "5.B" in r.json()["detail"]
    issue_codes(client, csrf, org["sv"], {daycare: 1})
    # Kun institutioner i samme tenant kan tildeles
    assert client.put(url, json={"unitIds": [cls]}, headers=H(csrf)).status_code == 422
    # Tildel igen: koder til klassen virker (arves fra institutionen)
    assert client.put(url, json={"unitIds": [daycare, school]}, headers=H(csrf)).status_code == 200
    issue_codes(client, csrf, org["sv"], {cls: 2})
    # Afdelingsadmin kan ikke ændre tildelinger
    ua = make_admin("unit.assign", [{"role_code": "unit_admin", "tenant_id": t, "unit_id": school}])
    csrf2 = login(client, ua)
    assert client.put(url, json={"unitIds": []}, headers=H(csrf2)).status_code == 404


def test_frontend_assets_are_versioned_for_cache_busting(client):
    """CDN'er kan overskrive Cache-Control; versionerede URL'er sikrer, at en deploy slår igennem."""
    import re

    html = client.get("/")
    assert html.headers["cache-control"] == "no-store"
    m = re.search(r'src="/js/respondent\.js\?v=([0-9a-f]{12})"', html.text)
    assert m, html.text[:500]
    v = m[1]
    assert f'href="/css/app.css?v={v}"' in html.text
    js = client.get(f"/js/respondent.js?v={v}")
    assert js.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert f"from './api.js?v={v}'" in js.text and f"import './chrome.js?v={v}'" in js.text
    assert "javascript" in js.headers["content-type"]
    css = client.get(f"/css/app.css?v={v}")
    assert f'url("/fonts/inter-latin.woff2?v={v}")' in css.text
    # Uversioneret eller forældet version revalideres altid
    assert client.get("/js/respondent.js").headers["cache-control"] == "no-cache"
    assert client.get("/js/respondent.js?v=000000000000").headers["cache-control"] == "no-cache"
    assert client.get("/admin/").text.count(f"?v={v}") >= 2


def test_codes_are_grouped_in_batches_with_unit_blocks(client, org):
    t, csrf = org["tenant"], org["csrf"]
    school, daycare = org["units"]["school"], org["units"]["daycare"]
    # Bestilt rækkefølge: skole først, så dagtilbud
    issue_codes(client, csrf, org["sv"], {school: 3, daycare: 2})
    issue_codes(client, csrf, org["sv"], {daycare: 1})
    codes = client.get(f"/api/admin/access-codes?tenantId={t}").json()
    batches = {}
    for c in codes:
        batches.setdefault(c["batchId"], []).append(c)
    assert len(batches) == 2
    big = next(b for b in batches.values() if len(b) == 5)
    assert sorted((c["batchPos"], c["seqNo"], c["unitId"]) for c in big) == [
        (0, 1, school), (0, 2, school), (0, 3, school), (1, 1, daycare), (1, 2, daycare)]
    bid = big[0]["batchId"]
    # Deaktivér én afdelingsblok, derefter resten af bestillingen
    r = client.post(f"/api/admin/access-codes/batches/{bid}/disable", json={"tenantId": t, "unitId": school},
                    headers=H(csrf))
    assert r.json() == {"disabled": 3}
    r = client.post(f"/api/admin/access-codes/batches/{bid}/disable", json={"tenantId": t}, headers=H(csrf))
    assert r.json() == {"disabled": 2}
    codes = client.get(f"/api/admin/access-codes?tenantId={t}").json()
    assert sum(c["status"] == "active" for c in codes) == 1  # den anden bestilling er urørt
