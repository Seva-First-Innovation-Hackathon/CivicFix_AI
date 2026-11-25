from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    Complaint,
    DepartmentMembership,
    SLABreachEvent,
    User,
)
from app.models.enums import ComplaintStatus, NotificationType, UserRole
from app.services.audit import log_audit
from app.services.notifications.service import send_notification

logger = logging.getLogger(__name__)

CLOSED_SLA_STATUSES = (
    ComplaintStatus.RESOLVED.value,
    ComplaintStatus.CANCELLED.value,
    ComplaintStatus.REJECTED.value,
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_responsible_staff(db: Session, complaint: Complaint) -> List[User]:
    """
    Finds responsible municipal staff for SLA escalation alerts without altering assignment.
    Prefers officers assigned to complaint.department_id, falling back to active Government Admin.
    """
    recipients: List[User] = []
    if complaint.department_id:
        recipients = (
            db.query(User)
            .join(DepartmentMembership, DepartmentMembership.user_id == User.id)
            .filter(
                DepartmentMembership.department_id == complaint.department_id,
                User.is_active == True,
                User.role == UserRole.MUNICIPAL_MEMBER.value,
            )
            .all()
        )
    if not recipients:
        recipients = (
            db.query(User)
            .filter(User.role == UserRole.GOVERNMENT_ADMIN.value, User.is_active == True)
            .all()
        )
    return recipients


def monitor_sla_deadlines(
    db: Session,
    now: Optional[datetime] = None,
    enqueue_emails: bool = True,
) -> Dict[str, int]:
    """
    Detects overdue open complaints whose SLA deadline has elapsed, persists deduplicated
    SLABreachEvent records, sends in-app/outbox notifications to responsible municipal staff,
    and writes immutable audit entries without automatically changing priority or assignment.
    """
    current_time = _as_utc(now or datetime.now(timezone.utc))

    overdue_complaints = (
        db.query(Complaint)
        .filter(
            Complaint.sla_deadline.isnot(None),
            Complaint.sla_deadline < current_time,
            Complaint.status.notin_(CLOSED_SLA_STATUSES),
        )
        .order_by(Complaint.sla_deadline.asc())
        .all()
    )

    scanned_overdue = len(overdue_complaints)
    new_breaches = 0
    notifications_created = 0

    from app.services.jobs.queue import create_outbox_job

    for complaint in overdue_complaints:
        deadline_utc = _as_utc(complaint.sla_deadline)
        existing = (
            db.query(SLABreachEvent)
            .filter(
                SLABreachEvent.complaint_id == complaint.id,
                SLABreachEvent.sla_deadline == complaint.sla_deadline,
            )
            .first()
        )
        if existing:
            continue

        hours_overdue = round(max(0.0, (current_time - deadline_utc).total_seconds() / 3600.0), 2)
        recipients = _resolve_responsible_staff(db, complaint)

        breach = SLABreachEvent(
            complaint_id=complaint.id,
            priority=complaint.priority,
            sla_deadline=complaint.sla_deadline,
            detected_at=current_time,
            hours_overdue=hours_overdue,
            notification_sent=len(recipients) > 0,
            notified_user_count=len(recipients),
            notes=(
                f"SLA deadline ({complaint.priority}) missed by {hours_overdue:.1f}h "
                f"while in '{complaint.status}' status."
            ),
        )
        try:
            nested = db.begin_nested()
            db.add(breach)
            db.flush()
        except IntegrityError:
            nested.rollback()
            continue

        for officer in recipients:
            send_notification(
                db=db,
                user_id=officer.id,
                title=f"SLA Breach Alert: #{complaint.reference_number}",
                message=(
                    f"Complaint #{complaint.reference_number} ({complaint.priority}) exceeded its SLA target "
                    f"by {hours_overdue:.1f} hours while in status '{complaint.status}'."
                ),
                notification_type=NotificationType.SLA_BREACH.value,
                complaint_id=complaint.id,
                commit=False,
            )
            notifications_created += 1

            if enqueue_emails and officer.email:
                create_outbox_job(
                    db=db,
                    job_type="send_email",
                    dedup_key=f"sla_breach:{complaint.id}:{breach.id}:{officer.id}",
                    complaint_id=complaint.id,
                    payload={
                        "template": "sla_breach",
                        "to_email": officer.email,
                        "recipient_name": officer.full_name or "Municipal Officer",
                        "reference_number": complaint.reference_number,
                        "priority": complaint.priority,
                        "hours_overdue": hours_overdue,
                        "complaint_id": complaint.id,
                    },
                    commit=False,
                )

        log_audit(
            db=db,
            action="SLA_BREACH_DETECTED",
            entity_type="COMPLAINT",
            entity_id=complaint.id,
            user_id=None,
            details={
                "priority": complaint.priority,
                "sla_deadline": deadline_utc.isoformat(),
                "hours_overdue": hours_overdue,
                "notified_staff_count": len(recipients),
            },
            commit=False,
        )
        new_breaches += 1

    db.commit()
    if new_breaches:
        logger.warning(
            "SLA monitor recorded %d new breaches across %d overdue complaints.",
            new_breaches,
            scanned_overdue,
        )
    return {
        "scanned_overdue": scanned_overdue,
        "new_breaches_recorded": new_breaches,
        "notifications_created": notifications_created,
    }
