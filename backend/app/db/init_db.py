"""
CivicFix AI — Application Startup Database Helpers

Schema creation and DDL migrations are owned exclusively by Alembic (`backend/migrate.py`).
This module contains only idempotent runtime data initialization executed safely inside
the FastAPI lifespan context.
"""
import logging
from sqlalchemy.orm import Session
from app.models.entities import MunicipalDepartment

logger = logging.getLogger(__name__)

DEFAULT_DEPARTMENTS = [
    ("Roads and Public Works", "ROADS", "Road surface, potholes, bridges, and vehicular corridors"),
    ("Street Lighting & Electrical", "LIGHTING", "Illumination luminaires, streetlights, and electrical poles"),
    ("Sanitation & Solid Waste", "SANITATION", "Waste collection, litter removal, and public hygiene"),
    ("Water Supply & Distribution", "WATER", "Drinking water network, pipelines, and valves"),
    ("Drainage & Flood Management", "DRAINAGE", "Stormwater drains, culverts, and monsoon waterlogging"),
    ("Parks & Urban Forestry", "PARKS", "Urban tree cover, parks, and fallen arbor hazards"),
]


def ensure_default_departments(db: Session) -> None:
    """Idempotently inserts default municipal departments without issuing any schema DDL."""
    created = False
    for name, code, desc in DEFAULT_DEPARTMENTS:
        dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.code == code).first()
        if not dept:
            db.add(MunicipalDepartment(name=name, code=code, description=desc, is_active=True))
            created = True
    if created:
        db.commit()
