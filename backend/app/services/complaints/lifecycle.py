import logging
from typing import Optional, Dict, List
from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.entities import Complaint, ComplaintStatusHistory, User, Notification
from app.models.enums import UserRole, ComplaintStatus, NotificationType
from app.services.audit import log_audit
from app.services.notifications.service import send_notification
from app.services.email.service import email_service

logger = logging.getLogger(__name__)

# Permitted server-side complaint lifecycle state machine
VALID_TRANSITIONS: Dict[str, List[str]] = {
    ComplaintStatus.SUBMITTED.value: [
        ComplaintStatus.AI_ANALYSIS_PENDING.value,
        ComplaintStatus.UNDER_REVIEW.value,
        ComplaintStatus.VERIFIED.value,
        ComplaintStatus.CANCELLED.value,
        ComplaintStatus.REJECTED.value,
        ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value,
    ],
    ComplaintStatus.AI_ANALYSIS_PENDING.value: [
        ComplaintStatus.UNDER_REVIEW.value,
        ComplaintStatus.VERIFIED.value,
        ComplaintStatus.CANCELLED.value,
    ],
    ComplaintStatus.UNDER_REVIEW.value: [
        ComplaintStatus.VERIFIED.value,
        ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value,
        ComplaintStatus.ASSIGNED.value,
        ComplaintStatus.REJECTED.value,
        ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value,
        ComplaintStatus.CANCELLED.value,
    ],
    ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value: [
        ComplaintStatus.UNDER_REVIEW.value,
        ComplaintStatus.CANCELLED.value,
        ComplaintStatus.REJECTED.value,
    ],
    ComplaintStatus.VERIFIED.value: [
        ComplaintStatus.ASSIGNED.value,
        ComplaintStatus.IN_PROGRESS.value,
        ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value,
        ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value,
        ComplaintStatus.CANCELLED.value,
        ComplaintStatus.REJECTED.value,
    ],
    ComplaintStatus.ASSIGNED.value: [
        ComplaintStatus.IN_PROGRESS.value,
        ComplaintStatus.UNDER_REVIEW.value,
        ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value,
        ComplaintStatus.CANCELLED.value,
    ],
    ComplaintStatus.IN_PROGRESS.value: [
        ComplaintStatus.WORK_COMPLETED_PENDING_REVIEW.value,
        ComplaintStatus.ASSIGNED.value,  # When blocked or reassigned
        ComplaintStatus.UNDER_REVIEW.value,
        ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value,  # Legacy shortcut support
    ],
    ComplaintStatus.WORK_COMPLETED_PENDING_REVIEW.value: [
        ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value,
        ComplaintStatus.IN_PROGRESS.value,  # When evidence returned for rework
        ComplaintStatus.RESOLVED.value,     # Admin override only
    ],
    ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value: [
        ComplaintStatus.RESOLVED.value,
        ComplaintStatus.REOPENED.value,
    ],
    ComplaintStatus.REOPENED.value: [
        ComplaintStatus.UNDER_REVIEW.value,
        ComplaintStatus.VERIFIED.value,
        ComplaintStatus.ASSIGNED.value,
        ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value,
    ],
    ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value: [
        ComplaintStatus.UNDER_REVIEW.value,
        ComplaintStatus.VERIFIED.value,
        ComplaintStatus.ASSIGNED.value,
        ComplaintStatus.REJECTED.value,
    ],
    ComplaintStatus.REJECTED.value: [
        ComplaintStatus.UNDER_REVIEW.value,  # Admin reopen/appeal
    ],
    ComplaintStatus.CANCELLED.value: [],
    ComplaintStatus.RESOLVED.value: [
        ComplaintStatus.REOPENED.value,      # Citizen dispute window
    ],
}

def validate_transition(
    complaint: Complaint,
    target_status: str,
    user: User,
    reason: Optional[str] = None
) -> None:
    """
    Strict server-side validation enforcing:
    1. Legal status transitions according to the state machine.
    2. Role-based authority rules.
    3. Ownership and department boundaries.
    """
    current_status = complaint.status

    if current_status == target_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Complaint is already in '{current_status}' status"
        )

    allowed_destinations = VALID_TRANSITIONS.get(current_status, [])
    if target_status not in allowed_destinations and user.role != UserRole.GOVERNMENT_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Illegal transition: Cannot move complaint from '{current_status}' to '{target_status}'. Allowed transitions: {allowed_destinations}"
        )

    # Role-based constraints
    if user.role == UserRole.CITIZEN.value:
        if complaint.citizen_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not own this complaint"
            )
        
        citizen_allowed = {
            (ComplaintStatus.SUBMITTED.value, ComplaintStatus.CANCELLED.value),
            (ComplaintStatus.UNDER_REVIEW.value, ComplaintStatus.CANCELLED.value),
            (ComplaintStatus.VERIFIED.value, ComplaintStatus.CANCELLED.value),
            (ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value, ComplaintStatus.CANCELLED.value),
            (ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value, ComplaintStatus.UNDER_REVIEW.value),
            (ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value, ComplaintStatus.RESOLVED.value),
            (ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value, ComplaintStatus.REOPENED.value),
            (ComplaintStatus.RESOLVED.value, ComplaintStatus.REOPENED.value),
        }
        if (current_status, target_status) not in citizen_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Citizens cannot perform transition '{current_status}' -> '{target_status}'"
            )

    elif user.role == UserRole.FIELD_CREW.value:
        # Field crew can only update their assigned complaints
        if complaint.assigned_crew_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: This complaint is not assigned to your crew"
            )
        
        crew_allowed = {
            (ComplaintStatus.ASSIGNED.value, ComplaintStatus.IN_PROGRESS.value),
            (ComplaintStatus.IN_PROGRESS.value, ComplaintStatus.WORK_COMPLETED_PENDING_REVIEW.value),
            (ComplaintStatus.IN_PROGRESS.value, ComplaintStatus.ASSIGNED.value),
            (ComplaintStatus.IN_PROGRESS.value, ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value), # legacy support
        }
        if (current_status, target_status) not in crew_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Field crews cannot perform transition '{current_status}' -> '{target_status}'. Field crews cannot approve resolution or reject complaints."
            )

    elif user.role == UserRole.MUNICIPAL_MEMBER.value:
        # Department scoping: if complaint has a department assigned, member must belong to it
        if complaint.department_id and user.department_membership:
            if user.department_membership.department_id != complaint.department_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You do not have jurisdiction over complaints belonging to another department"
                )

        # Municipal member cannot directly mark RESOLVED without citizen verification
        if target_status == ComplaintStatus.RESOLVED.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Municipal members cannot directly mark complaints as RESOLVED without citizen verification. Use Government Admin override if required."
            )

    # Mandatory reason checks
    if target_status in [ComplaintStatus.REJECTED.value, ComplaintStatus.CANCELLED.value, ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value, ComplaintStatus.REOPENED.value]:
        if not reason or len(reason.strip()) < 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A documented reason of at least 5 characters is required for status '{target_status}'"
            )

def execute_transition(
    db: Session,
    complaint: Complaint,
    target_status: str,
    user: User,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None
) -> Complaint:
    """
    Executes a validated transition, creates immutable audit & history records,
    and enqueues in-app and email notifications.
    """
    validate_transition(complaint, target_status, user, reason)

    old_status = complaint.status
    complaint.status = target_status

    if target_status == ComplaintStatus.CANCELLED.value:
        complaint.cancellation_reason = reason
    elif target_status == ComplaintStatus.REJECTED.value:
        complaint.rejection_reason = reason
    elif target_status == ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value:
        complaint.investigation_notes = reason
    elif target_status == ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value:
        complaint.clarification_requested = reason

    # Immutable history entry
    history = ComplaintStatusHistory(
        complaint_id=complaint.id,
        from_status=old_status,
        to_status=target_status,
        changed_by_id=user.id,
        change_reason=reason or f"Transitioned to {target_status}",
        notes=notes
    )
    db.add(history)

    # Audit log
    log_audit(
        db=db,
        action="COMPLAINT_STATUS_TRANSITION",
        entity_type="COMPLAINT",
        entity_id=complaint.id,
        user_id=user.id,
        details={
            "from_status": old_status,
            "to_status": target_status,
            "reason": reason,
            "notes": notes
        }
    )

    # Notification mappings
    public_status_titles = {
        ComplaintStatus.VERIFIED.value: "Complaint Verified & Prioritized",
        ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value: "Action Required: More Information Requested",
        ComplaintStatus.ASSIGNED.value: "Complaint Assigned to Department",
        ComplaintStatus.IN_PROGRESS.value: "Work in Progress",
        ComplaintStatus.WORK_COMPLETED_PENDING_REVIEW.value: "Field Work Completed (Under Review)",
        ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value: "Repair Completed — Please Verify",
        ComplaintStatus.RESOLVED.value: "Complaint Resolved",
        ComplaintStatus.REOPENED.value: "Complaint Reopened",
        ComplaintStatus.REJECTED.value: "Complaint Decision: Not Eligible / Rejected",
        ComplaintStatus.CANCELLED.value: "Complaint Cancelled",
    }

    if target_status in public_status_titles and complaint.citizen_id:
        title = public_status_titles[target_status]
        msg = f"Your complaint #{complaint.reference_number} is now in '{target_status}' status."
        if reason:
            msg += f" Details: {reason}"

        send_notification(
            db=db,
            user_id=complaint.citizen_id,
            title=title,
            message=msg,
            notification_type=NotificationType.PROGRESS_UPDATE.value,
            complaint_id=complaint.id
        )

        # Enqueue async email if citizen has email
        if background_tasks and complaint.citizen and complaint.citizen.email:
            background_tasks.add_task(
                email_service.send_status_update,
                to_email=complaint.citizen.email,
                recipient_name=complaint.citizen.full_name or "Citizen",
                reference_number=complaint.reference_number,
                old_status=old_status,
                new_status=target_status,
                reason=reason,
                complaint_id=complaint.id
            )

    db.commit()
    db.refresh(complaint)
    return complaint

