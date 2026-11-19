"""FastAPI-applikation."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .db import ping
from .static_assets import VersionedStaticFiles
from .routers import admin_analyses, admin_auth, admin_dashboard, admin_demo, admin_exports, admin_org, admin_surveys, public, respondent, system

log = logging.getLogger("app")

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# Frontend-CSP (tidligere sat af Caddy). Ingen inline-scripts, Trusted Types håndhævet.
WEB_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; manifest-src 'self'; form-action 'self'; base-uri 'none'; object-src 'none'; "
    "frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types 'none'; "
    "upgrade-insecure-requests; report-to csp"
)
PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=(), "
    "browsing-topics=()"
)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
MAX_BODY = 2 * 1024 * 1024 + 4096


def _retention_loop(stop: threading.Event) -> None:
    from .services.retention import run_retention

    while not stop.wait(3600):
        try:
            run_retention()
        except Exception:  # noqa: BLE001
            log.exception("retention job fejlede")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fejl tidligt ved manglende/svage hemmeligheder
    stop = threading.Event()
    t = None
    if not get_settings().is_test:
        t = threading.Thread(target=_retention_loop, args=(stop,), daemon=True)
        t.start()
    yield
    stop.set()


def create_app() -> FastAPI:
    s = get_settings()
    asset_version: str | None = None  # sættes, når frontend monteres nedenfor
    app = FastAPI(
        title="Spørgeskema-API",
        version=s.app_version,
        docs_url=None,  # ingen offentlig API-dokumentation i produktion
        redoc_url=None,
        openapi_url="/api/openapi.json" if s.app_env != "production" else None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        path = request.url.path
        # Fetch Metadata: afvis cross-site API-kald før autentifikation
        site = request.headers.get("sec-fetch-site")
        if path.startswith("/api/") and site and site not in ("same-origin", "none"):
            return JSONResponse({"detail": "Forbudt."}, status_code=403)
        if request.method in UNSAFE and path.startswith("/api/") and path != "/api/csp-report":
            origin = request.headers.get("origin")
            if origin is not None and origin != s.public_origin:
                return JSONResponse({"detail": "Ugyldig oprindelse."}, status_code=403)
            ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return JSONResponse({"detail": "Content-Type skal være application/json."}, status_code=415)
            try:
                if int(request.headers.get("content-length", "0")) > MAX_BODY:
                    return JSONResponse({"detail": "Request er for stort."}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Ugyldig Content-Length."}, status_code=400)
        started = time.perf_counter()
        response = await call_next(request)
        h = response.headers
        if path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
            h.setdefault("Pragma", "no-cache")
            h["Content-Security-Policy"] = API_CSP
            h["Vary"] = "Cookie, Sec-Fetch-Site"
        else:
            # Statiske frontend-filer: html caches aldrig; js/css/fonts med aktuel ?v=<hash> er uforanderlige
            # (ny deploy = nye URL'er), alt andet revalideres
            if path.startswith(("/js/", "/css/", "/fonts/")):
                versioned = asset_version is not None and request.query_params.get("v") == asset_version
                h["Cache-Control"] = "public, max-age=31536000, immutable" if versioned else "no-cache"
            else:
                h["Cache-Control"] = "no-store"
            h["Content-Security-Policy"] = WEB_CSP
            h["Reporting-Endpoints"] = 'csp="/api/csp-report"'
        h["Strict-Transport-Security"] = f"max-age={s.hsts_max_age}; includeSubDomains"
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = PERMISSIONS_POLICY
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        h["Cross-Origin-Embedder-Policy"] = "require-corp"
        # Ingen IP, cookies eller query i applikationsloggen
        log.info("%s %s %s %.0fms", request.method, path, response.status_code,
                 (time.perf_counter() - started) * 1000)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # Returnér ikke inputværdier tilbage (kan indeholde følsomme data)
        errs = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()][:20]
        return JSONResponse({"detail": "Ugyldigt input.", "errors": errs}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Uventet fejl på %s", request.url.path)
        return JSONResponse({"detail": "Intern fejl."}, status_code=500)

    @app.get("/api/health", include_in_schema=False)
    def health():
        ping()
        return {"status": "ok"}

    for r in (respondent, admin_auth, admin_org, admin_surveys, admin_dashboard, admin_demo,
              admin_analyses, admin_exports, system, public):
        app.include_router(r.router)
    # Frontend (vanilla HTML/JS) serveres af appen selv; TLS håndteres af ekstern reverse proxy.
    # Monteres sidst, så /api/* altid rammer routerne. html=True giver /admin/ -> admin/index.html.
    if FRONTEND_DIR.is_dir():
        static = VersionedStaticFiles(directory=FRONTEND_DIR, html=True)
        asset_version = static.version
        app.mount("/", static, name="frontend")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
