#!/usr/bin/env python3
"""Genererer frontend/js/icons.js fra Lucide (ISC-licens, https://lucide.dev).

Ikonerne hentes ved BYGGETID og indlejres som data, så frontenden ikke indlæser noget fra
tredjepart (CSP: script-src 'self'). Kør: python3 scripts/build_icons.py
"""
import json
import pathlib
import re
import urllib.request

VERSION = "0.460.0"
ICONS = [
    "shield-check", "clock", "mail", "building-2", "target", "circle-check", "arrow-right", "arrow-left",
    "chevron-down", "copy", "check", "key-round", "log-out", "lock", "chart-bar", "file-text", "users",
    "download", "trash-2", "info", "triangle-alert", "layout-dashboard", "clipboard-list", "flask-conical",
    "scroll-text", "landmark", "heart-handshake", "circle-help", "send", "lightbulb", "eye-off", "play",
]


def fetch(name: str) -> str:
    url = f"https://unpkg.com/lucide-static@{VERSION}/icons/{name}.svg"
    with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 (fast, kendt URL)
        return r.read().decode()


out = {}
for n in ICONS:
    svg = fetch(n)
    inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    nodes = re.findall(r"<(path|circle|rect|line|polyline|polygon|ellipse)\s+([^>]*?)/>", inner)
    parsed = []
    for tag, attrs in nodes:
        parsed.append([tag, dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))])
    assert parsed, n
    out[n] = parsed

js = (
    "// GENERERET af scripts/build_icons.py – redigér ikke i hånden.\n"
    f"// Lucide v{VERSION} (ISC, https://lucide.dev). Opbygges med createElementNS (Trusted Types-sikkert).\n"
    "const DATA = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n\n"
    "const NS = 'http://www.w3.org/2000/svg';\n"
    "/** Dekorativt ikon (aria-hidden). Størrelse styres i CSS via .icon / .icon-sm / .icon-lg. */\n"
    "export function icon(name, cls = '') {\n"
    "  const nodes = DATA[name];\n"
    "  if (!nodes) throw new Error(`Ukendt ikon: ${name}`);\n"
    "  const svg = document.createElementNS(NS, 'svg');\n"
    "  svg.setAttribute('viewBox', '0 0 24 24');\n"
    "  svg.setAttribute('fill', 'none');\n"
    "  svg.setAttribute('stroke', 'currentColor');\n"
    "  svg.setAttribute('stroke-width', '2');\n"
    "  svg.setAttribute('stroke-linecap', 'round');\n"
    "  svg.setAttribute('stroke-linejoin', 'round');\n"
    "  svg.setAttribute('aria-hidden', 'true');\n"
    "  svg.setAttribute('focusable', 'false');\n"
    "  svg.setAttribute('class', `icon ${cls}`.trim());\n"
    "  for (const [tag, attrs] of nodes) {\n"
    "    const el = document.createElementNS(NS, tag);\n"
    "    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);\n"
    "    svg.append(el);\n"
    "  }\n"
    "  return svg;\n"
    "}\n"
)
target = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "js" / "icons.js"
target.write_text(js, encoding="utf-8")
print(f"Skrev {target} ({len(out)} ikoner)")
