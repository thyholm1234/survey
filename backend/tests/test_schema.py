"""JSON-schema contract tests (spec §5, §16)."""
import copy
import json
import pathlib

import pytest

from app.services import survey_import

SAMPLE = pathlib.Path("/app/data/sample_almenramme_survey.json")


@pytest.fixture()
def doc():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_sample_is_valid_and_preview(doc):
    assert survey_import.validate(doc) == []
    p = survey_import.preview(doc)
    assert p["items"] == 40 and p["questions"] == 160 and p["domains"] == 10 and p["subscales"] == 4
    assert p["questionsPerSubscale"] == {"self": 40, "team": 40, "frame": 40, "belong": 40}
    assert p["reverseScored"] == 0


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["items"].append(copy.deepcopy(d["items"][0])), "dubleret scenarioId"),
    (lambda d: d["items"][1]["questions"][0].update(id=d["items"][0]["questions"][0]["id"]), "dubleret spørgsmåls-id"),
    (lambda d: d["items"][0].update(domainCode="ZZ"), "ukendt domainCode"),
    (lambda d: d["items"][0]["questions"][0].update(perspective="other"), "perspective"),
    (lambda d: d["responseScale"].update(min=6, max=1), "min skal være mindre"),
    (lambda d: d["responseScale"].update(type="slider"), "responseScale/type"),
    (lambda d: d["domains"].append(dict(d["domains"][0])), "dubleret kode"),
    (lambda d: d.update(extra=1), "Additional properties"),
    (lambda d: d["items"][0]["questions"].append(dict(d["items"][0]["questions"][0], id="X1")), "flere spørgsmål for perspektiv"),
    (lambda d: d.update(fixedLastPerspective="team") or d["perspectives"].pop(1), "fixedLastPerspective"),
])
def test_rejections(doc, mutate, needle):
    mutate(doc)
    errors = survey_import.validate(doc)
    assert errors, "skulle være afvist"
    assert any(needle in e for e in errors), errors


def test_parse_rejects_nan_and_oversize():
    _, errs = survey_import.parse_json(b'{"a": NaN}')
    assert errs
    _, errs = survey_import.parse_json(b" " * (survey_import.MAX_BYTES + 1))
    assert errs


def test_canonical_hash_stable(doc):
    h1 = survey_import.canonical_sha256(doc)
    h2 = survey_import.canonical_sha256(json.loads(json.dumps(doc, indent=4)))
    assert h1 == h2
