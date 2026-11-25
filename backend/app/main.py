from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import time
from typing import Optional
import uuid

from fastapi import FastAPI, Depends, Query, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core import limiter as limiter_module
from app.core.limiter import limiter, rate_limit_exceeded_handler
from app.db.session import engine, Base, get_db, SessionLocal
from app.db.init_db import ensure_default_departments
from app.api.v1.api import api_router
from app.api.v1.evidence import (
    resolve_evidence_user,
    authorize_and_resolve_attachment,
    serve_authorized_attachment_response,
)
from app.models.entities import ComplaintAttachment
from app.services.ai.service import recover_interrupted_ai_jobs
from app.services.jobs.queue import check_queue_and_worker_health, get_queue_status_summary, recover_stale_running_jobs
from app.services.storage.service import storage_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize local storage directories when using local storage (never on module import)
    if (settings.STORAGE_BACKEND or "local").lower() == "local":
        storage_service.upload_dir = settings.UPLOAD_DIR
        storage_service.ensure_local_directories()

    db = SessionLocal()
    try:
        ensure_default_departments(db)
    except Exception as exc:
        logger.warning("Skipping default department initialization (verify migrations are applied): %s", exc)
        db.rollback()
    finally:
        db.close()

    recover_stale_running_jobs()
    recover_interrupted_ai_jobs()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Intelligent civic complaint reporting, prioritization, assignment, resolution, and verification platform for municipalities.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Register Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Strictly validated explicit CORS allowlist (no wildcard regex across external apps)
cors_origins = settings.get_effective_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-_]{4,64}$")


@app.middleware("http")
async def attach_request_correlation_id(request: Request, call_next):
    """Propagates X-Request-ID and emits minimal non-PII structured operational timing logs."""
    incoming_rid = request.headers.get("X-Request-ID", "")
    request_id = incoming_rid if _SAFE_REQUEST_ID.match(incoming_rid) else uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    response.headers["X-Request-ID"] = request_id
    if not request.url.path.startswith("/health"):
        logger.info(
            "http_request request_id=%s method=%s path=%s status=%d duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    return response


@app.get("/uploads/{folder}/{filename}", tags=["Evidence & Attachments"])
def get_authorized_upload_file(
    folder: str,
    filename: str,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    signed: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Secured evidence delivery: rejects anonymous and unlinked/unregistered files,
    validates folder/path safety, and enforces strict RBAC/ownership permissions.
    """
    if folder not in storage_service.ALLOWED_FOLDERS or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload path")

    user = resolve_evidence_user(token=token, authorization=authorization, db=db)
    rel_path = f"/uploads/{folder}/{filename}"
    attachment = db.query(ComplaintAttachment).filter(ComplaintAttachment.file_path == rel_path).first()
    att, _meta = authorize_and_resolve_attachment(db=db, user=user, attachment=attachment)
    return serve_authorized_attachment_response(att, signed=signed)


# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """System and service health probe."""
    try:
        db.execute(Base.metadata.tables["users"].select().limit(1))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    storage_backend = (settings.STORAGE_BACKEND or "local").lower()
    is_prod = settings.ENVIRONMENT.lower() == "production"
    queue_health = check_queue_and_worker_health(db)
    storage_durable = storage_service.is_durable()

    # In production, never report 'healthy' if durable queue/worker or Redis is degraded
    if db_status != "connected":
        overall_status = "degraded"
    elif is_prod and (not queue_health["durable_queue"] or not storage_durable):
        overall_status = "degraded"
    else:
        overall_status = "healthy" if queue_health["status"] == "healthy" else "degraded"

    return {
        "status": overall_status,
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "ai_provider": settings.AI_PROVIDER,
        "storage": {
            "backend": storage_backend,
            "durable": storage_durable,
            "ephemeral_warning": bool(is_prod and storage_backend == "local"),
        },
        "queue": {
            **queue_health["queue"],
            "durable": queue_health["durable_queue"],
            "redis_connected": queue_health["redis_connected"],
            "worker_alive": queue_health["worker_alive"],
        },
        "rate_limiter_mode": queue_health["rate_limiter_mode"],
        "warnings": queue_health["warnings"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health/queue", tags=["Health"])
@app.get("/api/v1/health/queue", tags=["Health"])
def health_check_queue(db: Session = Depends(get_db)):
    """Queue outbox backlog, Redis, and worker readiness probe without exposing Redis credentials."""
    queue_health = check_queue_and_worker_health(db)
    return {
        **queue_health,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/db", tags=["Health"])
@app.get("/api/v1/health/db", tags=["Health"])
def health_check_db(db: Session = Depends(get_db)):
    """Database connectivity status probe without leaking credentials or internal details."""
    try:
        db.execute(Base.metadata.tables["users"].select().limit(1))
        postgis_version = None
        spatial_gist_index = False
        if engine.dialect.name == "postgresql":
            try:
                res = db.execute(text("SELECT PostGIS_Version();")).scalar()
                postgis_version = str(res)
                idx = db.execute(
                    text("SELECT to_regclass('public.ix_complaints_location_gist');")
                ).scalar()
                spatial_gist_index = bool(idx)
            except Exception:
                postgis_version = "not_installed"

        return {
            "status": "healthy",
            "database": "connected",
            "dialect": engine.dialect.name,
            "postgis": postgis_version,
            "spatial_gist_index": spatial_gist_index if engine.dialect.name == "postgresql" else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Database connectivity check failed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
