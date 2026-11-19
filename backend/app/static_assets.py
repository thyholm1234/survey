"""Frontend med cache-busting: alle referencer til /js, /css og /fonts får ?v=<indholdshash>.

En CDN foran appen (fx Cloudflare med »Browser Cache TTL«) kan overskrive appens Cache-Control, så
browsere beholder gamle JS-filer i timevis efter en deploy. Med versionerede URL'er henter browseren
automatisk de nye filer, fordi HTML-siderne (som aldrig caches) peger på nye adresser.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

_HTML_REF = re.compile(r'((?:src|href)=")(/(?:js|css|fonts)/[^"?#]+)(")')
_JS_IMPORT = re.compile(r"""((?:\bfrom|^import)\s+')(\./[^'?#]+\.js)(')""", re.M)
_CSS_URL = re.compile(r'(url\(")(/fonts/[^"?#]+)("\))')
REWRITE = {".html": _HTML_REF, ".js": _JS_IMPORT, ".css": _CSS_URL}


def asset_version(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


class VersionedStaticFiles(StaticFiles):
    def __init__(self, *, directory: Path, **kw) -> None:
        super().__init__(directory=directory, **kw)
        self.version = asset_version(directory)
        self._cache: dict[str, bytes] = {}

    def _rewrite(self, path: str, suffix: str) -> bytes:
        if path not in self._cache:
            text = Path(path).read_text(encoding="utf-8")
            text = REWRITE[suffix].sub(lambda m: f"{m[1]}{m[2]}?v={self.version}{m[3]}", text)
            self._cache[path] = text.encode("utf-8")
        return self._cache[path]

    async def get_response(self, path: str, scope) -> Response:
        resp = await super().get_response(path, scope)
        if isinstance(resp, FileResponse) and resp.status_code == 200:
            suffix = Path(resp.path).suffix
            if suffix in REWRITE:
                return Response(self._rewrite(str(resp.path), suffix), media_type=resp.media_type)
        return resp
