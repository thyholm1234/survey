"""Eksport (spec §11). Kræver eksportrettighed; aldrig adgangskoder eller direkte identifikatorer."""
from __future__ import annotations

import csv
import html
import io
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import Principal, admin
from ..services import analysis_data, dashboard
from ..services.scoring import DEFAULT_DOMAIN_THRESHOLD, DEFAULT_SUBSCALE_THRESHOLD
from .admin_dashboard import tenant_k

router = APIRouter(prefix="/api/admin/exports", tags=["admin-exports"])

FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


class ExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenantId: str = Field(max_length=32)
    format: Literal["long_csv", "wide_csv", "codebook_json", "protocol_json", "report_html"]
    filters: analysis_data.Filters


def _safe(v) -> str:
    """Beskyt mod CSV/formel-injektion i regneark."""
    if v is None:
        return ""
    if isinstance(v, float) and v != v:  # NaN
        return ""
    s = str(v)
    return "'" + s if s.startswith(FORMULA_PREFIX) else s


def _csv(rows: list[list], header: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([_safe(x) for x in r])
    return buf.getvalue()


LONG_COLS = ["response_id", "unit_id", "institution_id", "unit_type", "question_key", "scenario_key", "subscale", "domain",
             "raw", "value", "missing", "global_position", "block_index", "block_position",
             "first_shown_at", "answered_at", "rt_ms", "change_count", "changed_after_back"]


def long_csv(ds: analysis_data.Dataset, sv_id: str) -> str:
    bg = [c for c in ds.responses.columns if c.startswith("bg_")]
    meta = ds.responses.set_index("response_id")
    rows = []
    for r in ds.long.itertuples(index=False):
        rr = r._asdict()
        raw = rr["raw"]
        rows.append([
            rr["response_id"], rr["unit_id"], rr["institution_id"], rr["unit_type"], rr["question_key"], rr["scenario_key"],
            rr["subscale"], rr["domain"], None if raw != raw or raw is None else int(raw),
            None if rr["value"] != rr["value"] else rr["value"], rr["missing"],
            None if rr["global_position"] != rr["global_position"] else int(rr["global_position"]),
            None if rr["block_index"] != rr["block_index"] else int(rr["block_index"]),
            None if rr["block_position"] != rr["block_position"] else int(rr["block_position"]),
            rr["first_shown_at"].isoformat() if hasattr(rr["first_shown_at"], "isoformat") else None,
            rr["answered_at"].isoformat() if hasattr(rr["answered_at"], "isoformat") else None,
            None if rr["rt_ms"] != rr["rt_ms"] or rr["rt_ms"] is None else int(rr["rt_ms"]),
            None if rr["change_count"] != rr["change_count"] or rr["change_count"] is None else int(rr["change_count"]),
            None if rr["changed_after_back"] is None or rr["changed_after_back"] != rr["changed_after_back"]
            else int(bool(rr["changed_after_back"])),
            sv_id, *[meta.at[rr["response_id"], c] for c in bg],
        ])
    return _csv(rows, LONG_COLS + ["survey_version_id"] + bg)


def wide_csv(ds: analysis_data.Dataset, sv_id: str) -> str:
    qkeys = ds.questions["question_key"].tolist()
    bg = [c for c in ds.responses.columns if c.startswith("bg_")]
    cell = ds.long.assign(cell=ds.long.apply(
        lambda r: r["missing"] if r["missing"] else int(r["raw"]), axis=1))
    pivot = cell.pivot(index="response_id", columns="question_key", values="cell")
    rows = []
    for r in ds.responses.itertuples(index=False):
        d = r._asdict()
        rows.append([d["response_id"], d["unit_id"], d["institution_id"], d["unit_type"], sv_id, d["status"],
                     d["started_at"].isoformat() if d["started_at"] is not None else None,
                     d["completed_at"].isoformat() if d["completed_at"] is not None and d["completed_at"] == d["completed_at"] else None,
                     d["seed"], d["block_order"], *[d.get(c) for c in bg],
                     *[pivot.at[d["response_id"], q] if q in pivot.columns else None for q in qkeys]])
    header = ["response_id", "unit_id", "institution_id", "unit_type", "survey_version_id", "status", "started_at",
              "completed_at", "seed", "block_order", *bg, *qkeys]
    return _csv(rows, header)


def codebook(ds: analysis_data.Dataset, sv_id: str) -> dict:
    doc = ds.doc
    return {
        "surveyVersionId": sv_id,
        "surveyId": doc["surveyId"],
        "title": doc["title"],
        "responseScale": doc["responseScale"],
        "perspectives": doc["perspectives"],
        "domains": doc["domains"],
        "backgroundVariables": doc.get("backgroundVariables", []),
        "questions": [
            {"questionId": q["id"], "scenarioId": i["scenarioId"], "domain": i["domainCode"],
             "subscale": q["perspective"], "reverseScored": q.get("reverseScored", False),
             "text": q["text"], "behavior": i["behavior"]}
            for i in doc["items"] for q in i["questions"]
        ],
        "missingCodes": {
            analysis_data.MISSING_CANNOT: "Kan ikke vurdere (eksplicit valgt)",
            analysis_data.MISSING_SKIPPED: "Vist men ikke besvaret",
            analysis_data.MISSING_NOT_REACHED: "Ikke vist",
        },
        "columns": {
            "raw": "Rå svarværdi", "value": "Scoret værdi (reverse-justeret), tom ved missing",
            "rt_ms": "Svartid fra første visning til første svar (server-målt, ms; winsorisér i analyse)",
            "global_position": "0-indekseret position i samlet rækkefølge",
            "block_index": "0-indekseret blok", "changed_after_back": "Svar ændret efter tilbage-navigation",
        },
    }


def _fmt(x, nd=2) -> str:
    return "–" if x is None else f"{x:.{nd}f}"


def report_html(dash: dict, proto: dict, title: str) -> str:
    e = html.escape
    names = {s["code"]: s["name"] for s in dash["subscales"]}
    parts = [
        "<!doctype html><html lang='da'><head><meta charset='utf-8'>",
        f"<title>{e(title)} – rapport</title>",
        "<meta name='color-scheme' content='light dark'>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #8888;padding:.3rem .5rem;"
        "text-align:right}th:first-child,td:first-child{text-align:left}caption{text-align:left;font-weight:600}"
        ".note{border-left:4px solid #b58900;padding:.5rem 1rem}</style></head><body>",
        f"<h1>{e(title)}</h1>",
        "<p class='note'>Resultaterne er aggregerede, beskrivende og må ikke bruges til individuelle "
        "medarbejderprofiler, ranglister eller performancebeslutninger. Forskelle må ikke fortolkes kausalt.</p>",
    ]
    if dash.get("syntheticN"):
        parts.append(f"<p class='note'><strong>DEMODATA:</strong> {dash['syntheticN']} af {dash['n']} besvarelser er "
                     "syntetiske demosvar og ikke rigtige besvarelser.</p>")
    if dash.get("suppressed"):
        parts.append(f"<p>{e(dash.get('reason', 'Undertrykt.'))}</p>")
    else:
        parts.append(f"<h2>Metode</h2><p>N = {dash['n']} fuldførte besvarelser. Subskalascore = middel af gyldige "
                     f"items ved mindst {int(dash['thresholds']['subscale'] * 100)} % besvaret. 'Kan ikke vurdere' "
                     f"og ubesvarede behandles som missing. Celler med n &lt; {dash['minCellSize']} er undertrykt "
                     f"({e(dash['suppressionRules'])}). Totalscore beregnes ikke.</p>")
        parts.append("<table><caption>Subskalaprofil</caption><thead><tr><th scope='col'>Subskala</th>"
                     "<th scope='col'>N gyldige</th><th scope='col'>Missing %</th><th scope='col'>Middel</th>"
                     "<th scope='col'>SD</th><th scope='col'>Median</th><th scope='col'>IQR</th>"
                     "<th scope='col'>95 % CI</th></tr></thead><tbody>")
        for r in dash["profile"]:
            if r.get("suppressed"):
                parts.append(f"<tr><th scope='row'>{e(names[r['subscale']])}</th><td colspan='7'>Undertrykt</td></tr>")
                continue
            ci = r["ci95"] or [None, None]
            parts.append(f"<tr><th scope='row'>{e(names[r['subscale']])}</th><td>{r['nValid']}</td>"
                         f"<td>{_fmt(r['missingPct'], 1)}</td><td>{_fmt(r['mean'])}</td><td>{_fmt(r['sd'])}</td>"
                         f"<td>{_fmt(r['median'])}</td><td>{_fmt(r['iqr'])}</td>"
                         f"<td>{_fmt(ci[0])}–{_fmt(ci[1])}</td></tr>")
        parts.append("</tbody></table>")
        lvl = "Institutioner" if dash.get("comparisonLevel") == "institution" else (
            "Valgte institutioner og afdelinger" if dash.get("comparisonLevel") == "custom" else None) or (
            f"Afdelinger/klasser – {dash['institution']['name']}" if dash.get("institution") else "Afdelinger/klasser")
        parts.append(f"<table><caption>{e(lvl)} (alfabetisk, ikke rangliste; middel)</caption><thead><tr>"
                     "<th scope='col'>Navn</th><th scope='col'>N</th>"
                     + "".join(f"<th scope='col'>{e(names[s['code']])}</th>" for s in dash["subscales"])
                     + "</tr></thead><tbody>")
        for u in dash["units"]:
            if u.get("suppressed"):
                parts.append(f"<tr><th scope='row'>{e(u['name'])}</th>"
                             f"<td colspan='{1 + len(dash['subscales'])}'>Undertrykt</td></tr>")
                continue
            parts.append(f"<tr><th scope='row'>{e(u['name'])}</th><td>{u['n']}</td>" + "".join(
                "<td>Undertrykt</td>" if c.get("suppressed") else f"<td>{_fmt(c['mean'])}</td>" for c in u["subscales"])
                + "</tr>")
        parts.append("</tbody></table>")
        parts.append("<table><caption>Skole og dagtilbud (beskrivende; Hedges g skole minus dagtilbud)</caption>"
                     "<thead><tr><th scope='col'>Subskala</th><th scope='col'>Dagtilbud middel (n)</th>"
                     "<th scope='col'>Skole middel (n)</th><th scope='col'>Hedges g [95 % CI]</th></tr></thead><tbody>")
        for r in dash["setting"]:
            def cell(d):
                return "Undertrykt" if d.get("suppressed") else f"{_fmt(d['mean'])} ({d['nValid']})"
            g = r.get("hedgesG_school_minus_daycare") or {}
            gci = g.get("ci95") or [None, None]
            parts.append(f"<tr><th scope='row'>{e(names[r['subscale']])}</th><td>{cell(r['daycare'])}</td>"
                         f"<td>{cell(r['school'])}</td><td>{_fmt(g.get('g'))} [{_fmt(gci[0])}; {_fmt(gci[1])}]</td></tr>")
        parts.append("</tbody></table>")
        parts.append("<table><caption>Missing pr. subskala (% af celler)</caption><thead><tr><th scope='col'>Subskala"
                     "</th><th scope='col'>Gyldige</th><th scope='col'>Kan ikke vurdere</th><th scope='col'>"
                     "Ubesvaret</th><th scope='col'>Ikke nået</th></tr></thead><tbody>")
        for r in dash["missing"]["bySubscale"]:
            parts.append(f"<tr><th scope='row'>{e(names[r['subscale']])}</th><td>{r.get('validPct')}</td>"
                         f"<td>{r.get('cannotAssessPct')}</td><td>{r.get('notAnsweredPct')}</td>"
                         f"<td>{r.get('notReachedPct')}</td></tr>")
        parts.append("</tbody></table>")
    parts.append("<h2>Analyseprotokol</h2><pre>" + e(json.dumps(proto, indent=2, ensure_ascii=False)) + "</pre>")
    parts.append("<h2>Forbehold</h2><ul><li>Pseudonymiserede data er stadig personoplysninger.</li>"
                 "<li>Inferens for skole/dagtilbud bør baseres på mixed model (analysekørsel), da medarbejdere "
                 "er grupperet i afdelinger.</li><li>Instrumentets faktorstruktur og måleinvarians er ikke "
                 "undersøgt (fase 2).</li></ul></body></html>")
    return "".join(parts)


@router.post("")
def export(body: ExportIn, p: Principal = Depends(admin), db: Session = Depends(get_db, scope="function")):
    allowed = p.allowed_units(db, body.tenantId)
    f = body.filters
    scope_units = (set(f.unitIds) & allowed) if f.unitIds else allowed
    if not p.can_export(body.tenantId, scope_units):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du har ikke eksportrettighed.")
    try:
        ds = analysis_data.load(db, body.tenantId, allowed, f)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ikke fundet.") from None
    k = tenant_k(db, body.tenantId)
    row_level = body.format in ("long_csv", "wide_csv")
    if row_level and (ds.n < k or (f.optional_active() and 0 < ds.base_n - ds.n < k)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Eksport kræver mindst {k} besvarelser og må ikke isolere en lille gruppe.")
    proto = analysis_data.protocol(ds, f, {"export": body.format, "minCellSize": k})
    digest = proto["dataSha256"]
    sv = f.surveyVersionId
    if body.format == "long_csv":
        content, mime, ext = long_csv(ds, sv), "text/csv; charset=utf-8", "csv"
    elif body.format == "wide_csv":
        content, mime, ext = wide_csv(ds, sv), "text/csv; charset=utf-8", "csv"
    elif body.format == "codebook_json":
        content, mime, ext = json.dumps(codebook(ds, sv), ensure_ascii=False, indent=2), "application/json", "json"
    elif body.format == "protocol_json":
        content, mime, ext = json.dumps(proto, ensure_ascii=False, indent=2, default=str), "application/json", "json"
    else:
        dash = dashboard.build(ds, f, k, DEFAULT_SUBSCALE_THRESHOLD, DEFAULT_DOMAIN_THRESHOLD)
        content, mime, ext = report_html(dash, proto, ds.doc["title"]), "text/html; charset=utf-8", "html"
    audit.record("export.create", actor_type="user", actor_id=p.id, tenant_id=body.tenantId,
                 target_type="survey_version", target_id=sv,
                 details={"format": body.format, "n": ds.n, "dataSha256": digest,
                          "filters": json.loads(f.model_dump_json())})
    fname = f"{body.format}_{sv[:8]}_{digest[:12]}.{ext}"
    return Response(content=content.encode("utf-8"), media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="{fname}"',
        "X-Data-SHA256": digest,
        "Cache-Control": "no-store",
    })
