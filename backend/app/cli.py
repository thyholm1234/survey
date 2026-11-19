"""Administrations-CLI.

  python -m app.cli create-sysadmin <brugernavn>
  python -m app.cli reset-password <brugernavn>   # ny engangsadgangskode (skal skiftes ved login)
  python -m app.cli seed-demo            # SYNTETISK demo-tenant med data
  python -m app.cli export-synthetic     # skriver syntetisk long-CSV til stdout
  python -m app.cli verify-audit
"""
from __future__ import annotations

import json
import math
import pathlib
import random
import secrets
import sys
from datetime import timedelta

from sqlalchemy import select

from . import audit
from .db import session_scope
from .models import (
    AccessCode,
    Answer,
    OrganizationUnit,
    PresentationEvent,
    Question,
    Response,
    Scenario,
    Subscale,
    Domain,
    Tenant,
    User,
    UserScope,
    utcnow,
)
from .security import argon2_hash, code_lookup, generate_code, normalize_code
from .services import survey_import
from .services.randomization import Item, build_plan

DEMO_TENANT = "SYNTETISK DEMO – Eksempel Kommune"
SYNTH_SEED = 20241119
SAMPLE = pathlib.Path(__file__).resolve().parents[1] / "data" / "sample_almenramme_survey.json"


def _user(db, username: str, scopes: list[UserScope]) -> tuple[User, str]:
    pw = secrets.token_urlsafe(18)
    u = User(username=username, password_hash=argon2_hash(pw), must_change_password=True)
    db.add(u)
    db.flush()
    for sc in scopes:
        sc.user_id = u.id
        db.add(sc)
    return u, pw


def create_sysadmin(username: str) -> None:
    with session_scope() as db:
        if db.scalar(select(User).where(User.username == username)):
            sys.exit("Brugeren findes allerede.")
        u, pw = _user(db, username, [UserScope(role_code="system_admin")])
    audit.record("user.create", actor_type="system", target_type="user", target_id=u.id,
                 details={"role": "system_admin", "via": "cli"})
    print(f"Systemadmin oprettet: {username}\nEngangsadgangskode: {pw}\n"
          "Opsæt TOTP og skift adgangskode ved første login.")


def reset_password(username: str) -> None:
    with session_scope() as db:
        u = db.scalar(select(User).where(User.username == username))
        if u is None:
            sys.exit("Brugeren findes ikke.")
        pw = secrets.token_urlsafe(18)
        u.password_hash = argon2_hash(pw)
        u.must_change_password = True
        u.failed_logins = 0
        u.locked_until = None
        uid = u.id
    audit.record("user.password_reset", actor_type="system", target_type="user", target_id=uid,
                 details={"via": "cli"})
    print(f"Ny engangsadgangskode for {username}: {pw}\nSkal skiftes ved næste login.")


def seed_demo() -> None:
    rng = random.Random(SYNTH_SEED)
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    errors = survey_import.validate(doc)
    if errors:
        sys.exit("Eksempel-JSON er ugyldig: " + "; ".join(errors[:5]))
    creds = []
    with session_scope() as db:
        if db.scalar(select(Tenant).where(Tenant.name == DEMO_TENANT)):
            sys.exit("Demo-tenant findes allerede.")
        tenant = Tenant(name=DEMO_TENANT, min_cell_size=10, retention_months=24,
                        data_controller="SYNTETISK – ingen dataansvarlig", contact="demo@example.invalid")
        db.add(tenant)
        db.flush()
        units = []
        for name, typ in [("Dagtilbud Solsikken", "daycare"), ("Dagtilbud Mælkebøtten", "daycare"),
                          ("Dagtilbud Skovbrynet", "daycare"), ("Skole Nord – indskoling", "school"),
                          ("Skole Nord – mellemtrin", "school"), ("Skole Syd – indskoling", "school")]:
            u = OrganizationUnit(tenant_id=tenant.id, name=name, unit_type=typ)
            db.add(u)
            units.append(u)
        db.flush()
        org_user, org_pw = _user(db, "demo.org", [UserScope(role_code="org_admin", tenant_id=tenant.id,
                                                            can_export=True)])
        unit_user, unit_pw = _user(db, "demo.unit", [UserScope(role_code="unit_admin", tenant_id=tenant.id,
                                                               unit_id=units[0].id)])
        creds += [("demo.org", org_pw), ("demo.unit", unit_pw)]
        sv = survey_import.store_draft(db, tenant.id, org_user.id, doc)
        survey_import.publish(db, sv, org_user.id)

        codes = []
        now = utcnow()
        for u in units:
            plain = generate_code()
            norm = normalize_code(plain)
            c = AccessCode(tenant_id=tenant.id, unit_id=u.id, survey_version_id=sv.id,
                           lookup_hmac=code_lookup(norm), code_hash=argon2_hash(norm), label="Demo",
                           valid_from=now - timedelta(days=1), valid_to=now + timedelta(days=90),
                           created_by=org_user.id)
            db.add(c)
            codes.append((u.name, plain, c))
        db.flush()

        # --- Syntetiske besvarelser (TYDELIGT MARKERET is_synthetic=1) --------------
        qrows = db.execute(
            select(Question.id, Question.question_key, Subscale.code, Domain.code, Question.reverse_scored)
            .join(Subscale, Subscale.id == Question.subscale_id)
            .join(Scenario, Scenario.id == Question.scenario_id)
            .join(Domain, Domain.id == Scenario.domain_id)
            .where(Question.survey_version_id == sv.id)
        ).all()
        qid = {r[1]: r[0] for r in qrows}
        reverse = {r[1] for r in qrows if r[4]}
        items = [Item(r[1], r[2], r[3]) for r in qrows]
        perspectives = [p["code"] for p in doc["perspectives"]]
        dom_eff = {d["code"]: rng.gauss(0, 0.35) for d in doc["domains"]}
        base = {("daycare", "self"): 4.3, ("daycare", "team"): 4.1, ("daycare", "frame"): 3.4,
                ("daycare", "belong"): 4.6, ("daycare", "expect"): 3.6, ("school", "self"): 3.9,
                ("school", "team"): 3.7, ("school", "frame"): 3.0, ("school", "belong"): 4.2,
                ("school", "expect"): 3.3}
        bgvars = doc["backgroundVariables"]
        for (uname, _plain, code), u in zip(codes, units):
            unit_eff = rng.gauss(0, 0.25)
            usage: dict = {}
            n_resp = rng.randint(22, 30)
            for _ in range(n_resp):
                seed = rng.getrandbits(63)
                plan = build_plan(items, perspectives, doc["fixedLastPerspective"], usage, seed)
                usage[tuple(plan.block_order)] = usage.get(tuple(plan.block_order), 0) + 1
                prof = rng.choice(["paedagog", "paed_assistent", "leder"] if u.unit_type == "daycare"
                                  else ["laerer", "paedagog", "leder"])
                bg = {"profession": prof, "experience": rng.choice(["0-2", "3-5", "6-10", "11plus"]),
                      "special_training": rng.choice(["yes", "no", "no"]),
                      "work_area": rng.choice(["0-2", "3-5"] if u.unit_type == "daycare"
                                              else ["indskoling", "mellemtrin", "sfo"])}
                assert all(b["code"] in bg for b in bgvars)
                start = now - timedelta(days=rng.randint(1, 20), minutes=rng.randint(0, 600))
                theta = {p: base[(u.unit_type, p)] + unit_eff + rng.gauss(0, 0.7) for p in perspectives}
                speed = rng.lognormvariate(0, 0.3)
                incomplete = rng.random() < 0.06
                stop_at = rng.randint(20, 120) if incomplete else len(plan.order)
                straight = rng.random() < 0.03
                r = Response(tenant_id=tenant.id, unit_id=u.id, unit_type=u.unit_type,
                             survey_version_id=sv.id, group_tags=[], background=bg,
                             started_at=start, last_activity_at=start, seed=seed,
                             block_order=plan.block_order, presentation_order=[i.question_id for i in plan.order],
                             randomization_meta=plan.meta, browser_class=rng.choice(["chromium", "firefox", "safari"]),
                             screen_class=rng.choice(["s", "m", "l"]), app_version="synthetic",
                             is_synthetic=True)
                db.add(r)
                db.flush()
                t = start
                block_counts: dict[int, int] = {}
                for pos, it in enumerate(plan.order[:stop_at]):
                    bi = plan.block_order.index(it.perspective)
                    bp = block_counts.get(bi, 0)
                    block_counts[bi] = bp + 1
                    rt = int(rng.lognormvariate(math.log(6500), 0.45) * speed)
                    shown = t
                    t = t + timedelta(milliseconds=rt)
                    u_ = rng.random()
                    value, miss, answered = None, None, t
                    if u_ < 0.03:
                        miss = "CANNOT_ASSESS"
                    elif u_ < 0.045:
                        answered, rt = None, None
                    else:
                        x = 4 if straight else theta[it.perspective] + dom_eff[it.domain] + rng.gauss(0, 0.8)
                        value = int(min(6, max(1, round(x))))
                        if it.question_id in reverse:  # negativt formuleret: rå værdi spejles
                            value = 7 - value
                    db.add(Answer(response_id=r.id, question_id=qid[it.question_id], value=value,
                                  missing_code=miss, global_position=pos, block_index=bi, block_position=bp,
                                  first_shown_at=shown, answered_at=answered, rt_ms=rt,
                                  change_count=1 if rng.random() < 0.02 else 0, last_seq=1))
                r.last_activity_at = t
                if not incomplete:
                    r.status, r.completed_at = "completed", t
                    code.completions_count += 1
                code.starts_count += 1
                db.add(PresentationEvent(response_id=r.id, event_type="start", at=start))
        tenant_id = tenant.id
    audit.record("demo.seed", actor_type="system", tenant_id=tenant_id, details={"synthetic": True})
    print("=== SYNTETISK DEMO oprettet ===")
    print("Admin-brugere (engangsadgangskoder – opsæt TOTP og skift ved første login):")
    for u, p in creds:
        print(f"  {u}: {p}")
    print("Respondentkoder (vises kun nu):")
    for uname, plain, _ in codes:
        print(f"  {uname}: {plain}")


def export_synthetic() -> None:
    from .routers.admin_exports import long_csv
    from .services import analysis_data

    with session_scope() as db:
        t = db.scalar(select(Tenant).where(Tenant.name == DEMO_TENANT))
        if t is None:
            sys.exit("Ingen demo-tenant.")
        units = set(db.scalars(select(OrganizationUnit.id).where(OrganizationUnit.tenant_id == t.id)))
        from .models import SurveyVersion

        sv = db.scalar(select(SurveyVersion).where(SurveyVersion.tenant_id == t.id))
        ds = analysis_data.load(db, t.id, units, analysis_data.Filters(surveyVersionId=sv.id))
        sys.stdout.write("# SYNTETISK DATASÆT – genereret med seed %d – ikke rigtige besvarelser\n" % SYNTH_SEED)
        sys.stdout.write(long_csv(ds, sv.id))


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == "create-sysadmin" and len(argv) == 2:
        create_sysadmin(argv[1].strip().lower())
    elif cmd == "reset-password" and len(argv) == 2:
        reset_password(argv[1].strip().lower())
    elif cmd == "seed-demo":
        seed_demo()
    elif cmd == "export-synthetic":
        export_synthetic()
    elif cmd == "verify-audit":
        print(json.dumps(audit.verify_chain()))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
