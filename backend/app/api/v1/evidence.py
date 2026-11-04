import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import decode_token
from app.models.entities import ComplaintAttachment, Complaint, User, WorkOrder
from app.models.enums import UserRole
from app.services.storage.service import storage_service

router = APIRouter(prefix="/evidence", tags=["Evidence & Attachments"])

def resolve_evidence_user(
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Extracts and authenticates user from either Authorization header or short-lived token query param.
    Enables secure <img> preview without exposing public static directories.
    """
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split(" ")[1]
    elif token:
        raw_token = token

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view evidence"
        )

    payload = decode_token(raw_token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token"
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated"
        )
    return user

@router.get("/{attachment_id}")
def get_secure_evidence(
    attachment_id: str,
    user: User = Depends(resolve_evidence_user),
    db: Session = Depends(get_db)
):
    """
    Secured evidence delivery endpoint enforcing strict authorization:
    - Citizens: Can only access non-internal photos attached to their own complaints.
    - Field Crews: Can only access evidence attached to complaints or work orders assigned to them.
    - Municipal Members: Can only access evidence within their authorized department.
    - Government Admin: Global administrative audit access.
    """
    attachment = db.query(ComplaintAttachment).filter(ComplaintAttachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    complaint = attachment.complaint
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated complaint not found")

    # Authorization enforcement
    if user.role == UserRole.CITIZEN.value:
        if complaint.citizen_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Cannot access evidence belonging to another citizen"
            )
        if attachment.is_internal:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Internal municipal investigation record"
            )

    elif user.role == UserRole.FIELD_CREW.value:
        # Check if crew is assigned directly or has an assigned work order
        has_work_order = db.query(WorkOrder).filter(
            WorkOrder.complaint_id == complaint.id,
            WorkOrder.crew_id == user.id
        ).first()
        if complaint.assigned_crew_id != user.id and not has_work_order:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not assigned to this complaint"
            )

    elif user.role == UserRole.MUNICIPAL_MEMBER.value:
        # Department scoping
        if complaint.department_id and user.department_membership:
            if user.department_membership.department_id != complaint.department_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Evidence belongs to a different municipal department"
                )

    abs_path = storage_service.get_absolute_path(attachment.file_path)
    if not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical file not found on disk")

    return FileResponse(
        path=str(abs_path),
        media_type=attachment.mime_type,
        filename=attachment.file_name
    )

