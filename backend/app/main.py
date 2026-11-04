from typing import Optional
from fastapi import FastAPI, Depends, status, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import os

from app.core.config import settings
from app.db.session import engine, Base, get_db
from app.api.v1.api import api_router
from app.models.entities import MunicipalDepartment, ComplaintAttachment, WorkOrder
from app.models.enums import UserRole
from app.api.v1.evidence import resolve_evidence_user
from app.services.storage.service import storage_service

from app.db.init_db import ensure_schema_upgrades

# Initialize DB tables and apply schema upgrades
ensure_schema_upgrades()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure default municipal departments exist on application bootstrap
    db = next(get_db())
    try:
        default_depts = [
            ("Roads and Public Works", "ROADS", "Road surface, potholes, bridges, and vehicular corridors"),
            ("Street Lighting & Electrical", "LIGHTING", "Illumination luminaires, streetlights, and electrical poles"),
            ("Sanitation & Solid Waste", "SANITATION", "Waste collection, litter removal, and public hygiene"),
            ("Water Supply & Distribution", "WATER", "Drinking water network, pipelines, and valves"),
            ("Drainage & Flood Management", "DRAINAGE", "Stormwater drains, culverts, and monsoon waterlogging"),
            ("Parks & Urban Forestry", "PARKS", "Urban tree cover, parks, and fallen arbor hazards"),
        ]
        for name, code, desc in default_depts:
            dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.code == code).first()
            if not dept:
                new_d = MunicipalDepartment(name=name, code=code, description=desc, is_active=True)
                db.add(new_d)
        db.commit()
    finally:
        db.close()
    yield

from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter, rate_limit_exceeded_handler

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Intelligent civic complaint reporting, prioritization, assignment, resolution, and verification platform for municipalities.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Register Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS or ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Secure uploads directory - Authenticated delivery only
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

@app.get("/uploads/{folder}/{filename}", tags=["Evidence & Attachments"])
def get_authorized_upload_file(
    folder: str,
    filename: str,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Secured evidence delivery: rejects anonymous access and enforces ownership/role permissions."""
    user = resolve_evidence_user(token=token, authorization=authorization, db=db)
    rel_path = f"/uploads/{folder}/{filename}"
    attachment = db.query(ComplaintAttachment).filter(ComplaintAttachment.file_path == rel_path).first()
    if not attachment:
        abs_path = storage_service.get_absolute_path(rel_path)
        if abs_path.exists() and user.role in [UserRole.GOVERNMENT_ADMIN.value, UserRole.MUNICIPAL_MEMBER.value]:
            return FileResponse(path=str(abs_path))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    complaint = attachment.complaint
    if complaint:
        if user.role == UserRole.CITIZEN.value:
            if complaint.citizen_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
            if attachment.is_internal:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Internal staff record")
        elif user.role == UserRole.FIELD_CREW.value:
            has_wo = db.query(WorkOrder).filter(WorkOrder.complaint_id == complaint.id, WorkOrder.crew_id == user.id).first()
            if complaint.assigned_crew_id != user.id and not has_wo:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        elif user.role == UserRole.MUNICIPAL_MEMBER.value:
            if complaint.department_id and user.department_membership:
                if user.department_membership.department_id != complaint.department_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    abs_path = storage_service.get_absolute_path(rel_path)
    if not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical evidence file not found on disk")

    return FileResponse(path=str(abs_path), media_type=attachment.mime_type, filename=attachment.file_name)

# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """System and service health probe."""
    try:
        db.execute(Base.metadata.tables["users"].select().limit(1))
        db_status = "connected"
    except Exception as e:
        db_status = "disconnected"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "ai_provider": settings.AI_PROVIDER,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/health/db", tags=["Health"])
@app.get("/api/v1/health/db", tags=["Health"])
def health_check_db(db: Session = Depends(get_db)):
    """Database connectivity status probe without leaking credentials or internal details."""
    try:
        db.execute(Base.metadata.tables["users"].select().limit(1))
        return {
            "status": "healthy",
            "database": "connected",
            "dialect": engine.dialect.name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Database connectivity check failed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }



