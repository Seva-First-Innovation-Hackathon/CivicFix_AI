from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Complaint, ResolutionVerification
from app.models.enums import ComplaintStatus

router = APIRouter(prefix="/public", tags=["Public Data"])


def _compute_average_resolution_hours(db: Session) -> float | None:
    """
    Calculates real mean turnaround duration in hours across resolved complaints.
    Uses verified resolution timestamp when available (is_satisfied=True), falling
    back to complaint.updated_at. Returns None when no valid resolved data exists.
    """
    resolved_rows = (
        db.query(Complaint)
        .filter(Complaint.status == ComplaintStatus.RESOLVED.value)
        .all()
    )
    if not resolved_rows:
        return None

    satisfied_times: dict[str, object] = {}
    verif_rows = (
        db.query(ResolutionVerification.complaint_id, func.max(ResolutionVerification.verified_at))
        .filter(ResolutionVerification.is_satisfied == True)
        .group_by(ResolutionVerification.complaint_id)
        .all()
    )
    for comp_id, verified_at in verif_rows:
        satisfied_times[comp_id] = verified_at

    durations_seconds: list[float] = []
    for comp in resolved_rows:
        end_dt = satisfied_times.get(comp.id) or comp.updated_at
        if end_dt and comp.created_at:
            diff_sec = (end_dt - comp.created_at).total_seconds()
            if diff_sec >= 0:
                durations_seconds.append(diff_sec)

    if not durations_seconds:
        return None

    mean_hours = sum(durations_seconds) / (len(durations_seconds) * 3600.0)
    return round(mean_hours, 1)


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
        ComplaintStatus.WORK_COMPLETED_PENDING_REVIEW.value,
        ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value,
    ])).count()

    resolution_rate = round((resolved / total * 100.0), 1) if total > 0 else 0.0
    avg_hours = _compute_average_resolution_hours(db)

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
        "average_resolution_hours": avg_hours,
        "top_categories": categories_summary,
        "is_demonstration_mode": settings.ENVIRONMENT.lower() != "production",
    }
