"""Authenticated web dashboard and JSON API (brief section 7)."""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .auth import LoginLimiter, authenticate, load_users
from .config import Settings
from .export import errors_csv, predictions_csv, results_json
from .jobs import JobManager
from .pipeline import Analyzer

log = logging.getLogger("audioeval.web")
STATIC = Path(__file__).parent / "static"
SESSION_MAX_AGE = 8 * 3600
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")


def create_app(settings: Settings | None = None, analyzer_factory=None) -> FastAPI:
    settings = settings or Settings.from_env()
    users = load_users()
    if not users:
        log.warning("AUDIOEVAL_USERS is empty: nobody can log in")
    secret = os.environ.get("AUDIOEVAL_SECRET_KEY")
    if not secret:
        log.warning("AUDIOEVAL_SECRET_KEY not set: using a random key; sessions end on restart")
        secret = secrets.token_urlsafe(32)
    secure_cookie = os.environ.get("AUDIOEVAL_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}
    limiter = LoginLimiter()
    jobs = JobManager(settings, analyzer_factory or (lambda: Analyzer(settings)))

    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.shutdown()

    app = FastAPI(title="AudioEval", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs
    app.add_middleware(SessionMiddleware, secret_key=secret, session_cookie="audioeval_session",
                       max_age=SESSION_MAX_AGE, same_site="strict", https_only=secure_cookie)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        if secure_cookie:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def current_user(request: Request) -> str:
        user = request.session.get("user")
        if not user or user not in users:
            raise HTTPException(401, "login required")
        return user

    def check_csrf(request: Request) -> None:
        token = request.session.get("csrf")
        if not token or not secrets.compare_digest(token, request.headers.get("x-csrf-token", "")):
            raise HTTPException(403, "invalid CSRF token")

    def owned_job(request: Request, job_id: str) -> dict:
        try:
            return jobs.get(job_id, current_user(request))
        except KeyError:
            raise HTTPException(404, "job not found") from None

    # ---- pages ---------------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def index(request: Request):
        if request.session.get("user") not in users:
            return RedirectResponse("/login", status_code=303)
        return FileResponse(STATIC / "index.html")

    @app.get("/login", include_in_schema=False)
    async def login_page():
        return FileResponse(STATIC / "login.html")

    # ---- health ---------------------------------------------------------
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        try:
            analyzer = await run_in_threadpool(lambda: jobs.analyzer)
        except Exception:
            log.exception("analyzer failed to initialize")
            return JSONResponse({"ready": False}, status_code=503)
        return {"ready": True, "method": analyzer.method}

    # ---- auth -----------------------------------------------------------
    @app.post("/api/login")
    async def login(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "expected JSON")
        body = await request.json()
        username = str(body.get("username", ""))[:128]
        password = str(body.get("password", ""))[:1024]
        ip = request.client.host if request.client else "unknown"
        keys = (f"user:{username}", f"ip:{ip}")
        if limiter.blocked(*keys):
            raise HTTPException(429, "too many failed attempts; try again later")
        ok = await run_in_threadpool(authenticate, users, username, password)
        if not ok:
            limiter.fail(*keys)
            raise HTTPException(401, "invalid username or password")
        limiter.reset(*keys)
        request.session.clear()
        request.session.update(user=username, csrf=secrets.token_urlsafe(32))
        return {"ok": True}

    @app.post("/api/logout")
    async def logout(request: Request):
        check_csrf(request)
        request.session.clear()
        return {"ok": True}

    @app.get("/api/me")
    async def me(request: Request):
        user = current_user(request)
        analyzer = jobs._analyzer
        return {"user": user, "csrf": request.session["csrf"], "version": __version__,
                "method": analyzer.method if analyzer else None,
                "limits": {"max_upload_mb": settings.max_upload_mb, "max_files": settings.max_files,
                           "retention_hours": settings.retention_hours}}

    # ---- jobs -------------------------------------------------------------
    @app.post("/api/jobs")
    async def create_job(request: Request):
        user = current_user(request)
        check_csrf(request)
        length = int(request.headers.get("content-length") or 0)
        if length > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"upload larger than {settings.max_upload_mb} MB")
        form = await request.form(max_files=settings.max_files + 1, max_fields=settings.max_files + 10)
        try:
            files = form.getlist("files")
            paths = form.getlist("paths")
            uploads = []
            for i, f in enumerate(files):
                if not hasattr(f, "file"):
                    continue
                name = paths[i] if i < len(paths) and isinstance(paths[i], str) and paths[i] else f.filename
                uploads.append((name or f"upload_{i}", f.file))
            if not uploads:
                raise HTTPException(400, "no files uploaded")
            job = await run_in_threadpool(jobs.create, user, uploads)
        finally:
            await form.close()
        return job_view(job)

    @app.get("/api/jobs")
    async def list_jobs(request: Request):
        user = current_user(request)
        return [{k: j.get(k) for k in ("id", "created", "status", "summary", "manifest", "has_labels")} for j in jobs.list(user)]

    @app.get("/api/jobs/{job_id}")
    async def get_job(request: Request, job_id: str):
        return job_view(owned_job(request, job_id))

    @app.post("/api/jobs/{job_id}/resume")
    async def resume_job(request: Request, job_id: str):
        owned_job(request, job_id)
        check_csrf(request)
        return job_view(jobs.resume(job_id, current_user(request)))

    @app.get("/api/jobs/{job_id}/download/{kind}")
    async def download(request: Request, job_id: str, kind: str):
        job = owned_job(request, job_id)
        if kind == "predictions.csv":
            return PlainTextResponse(predictions_csv(job["items"]), media_type="text/csv", headers=_attachment(job_id, kind))
        if kind == "errors.csv":
            return PlainTextResponse(errors_csv(job["items"]), media_type="text/csv", headers=_attachment(job_id, kind))
        if kind == "results.json":
            return Response(results_json(job), media_type="application/json", headers=_attachment(job_id, kind))
        raise HTTPException(404, "unknown download")

    return app


def _attachment(job_id: str, kind: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="audioeval_{job_id}_{kind}"'}


def job_view(job: dict) -> dict:
    items = [{k: it.get(k) for k in ("name", "status", "error", "warnings", "in_manifest", "prediction", "label")}
             | {"field_confidence": (it.get("details") or {}).get("field_confidence"),
                "duration_s": ((it.get("details") or {}).get("audio") or {}).get("duration_s"),
                "processing_s": ((it.get("details") or {}).get("timings") or {}).get("total_s")}
             for it in job["items"]]
    return {k: job.get(k) for k in ("id", "created", "finished", "status", "errors", "warnings", "skipped",
                                     "manifest", "has_labels", "summary", "score", "method")} | {"items": items}
