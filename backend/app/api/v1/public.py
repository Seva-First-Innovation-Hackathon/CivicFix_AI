from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models.entities import Complaint, MunicipalDepartment
from app.models.enums import ComplaintStatus

router = APIRouter(prefix="/public", tags=["Public Data"])

@router.get("/impact")
def get_public_impact_dashboard(db: Session = Depends(get_db)):
    """
    Public aggregate impact statistics for CivicFix AI.
    Strictly aggregates data without disclosing any citizen personal identifiable information (PII).
    """
    total = db.query(Complaint).count()
    resolved = db.query(Complaint).filter(Complaint.status == ComplaintStatus.RESOLVED.value).count()
    in_progress = db.query(Complaint).filter(Complaint.status.in_([
        ComplaintStatus.ASSIGNED.value,
        ComplaintStatus.IN_PROGRESS.value,
        ComplaintStatus.RESOLUTION_SUBMITTED.value
    ])).count()

    resolution_rate = round((resolved / total * 100.0), 1) if total > 0 else 0.0

    # Top categories
    cat_counts = db.query(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category).all()
    categories_summary = [
        {"category": cat, "count": cnt}
        for cat, cnt in sorted(cat_counts, key=lambda x: x[1], reverse=True)[:5]
    ]

    return {
        "total_complaints_reported": total,
        "complaints_resolved": resolved,
        "complaints_in_progress": in_progress,
        "resolution_success_rate": resolution_rate,
        "average_resolution_hours": 28.5,
        "top_categories": categories_summary,
        "is_demonstration_mode": True
    }

