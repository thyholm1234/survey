"""Respondent-flow (spec §3, §7, §14)."""
from __future__ import annotations

import json
import secrets
from collections import Counter
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import ratelimit
from ..config import get_settings
from ..db import get_db
from ..deps import RESP_COOKIE, clear_cookie, respondent, set_cookie
from ..models import (
    AccessCode,
    Answer,
    CodeTicket,
    Domain,
    OrganizationUnit,
    PresentationEvent,
    Question,
    Response as ResponseRow,
    ResponseScale,
    ResponseSession,
    ResumeKey,
    Scenario,
    Subscale,
    SurveyVersion,
    Tenant,
    utcnow,
)
from ..security import (
    RESUME_LENGTH,
    argon2_hash,
    argon2_verify,
    code_lookup,
    generate_code,
    new_token,
    normalize_code,
    token_digest,
)
from ..services.randomization import Item, build_plan

router = APIRouter(prefix="/api/respondent", tags=["respondent"])

GENERIC_CODE_ERROR = "Koden er ugyldig, udløbet eller ikke længere aktiv."
TICKET_TTL = 600


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CodeIn(Strict):
    code: str = Field(min_length=6, max_length=40)


class ClientMeta(Strict):
    browserClass: Literal["chromium", "firefox", "safari", "other"] = "other"
    screenClass: Literal["s", "m", "l"] = "m"


class StartIn(Strict):
    ticket: str = Field(min_length=20, max_length=100)
    consent: Literal[True]
    background: dict[str, str | None] = Field(default_factory=dict, max_length=10)
    client: ClientMeta = Field(default_factory=ClientMeta)


class ResumeIn(Strict):
    resumeKey: str = Field(min_length=10, max_length=40)


class ShownIn(Strict):
    positions: list[int] = Field(min_length=1, max_length=3)


class AnswerIn(Strict):
    value: int | None = Field(default=None, ge=0, le=11)
    missingCode: Literal["CANNOT_ASSESS"] | None = None
    seq: int = Field(ge=1, le=1_000_000)
    viaBack: bool = False


# ---------------------------------------------------------------------------


def _code_valid(code: AccessCode | None, db: Session) -> tuple[SurveyVersion, Tenant] | None:
    now = utcnow()
    if code is None or code.status != "active" or not (code.valid_from <= now < code.valid_to):
        return None
    if code.max_starts is not None and code.starts_count >= code.max_starts:
        return None
    if code.max_completions is not None and code.completions_count >= code.max_completions:
        return None
    sv = db.get(SurveyVersion, code.survey_version_id)
    tenant = db.get(Tenant, code.tenant_id)
    unit = db.get(OrganizationUnit, code.unit_id)
    if sv is None or sv.status != "published" or tenant is None or tenant.status != "active":
        return None
    if unit is None or unit.status != "active":
        return None
    return sv, tenant


def _intro(sv: SurveyVersion, tenant: Tenant, db: Session) -> dict:
    doc = json.loads(sv.source_json)
    info = dict(doc.get("respondentInfo", {}))
    if tenant.data_controller:
        info["dataController"] = tenant.data_controller
    if tenant.contact:
        info["contact"] = tenant.contact
    info["retention"] = info.get("retention") or (
        f"Rå besvarelser opbevares i op til {tenant.retention_months} måneder."
    )
    n_q = db.query(Question).filter(Question.survey_version_id == sv.id).count()
    return {
        "title": doc["title"],
        "info": info,
        "backgroundVariables": doc.get("backgroundVariables", []),
        "questions": n_q,
        "estimatedMinutes": max(1, round(n_q * 9 / 60)),
    }


@router.post("/access-code/verify")
def verify_code(body: CodeIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    bucket = ratelimit.bucket_for(request, "code")
    ratelimit.check_blocked(bucket, s.rl_code_attempts)
    normalized = normalize_code(body.code)
    code = db.scalar(select(AccessCode).where(AccessCode.lookup_hmac == code_lookup(normalized)))
    # Argon2-verifikation altid (dummy-hash hvis ukendt) for ensartet svartid
    ok = argon2_verify(code.code_hash if code else None, normalized)
    valid = _code_valid(code, db) if ok else None
    if not valid:
        ratelimit.hit(bucket, s.rl_code_attempts, s.rl_code_window)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, GENERIC_CODE_ERROR)
    sv, tenant = valid
    ticket = new_token()
    db.add(CodeTicket(id=token_digest(ticket), access_code_id=code.id,
                      expires_at=utcnow() + timedelta(seconds=TICKET_TTL)))
    return {"ticket": ticket, "expiresIn": TICKET_TTL, **_intro(sv, tenant, db)}


def _validate_background(doc: dict, given: dict[str, str | None]) -> dict[str, str | None]:
    allowed = {b["code"]: {o["code"] for o in b["options"]} for b in doc.get("backgroundVariables", [])}
    out: dict[str, str | None] = {}
    for k, v in given.items():
        if k not in allowed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ukendt baggrundsvariabel.")
        if v is not None and v not in allowed[k]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldig svarmulighed.")
        out[k] = v
    return out


def _new_session(db: Session, response: Response, response_id: str, code_id: str) -> None:
    s = get_settings()
    token = new_token()
    now = utcnow()
    db.add(ResponseSession(
        id=token_digest(token), response_id=response_id, access_code_id=code_id,
        created_at=now, last_seen_at=now,
        absolute_expires_at=now + timedelta(seconds=s.respondent_session_max),
    ))
    set_cookie(response, RESP_COOKIE, token, s.respondent_session_max)


@router.post("/sessions", status_code=201)
def start_session(body: StartIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    ticket = db.get(CodeTicket, token_digest(body.ticket), with_for_update=True)
    if ticket is None or ticket.used or ticket.expires_at <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Adgangen er udløbet. Indtast koden igen.")
    ticket.used = True
    code = db.get(AccessCode, ticket.access_code_id)
    valid = _code_valid(code, db)
    if not valid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, GENERIC_CODE_ERROR)
    sv, _tenant = valid
    # Atomisk optælling (beskytter max_starts mod race conditions)
    res = db.execute(
        update(AccessCode)
        .where(AccessCode.id == code.id)
        .where((AccessCode.max_starts.is_(None)) | (AccessCode.starts_count < AccessCode.max_starts))
        .values(starts_count=AccessCode.starts_count + 1)
    )
    if res.rowcount != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, GENERIC_CODE_ERROR)

    doc = json.loads(sv.source_json)
    background = _validate_background(doc, body.background)
    unit = db.get(OrganizationUnit, code.unit_id)

    rows = db.execute(
        select(Question.id, Question.question_key, Subscale.code, Domain.code)
        .join(Subscale, Subscale.id == Question.subscale_id)
        .join(Scenario, Scenario.id == Question.scenario_id)
        .join(Domain, Domain.id == Scenario.domain_id)
        .where(Question.survey_version_id == sv.id)
        .order_by(Question.position)
    ).all()
    items = [Item(question_id=r[1], perspective=r[2], domain=r[3]) for r in rows]
    perspectives = [p["code"] for p in doc["perspectives"]]
    usage: Counter = Counter()
    for (bo,) in db.execute(
        select(ResponseRow.block_order).where(
            ResponseRow.survey_version_id == sv.id, ResponseRow.unit_id == unit.id
        )
    ):
        usage[tuple(bo)] += 1
    seed = secrets.randbits(63)
    plan = build_plan(items, perspectives, doc.get("fixedLastPerspective"), usage, seed)

    now = utcnow()
    resp = ResponseRow(
        tenant_id=code.tenant_id, unit_id=unit.id, unit_type=unit.unit_type,
        survey_version_id=sv.id, group_tags=code.group_tags or [], background=background,
        started_at=now, last_activity_at=now, seed=seed, block_order=plan.block_order,
        presentation_order=[i.question_id for i in plan.order], randomization_meta=plan.meta,
        browser_class=body.client.browserClass, screen_class=body.client.screenClass,
        app_version=s.app_version,
    )
    db.add(resp)
    db.flush()
    db.add(PresentationEvent(response_id=resp.id, event_type="start"))

    resume_key = generate_code(RESUME_LENGTH)
    norm = normalize_code(resume_key)
    db.add(ResumeKey(
        response_id=resp.id, access_code_id=code.id, lookup_hmac=code_lookup(norm, "resume"),
        key_hash=argon2_hash(norm), expires_at=now + timedelta(days=s.resume_key_ttl_days),
    ))
    _new_session(db, response, resp.id, code.id)
    return {"responseId": resp.id, "resumeKey": resume_key}


@router.post("/resume")
def resume(body: ResumeIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    bucket = ratelimit.bucket_for(request, "resume")
    ratelimit.check_blocked(bucket, s.rl_code_attempts)
    norm = normalize_code(body.resumeKey)
    rk = db.scalar(select(ResumeKey).where(ResumeKey.lookup_hmac == code_lookup(norm, "resume")))
    ok = argon2_verify(rk.key_hash if rk else None, norm)
    resp = db.get(ResponseRow, rk.response_id) if ok and rk else None
    if not ok or rk is None or rk.expires_at <= utcnow() or resp is None or resp.status != "in_progress":
        ratelimit.hit(bucket, s.rl_code_attempts, s.rl_code_window)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Genoptagelseskoden er ugyldig eller udløbet.")
    # Tilbagekald tidligere sessioner for denne besvarelse
    db.execute(update(ResponseSession).where(ResponseSession.response_id == resp.id).values(revoked=True))
    _new_session(db, response, resp.id, rk.access_code_id)
    db.add(PresentationEvent(response_id=resp.id, event_type="resume"))
    return {"responseId": resp.id}


@router.get("/session")
def current_session(sess: ResponseSession = Depends(respondent)):
    return {"responseId": sess.response_id}


def _own(sess: ResponseSession, response_id: str, db: Session, lock: bool = False) -> ResponseRow:
    if not secrets.compare_digest(sess.response_id, response_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    resp = db.get(ResponseRow, response_id, with_for_update=lock)
    if resp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.")
    return resp


@router.get("/sessions/{response_id}/next")
def next_state(response_id: str, sess: ResponseSession = Depends(respondent), db: Session = Depends(get_db)):
    resp = _own(sess, response_id, db)
    sv = db.get(SurveyVersion, resp.survey_version_id)
    doc = json.loads(sv.source_json)
    scale = db.scalar(select(ResponseScale).where(ResponseScale.survey_version_id == sv.id))
    qrows = db.execute(
        select(Question.question_key, Question.text, Subscale.code, Scenario.behavior)
        .join(Subscale, Subscale.id == Question.subscale_id)
        .join(Scenario, Scenario.id == Question.scenario_id)
        .where(Question.survey_version_id == sv.id)
    ).all()
    qmap = {r[0]: r for r in qrows}
    qid_by_key = dict(db.execute(
        select(Question.question_key, Question.id).where(Question.survey_version_id == sv.id)
    ).all())
    key_by_id = {v: k for k, v in qid_by_key.items()}
    answers = {
        key_by_id[a.question_id]: a
        for a in db.scalars(select(Answer).where(Answer.response_id == resp.id))
    }
    order = []
    block_counts: Counter = Counter()
    for pos, key in enumerate(resp.presentation_order):
        q = qmap[key]
        bi = resp.block_order.index(q[2])
        a = answers.get(key)
        order.append({
            "position": pos, "questionId": key, "perspective": q[2], "blockIndex": bi,
            "blockPosition": block_counts[bi], "behavior": q[3], "text": q[1],
            "value": a.value if a else None, "missingCode": a.missing_code if a else None,
            "shown": a is not None, "seq": a.last_seq if a else 0,
        })
        block_counts[bi] += 1
    resume_pos = next(
        (o["position"] for o in order if o["value"] is None and o["missingCode"] is None), len(order)
    )
    return {
        "responseId": resp.id,
        "status": resp.status,
        "title": doc["title"],
        "scale": {
            "min": scale.min_value, "max": scale.max_value, "labels": scale.labels,
            "cannotAssessLabel": scale.cannot_assess_label,
        },
        "blocks": [
            {"perspective": p, **next(({"name": x["name"], "instruction": x.get("instruction")}
                                       for x in doc["perspectives"] if x["code"] == p), {})}
            for p in resp.block_order
        ],
        "order": order,
        "resumePosition": resume_pos,
    }


@router.post("/sessions/{response_id}/shown", status_code=204)
def shown(response_id: str, body: ShownIn, sess: ResponseSession = Depends(respondent),
          db: Session = Depends(get_db)):
    resp = _own(sess, response_id, db, lock=True)
    if resp.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Besvarelsen er afsluttet.")
    now = utcnow()
    keys = resp.presentation_order
    sv_id = resp.survey_version_id
    qrows = dict(db.execute(
        select(Question.question_key, Question.id).where(Question.survey_version_id == sv_id)
    ).all())
    sub_by_key = dict(db.execute(
        select(Question.question_key, Subscale.code).join(Subscale, Subscale.id == Question.subscale_id)
        .where(Question.survey_version_id == sv_id)
    ).all())
    existing = set(db.scalars(select(Answer.question_id).where(Answer.response_id == resp.id)))
    for pos in body.positions:
        if not 0 <= pos < len(keys):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ugyldig position.")
        key = keys[pos]
        qid = qrows[key]
        if qid in existing:
            continue
        bi = resp.block_order.index(sub_by_key[key])
        block_pos = sum(1 for k in keys[:pos] if sub_by_key[k] == sub_by_key[key])
        db.add(Answer(response_id=resp.id, question_id=qid, global_position=pos, block_index=bi,
                      block_position=block_pos, first_shown_at=now))
        db.add(PresentationEvent(response_id=resp.id, event_type="shown", question_id=key, position=pos))
        existing.add(qid)
    resp.last_activity_at = now
    return Response(status_code=204)


@router.put("/sessions/{response_id}/answers/{question_key}")
def put_answer(response_id: str, question_key: str, body: AnswerIn,
               sess: ResponseSession = Depends(respondent), db: Session = Depends(get_db)):
    resp = _own(sess, response_id, db, lock=True)
    if resp.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Besvarelsen er afsluttet.")
    if question_key not in resp.presentation_order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ukendt spørgsmål.")
    if body.value is not None and body.missingCode is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Angiv enten værdi eller missing-kode.")
    scale = db.scalar(select(ResponseScale).where(ResponseScale.survey_version_id == resp.survey_version_id))
    if body.value is not None and not scale.min_value <= body.value <= scale.max_value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Værdi uden for skalaen.")
    if body.missingCode and not scale.cannot_assess_label:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kan ikke vurdere er ikke tilladt.")
    qid = db.scalar(select(Question.id).where(
        Question.survey_version_id == resp.survey_version_id, Question.question_key == question_key))
    ans = db.scalar(select(Answer).where(Answer.response_id == resp.id, Answer.question_id == qid))
    if ans is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Spørgsmålet er ikke vist endnu.")
    # Idempotens: ældre/gentagne sekvensnumre ændrer intet
    if body.seq <= ans.last_seq:
        return {"questionId": question_key, "value": ans.value, "missingCode": ans.missing_code,
                "seq": ans.last_seq}
    now = utcnow()
    had = ans.value is not None or ans.missing_code is not None
    changed = (ans.value, ans.missing_code) != (body.value, body.missingCode)
    if changed:
        if had:
            ans.change_count += 1
            if body.viaBack:
                ans.changed_after_back = True
        if ans.answered_at is None and (body.value is not None or body.missingCode):
            ans.answered_at = now
            ans.rt_ms = int((now - ans.first_shown_at).total_seconds() * 1000)
        ans.value = body.value
        ans.missing_code = body.missingCode
        db.add(PresentationEvent(response_id=resp.id, event_type="back" if body.viaBack else "answer",
                                 question_id=question_key, position=ans.global_position))
    ans.last_seq = body.seq
    resp.last_activity_at = now
    return {"questionId": question_key, "value": ans.value, "missingCode": ans.missing_code, "seq": ans.last_seq}


@router.post("/sessions/{response_id}/complete")
def complete(response_id: str, response: Response, sess: ResponseSession = Depends(respondent),
             db: Session = Depends(get_db)):
    resp = _own(sess, response_id, db, lock=True)
    if resp.status == "completed":
        clear_cookie(response, RESP_COOKIE)
        return {"status": "completed"}
    now = utcnow()
    resp.status = "completed"
    resp.completed_at = now
    resp.last_activity_at = now
    db.add(PresentationEvent(response_id=resp.id, event_type="complete"))
    db.execute(update(AccessCode).where(AccessCode.id == sess.access_code_id)
               .values(completions_count=AccessCode.completions_count + 1))
    db.execute(update(ResponseSession).where(ResponseSession.response_id == resp.id).values(revoked=True))
    rk = db.scalar(select(ResumeKey).where(ResumeKey.response_id == resp.id))
    if rk:
        db.delete(rk)
    clear_cookie(response, RESP_COOKIE)
    return {"status": "completed"}
