"""Syntetiske demosvar til afprøvning af resultater, analyser og rapporter.

Besvarelserne markeres is_synthetic=1 og app_version="synthetic", er ikke koblet til nogen adgangskode
og kan slettes samlet. Værdierne er generiske (virker for ethvert instrument): hver subskala får et
niveau omkring skalaens midte, hver afdeling en lille forskydning, og hver person sin egen variation.
"""
from __future__ import annotations

import json
import random
from datetime import timedelta

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ..models import (
    Answer,
    Domain,
    OrganizationUnit,
    PresentationEvent,
    Question,
    Response,
    ResponseScale,
    Scenario,
    Subscale,
    SurveyVersion,
    utcnow,
)
from .randomization import Item, build_plan


def generate(db: Session, sv: SurveyVersion, units: list[tuple[OrganizationUnit, int]], seed: int | None = None) -> int:
    rng = random.Random(seed)
    doc = json.loads(sv.source_json)
    scale = db.scalar(select(ResponseScale).where(ResponseScale.survey_version_id == sv.id))
    lo, hi = scale.min_value, scale.max_value
    mid, spread = (lo + hi) / 2, (hi - lo) / 5
    rows = db.execute(
        select(Question.id, Question.question_key, Subscale.code, Domain.code, Question.reverse_scored)
        .join(Subscale, Subscale.id == Question.subscale_id)
        .join(Scenario, Scenario.id == Question.scenario_id)
        .join(Domain, Domain.id == Scenario.domain_id)
        .where(Question.survey_version_id == sv.id)
        .order_by(Question.position)
    ).all()
    qid = {r[1]: r[0] for r in rows}
    reverse = {r[1] for r in rows if r[4]}
    items = [Item(question_id=r[1], perspective=r[2], domain=r[3]) for r in rows]
    perspectives = [p["code"] for p in doc["perspectives"]]
    sub_level = {p: mid + rng.gauss(0.3, 0.5) * spread for p in perspectives}
    dom_eff = {d["code"]: rng.gauss(0, 0.3) * spread for d in doc["domains"]}
    type_eff = {"daycare": rng.gauss(0, 0.3) * spread, "school": rng.gauss(0, 0.3) * spread, "other": 0.0}
    bgvars = doc.get("backgroundVariables", [])
    now = utcnow()
    created = 0
    for unit, n in units:
        unit_eff = rng.gauss(0, 0.25) * spread + type_eff.get(unit.unit_type, 0.0)
        usage: dict = {}
        for (bo,) in db.execute(select(Response.block_order).where(
                Response.survey_version_id == sv.id, Response.unit_id == unit.id)):
            usage[tuple(bo)] = usage.get(tuple(bo), 0) + 1
        for _ in range(n):
            pseed = rng.getrandbits(63)
            plan = build_plan(items, perspectives, doc.get("fixedLastPerspective"), usage, pseed)
            usage[tuple(plan.block_order)] = usage.get(tuple(plan.block_order), 0) + 1
            bg = {b["code"]: (rng.choice(b["options"])["code"] if rng.random() > 0.05 else None) for b in bgvars}
            start = now - timedelta(days=rng.randint(1, 30), minutes=rng.randint(0, 600))
            theta = {p: sub_level[p] + unit_eff + rng.gauss(0, 0.6) * spread for p in perspectives}
            speed = rng.lognormvariate(0, 0.3)
            incomplete = rng.random() < 0.05
            stop_at = rng.randint(len(plan.order) // 5, len(plan.order) - 1) if incomplete else len(plan.order)
            resp = Response(
                tenant_id=unit.tenant_id, unit_id=unit.id, unit_type=unit.unit_type, survey_version_id=sv.id,
                group_tags=[], background=bg, started_at=start, last_activity_at=start, seed=pseed,
                block_order=plan.block_order, presentation_order=[i.question_id for i in plan.order],
                randomization_meta=plan.meta, browser_class=rng.choice(["chromium", "firefox", "safari"]),
                screen_class=rng.choice(["s", "m", "l"]), app_version="synthetic", is_synthetic=True,
            )
            db.add(resp)
            db.flush()
            t = start
            answers = []
            block_counts: dict[int, int] = {}
            for pos, it in enumerate(plan.order[:stop_at]):
                bi = plan.block_order.index(it.perspective)
                bp = block_counts.get(bi, 0)
                block_counts[bi] = bp + 1
                rt = int(rng.lognormvariate(8.8, 0.45) * speed)  # ≈ 6,6 s median
                shown, t = t, t + timedelta(milliseconds=rt)
                u = rng.random()
                value, miss, answered = None, None, t
                if u < 0.03 and scale.cannot_assess_label:
                    miss = "CANNOT_ASSESS"
                elif u < 0.045:
                    answered, rt = None, None
                else:
                    x = theta[it.perspective] + dom_eff[it.domain] + rng.gauss(0, 0.7) * spread
                    value = int(min(hi, max(lo, round(x))))
                    if it.question_id in reverse:  # negativt formuleret: rå værdi spejles
                        value = lo + hi - value
                answers.append({"response_id": resp.id, "question_id": qid[it.question_id], "value": value,
                                "missing_code": miss, "global_position": pos, "block_index": bi,
                                "block_position": bp, "first_shown_at": shown, "answered_at": answered,
                                "rt_ms": rt, "change_count": 0, "changed_after_back": False, "last_seq": 1})
            if answers:
                db.execute(insert(Answer), answers)
            resp.last_activity_at = t
            if not incomplete:
                resp.status, resp.completed_at = "completed", t
            db.add(PresentationEvent(response_id=resp.id, event_type="start", at=start))
            created += 1
    db.flush()
    return created
