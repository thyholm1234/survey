"""PDF med personlige adgangskoder: én forside pr. afdeling til den ansvarlige og én side pr. kode.

Skrevet uden PDF-bibliotek (kun standardfonte, WinAnsi-kodning og QR-moduler tegnet som
rektangler), så der ikke tilføjes afhængigheder. Klartekstkoderne findes kun i hukommelsen,
mens dokumentet bygges; de gemmes aldrig.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import datetime

import segno

W, H = 595.28, 841.89  # A4 i punkter
MARGIN = 56

# Tegnbredder (1/1000 em) for Helvetica; fed tilnærmes med +6 %.
_HELV = dict(zip(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
    [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, *[556] * 10, 278, 278,
     584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667,
     778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556,
     278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500,
     334, 260, 334, 584],
))
_HELV.update({"æ": 889, "ø": 611, "å": 556, "Æ": 1000, "Ø": 778, "Å": 667, "é": 556, "–": 556, "•": 350,
              "«": 556, "»": 556, "“": 333, "”": 333, "„": 333})

FONTS = {"R": "Helvetica", "B": "Helvetica-Bold", "M": "Courier-Bold"}


def text_width(s: str, size: float, font: str = "R") -> float:
    if font == "M":
        return len(s) * 0.6 * size
    k = 1.06 if font == "B" else 1.0
    return sum(_HELV.get(c, 556) for c in s) * size * k / 1000


def wrap(s: str, size: float, width: float, font: str = "R") -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        cand = f"{cur} {word}".strip()
        if cur and text_width(cand, size, font) > width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def _esc(s: str) -> bytes:
    b = s.encode("cp1252", "replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


@dataclass
class Page:
    ops: list[bytes] = field(default_factory=list)

    def text(self, x: float, y: float, s: str, size: float = 11, font: str = "R", gray: float = 0.0) -> None:
        self.ops.append(b"BT %.3f g /%s %.1f Tf %.2f %.2f Td (" % (gray, font.encode(), size, x, y)
                        + _esc(s) + b") Tj ET")

    def center(self, y: float, s: str, size: float = 11, font: str = "R", gray: float = 0.0) -> None:
        self.text((W - text_width(s, size, font)) / 2, y, s, size, font, gray)

    def para(self, x: float, y: float, s: str, width: float, size: float = 11, font: str = "R",
             gray: float = 0.0, leading: float = 1.4) -> float:
        """Skriver ombrudt tekst; returnerer y under sidste linje."""
        for line in wrap(s, size, width, font):
            self.text(x, y, line, size, font, gray)
            y -= size * leading
        return y

    def rect(self, x: float, y: float, w: float, h: float, *, fill: float | None = None,
             stroke: float | None = None, lw: float = 1) -> None:
        op = b""
        if fill is not None:
            op += b"%.3f g " % fill
        if stroke is not None:
            op += b"%.3f G %.2f w " % (stroke, lw)
        paint = b"B" if fill is not None and stroke is not None else b"f" if fill is not None else b"S"
        self.ops.append(op + b"%.2f %.2f %.2f %.2f re %s" % (x, y, w, h, paint))

    def qr(self, x: float, y: float, size: float, data: str) -> None:
        rows = [list(r) for r in segno.make(data, error="m").matrix_iter(border=2)]
        m = size / len(rows)
        out = [b"0 g"]
        for i, row in enumerate(rows):
            j = 0
            while j < len(row):  # saml vandrette løb til ét rektangel
                if row[j]:
                    k = j
                    while k < len(row) and row[k]:
                        k += 1
                    out.append(b"%.2f %.2f %.2f %.2f re" % (x + j * m, y + size - (i + 1) * m, (k - j) * m, m))
                    j = k
                else:
                    j += 1
        out.append(b"f")
        self.ops.append(b"\n".join(out))


def _write_pdf(pages: list[Page], title: str) -> bytes:
    objs: list[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    font_ids = {k: add(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % v.encode())
                for k, v in FONTS.items()}
    fonts = b" ".join(b"/%s %d 0 R" % (k.encode(), i) for k, i in font_ids.items())
    pages_id = len(objs) + 1 + 2 * len(pages)  # reserveres efter sidernes objekter
    kids = []
    for p in pages:
        data = zlib.compress(b"\n".join(p.ops))
        cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream")
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font << %s >> >> "
                        b"/Contents %d 0 R >>" % (pages_id, W, H, fonts, cid)))
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>"
               % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))) == pages_id
    info = add(b"<< /Title (" + _esc(title) + b") /Producer (" + _esc("Spørgeskema") + b") >>")
    root = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, root, info, xref)
    return bytes(out)


# ---------------------------------------------------------------------------


@dataclass
class UnitCodes:
    unit_name: str
    institution: str | None
    codes: list[str]


def _cover(u: UnitCodes, survey: str, valid_to: datetime) -> Page:
    p = Page()
    where = f"{u.institution} › {u.unit_name}" if u.institution else u.unit_name
    p.text(MARGIN, H - 80, "Til den ansvarlige", 12, "B", 0.4)
    y = p.para(MARGIN, H - 120, where, W - 2 * MARGIN, 26, "B", leading=1.2)
    y = p.para(MARGIN, y - 4, survey, W - 2 * MARGIN, 14, gray=0.3)
    y -= 24
    p.rect(MARGIN, y - 70, W - 2 * MARGIN, 80, fill=0.95)
    p.text(MARGIN + 20, y - 22, f"{len(u.codes)} personlige adgangskoder", 18, "B")
    p.text(MARGIN + 20, y - 48, f"Gyldige til og med {valid_to:%d.%m.%Y}", 12, gray=0.3)
    y -= 110
    p.text(MARGIN, y, "Sådan fordeler du koderne", 14, "B")
    y -= 26
    steps = [
        "Giv én side til hver person, der skal deltage. Hver side har sin egen kode.",
        "En kode giver adgang til én besvarelse. Personen kan altid logge ind igen med samme kode for at "
        "fortsætte, trække sin besvarelse tilbage eller svare forfra.",
        "Notér ikke, hvem der får hvilken kode. Så forbliver besvarelserne pseudonyme.",
        "Ubrugte sider opbevares sikkert eller makuleres, når undersøgelsen er slut.",
        "Koderne gemmes ikke i systemet og kan ikke genskabes. Bortkommer en side, kan administratoren "
        "deaktivere koden ud fra nummeret øverst på siden.",
    ]
    for i, s in enumerate(steps, 1):
        p.text(MARGIN, y, f"{i}.", 11, "B")
        y = p.para(MARGIN + 20, y, s, W - 2 * MARGIN - 20, 11) - 8
    return p


def _code_page(u: UnitCodes, code: str, n: int, survey: str, url: str, valid_to: datetime) -> Page:
    p = Page()
    where = f"{u.institution} › {u.unit_name}" if u.institution else u.unit_name
    p.text(MARGIN, H - 60, where, 10, gray=0.45)
    nr = f"Kode nr. {n} af {len(u.codes)}"
    p.text(W - MARGIN - text_width(nr, 10), H - 60, nr, 10, gray=0.45)
    y = p.para(MARGIN, H - 110, "Din personlige adgangskode", W - 2 * MARGIN, 24, "B")
    y = p.para(MARGIN, y + 4, survey, W - 2 * MARGIN, 13, gray=0.3)

    # Kodeboks + QR
    box_top = y - 14
    qr_size = 128
    box_w = W - 2 * MARGIN - qr_size - 20
    p.rect(MARGIN, box_top - qr_size, box_w, qr_size, fill=0.95, stroke=0.75, lw=0.8)
    p.text(MARGIN + 20, box_top - 30, "Adgangskode", 11, "B", 0.35)
    size = min(30, (box_w - 40) / (len(code) * 0.6))
    p.text(MARGIN + 20, box_top - 30 - size - 12, code, size, "M")
    p.text(MARGIN + 20, box_top - qr_size + 18, f"Gyldig til og med {valid_to:%d.%m.%Y}", 10, gray=0.35)
    p.qr(W - MARGIN - qr_size, box_top - qr_size, qr_size, f"{url}/#kode={code.replace('-', '')}")
    y = box_top - qr_size - 14
    cap = "Scan for at åbne med koden udfyldt"
    p.text(W - MARGIN - qr_size + (qr_size - text_width(cap, 8)) / 2, y, cap, 8, gray=0.4)

    y -= 30
    p.text(MARGIN, y, "Sådan gør du", 15, "B")
    y -= 26
    steps = [
        f"Gå til {url} på computer, tablet eller telefon – eller scan QR-koden.",
        "Skriv koden ovenfor og tryk »Fortsæt«. Store/små bogstaver og bindestreger er ligegyldige.",
        "Læs informationen om undersøgelsen, og sæt flueben, hvis du vil deltage.",
        "Besvar spørgsmålene. Dine svar gemmes løbende, så du kan holde pause når som helst.",
        "Tryk »Afslut og indsend«, når du er færdig.",
    ]
    for i, s in enumerate(steps, 1):
        p.rect(MARGIN, y - 5, 18, 18, fill=0.15)
        p.text(MARGIN + (18 - text_width(str(i), 10, "B")) / 2, y, str(i), 10, "B", 1.0)
        y = p.para(MARGIN + 30, y, s, W - 2 * MARGIN - 30, 11.5) - 10

    y -= 8
    p.rect(MARGIN, y - 92, W - 2 * MARGIN, 104, stroke=0.75, lw=0.8)
    p.text(MARGIN + 16, y - 14, "Vil du ændre noget bagefter?", 12, "B")
    p.para(MARGIN + 16, y - 34,
           "Log ind igen med samme kode. Er du ikke færdig, fortsætter du, hvor du slap. Har du indsendt, "
           "kan du trække din besvarelse tilbage – så slettes den helt – og derefter svare forfra.",
           W - 2 * MARGIN - 32, 11)

    p.para(MARGIN, 96,
           "Koden er personlig – del den ikke med andre. Der gemmes ikke navn, e-mail eller IP-adresse "
           "sammen med dine svar, og resultater vises kun samlet for grupper.",
           W - 2 * MARGIN, 9.5, gray=0.4)
    return p


def build(units: list[UnitCodes], survey: str, url: str, valid_to: datetime) -> bytes:
    pages: list[Page] = []
    for u in units:
        pages.append(_cover(u, survey, valid_to))
        pages += [_code_page(u, c, i, survey, url, valid_to) for i, c in enumerate(u.codes, 1)]
    return _write_pdf(pages, f"Adgangskoder – {survey}")
