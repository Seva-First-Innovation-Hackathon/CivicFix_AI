from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.complaints import router as complaints_router
from app.api.v1.admin import router as admin_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.public import router as public_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.maps import router as maps_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(complaints_router)
api_router.include_router(admin_router)
api_router.include_router(notifications_router)
api_router.include_router(public_router)
api_router.include_router(evidence_router)
api_router.include_router(maps_router)

