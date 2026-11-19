"""Atomisk JSON-import af spørgeskemaer (spec §5)."""
from __future__ import annotations

import hashlib
import json
import pathlib
from collections import Counter
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Domain,
    Question,
    ResponseScale,
    Scenario,
    Subscale,
    Survey,
    SurveyVersion,
    utcnow,
)

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "schema" / "survey.schema.json"
MAX_BYTES = 2 * 1024 * 1024
SECONDS_PER_QUESTION = 9  # estimat inkl. læsning af adfærdsbeskrivelse


@lru_cache
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def parse_json(raw: bytes) -> tuple[dict | None, list[str]]:
    if len(raw) > MAX_BYTES:
        return None, [f"Filen er større end {MAX_BYTES // 1024} KB."]
    try:
        doc = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return None, [f"Ugyldig JSON: {exc}"[:300]]
    if not isinstance(doc, dict):
        return None, ["Roden skal være et objekt."]
    return doc, []


def _reject_constant(name: str) -> Any:
    raise ValueError(f"ikke-tilladt konstant {name}")


def validate(doc: dict) -> list[str]:
    errors: list[str] = []
    for err in sorted(_validator().iter_errors(doc), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "(rod)"
        errors.append(f"{path}: {err.message}"[:400])
        if len(errors) >= 50:
            errors.append("… flere fejl udeladt")
            return errors
    if errors:
        return errors

    scale = doc["responseScale"]
    if scale["min"] >= scale["max"]:
        errors.append("responseScale: min skal være mindre end max.")
    for lab in scale.get("labels", []):
        if not scale["min"] <= lab["value"] <= scale["max"]:
            errors.append(f"responseScale.labels: værdi {lab['value']} uden for skalaen.")
    label_vals = [lab["value"] for lab in scale.get("labels", [])]
    if len(label_vals) != len(set(label_vals)):
        errors.append("responseScale.labels: dublerede værdier.")

    persp = [p["code"] for p in doc["perspectives"]]
    for code, n in Counter(persp).items():
        if n > 1:
            errors.append(f"perspectives: dubleret kode '{code}'.")
    fixed = doc.get("fixedLastPerspective")
    if fixed and fixed not in persp:
        errors.append(f"fixedLastPerspective '{fixed}' findes ikke blandt perspectives.")

    doms = [d["code"] for d in doc["domains"]]
    for code, n in Counter(doms).items():
        if n > 1:
            errors.append(f"domains: dubleret kode '{code}'.")

    bvs = [b["code"] for b in doc.get("backgroundVariables", [])]
    for code, n in Counter(bvs).items():
        if n > 1:
            errors.append(f"backgroundVariables: dubleret kode '{code}'.")
    for b in doc.get("backgroundVariables", []):
        oc = [o["code"] for o in b["options"]]
        if len(oc) != len(set(oc)):
            errors.append(f"backgroundVariables.{b['code']}: dublerede svarmuligheder.")

    sids: Counter = Counter()
    qids: Counter = Counter()
    for i, item in enumerate(doc["items"]):
        sids[item["scenarioId"]] += 1
        if item["domainCode"] not in doms:
            errors.append(f"items/{i}: ukendt domainCode '{item['domainCode']}'.")
        seen_p = Counter()
        for q in item["questions"]:
            qids[q["id"]] += 1
            if q["perspective"] not in persp:
                errors.append(f"items/{i}: spørgsmål {q['id']} har ukendt perspektiv '{q['perspective']}'.")
            seen_p[q["perspective"]] += 1
        for p, n in seen_p.items():
            if n > 1:
                errors.append(f"items/{i}: flere spørgsmål for perspektiv '{p}' i samme scenarie.")
    for sid, n in sids.items():
        if n > 1:
            errors.append(f"items: dubleret scenarioId '{sid}'.")
    for qid, n in qids.items():
        if n > 1:
            errors.append(f"items: dubleret spørgsmåls-id '{qid}'.")
    return errors


def preview(doc: dict) -> dict:
    items = doc.get("items", [])
    n_q = sum(len(i.get("questions", [])) for i in items)
    per_sub = Counter(q["perspective"] for i in items for q in i.get("questions", []))
    per_dom = Counter(i["domainCode"] for i in items)
    return {
        "surveyId": doc.get("surveyId"),
        "title": doc.get("title"),
        "items": len(items),
        "questions": n_q,
        "domains": len(doc.get("domains", [])),
        "subscales": len(doc.get("perspectives", [])),
        "questionsPerSubscale": dict(per_sub),
        "itemsPerDomain": dict(per_dom),
        "reverseScored": sum(1 for i in items for q in i.get("questions", []) if q.get("reverseScored")),
        "backgroundVariables": [b["code"] for b in doc.get("backgroundVariables", [])],
        "estimatedMinutes": round(n_q * SECONDS_PER_QUESTION / 60),
    }


def canonical_sha256(doc: dict) -> str:
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def store_draft(db: Session, tenant_id: str, user_id: str, doc: dict) -> SurveyVersion:
    """Opretter en ny draft-version i én transaktion (kaldes inden for request-transaktionen)."""
    survey = db.scalar(
        select(Survey).where(Survey.tenant_id == tenant_id, Survey.survey_key == doc["surveyId"])
    )
    if survey is None:
        survey = Survey(tenant_id=tenant_id, survey_key=doc["surveyId"], title=doc["title"])
        db.add(survey)
        db.flush()
    next_no = (
        db.scalar(select(func.max(SurveyVersion.version_no)).where(SurveyVersion.survey_id == survey.id))
        or 0
    ) + 1
    sv = SurveyVersion(
        survey_id=survey.id,
        tenant_id=tenant_id,
        version_no=next_no,
        status="draft",
        schema_version=doc["schemaVersion"],
        source_json=json.dumps(doc, ensure_ascii=False, sort_keys=True),
        source_sha256=canonical_sha256(doc),
        imported_by=user_id,
    )
    db.add(sv)
    db.flush()

    scale = doc["responseScale"]
    db.add(ResponseScale(
        survey_version_id=sv.id, scale_type=scale["type"], min_value=scale["min"],
        max_value=scale["max"], labels=scale.get("labels", []),
        cannot_assess_label=(scale.get("cannotAssess") or {}).get("label"),
    ))
    subs = {}
    for pos, p in enumerate(doc["perspectives"]):
        s = Subscale(survey_version_id=sv.id, code=p["code"], name=p["name"],
                     instruction=p.get("instruction"), position=pos)
        db.add(s)
        subs[p["code"]] = s
    doms = {}
    for pos, d in enumerate(doc["domains"]):
        dm = Domain(survey_version_id=sv.id, code=d["code"], name=d["name"], position=pos)
        db.add(dm)
        doms[d["code"]] = dm
    db.flush()
    qpos = 0
    for pos, item in enumerate(doc["items"]):
        sc = Scenario(survey_version_id=sv.id, scenario_key=item["scenarioId"],
                      domain_id=doms[item["domainCode"]].id, behavior=item["behavior"], position=pos)
        db.add(sc)
        db.flush()
        for q in item["questions"]:
            db.add(Question(
                survey_version_id=sv.id, question_key=q["id"], scenario_id=sc.id,
                subscale_id=subs[q["perspective"]].id, text=q["text"],
                reverse_scored=bool(q.get("reverseScored", False)), position=qpos,
            ))
            qpos += 1
    db.flush()
    return sv


def publish(db: Session, sv: SurveyVersion, user_id: str) -> SurveyVersion:
    if sv.status != "draft":
        raise ValueError("Kun draft-versioner kan publiceres.")
    sv.status = "published"
    sv.published_at = utcnow()
    sv.published_by = user_id
    db.flush()
    return sv
