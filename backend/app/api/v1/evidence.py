from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.entities import Complaint, ComplaintAttachment, User, WorkOrder
from app.models.enums import UserRole
from app.services.complaints.lifecycle import enforce_complaint_department_scope
from app.services.storage.backends import (
    StorageObjectMetadata,
    StorageObjectNotFoundError,
    StorageUnavailableError,
)
from app.services.storage.service import storage_service

router = APIRouter(prefix="/evidence", tags=["Evidence & Attachments"])


def resolve_evidence_user(
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """
    Extracts and authenticates user from Authorization header or short-lived token query param.
    """
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split(" ", 1)[1].strip()
    elif token:
        raw_token = token.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view evidence",
        )

    payload = decode_token(raw_token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated",
        )
    return user


def authorize_and_resolve_attachment(
    db: Session,
    user: User,
    attachment: Optional[ComplaintAttachment],
) -> tuple[ComplaintAttachment, StorageObjectMetadata]:
    """
    Single authoritative evidence access control gate:
    - Every served evidence file MUST have a valid ComplaintAttachment and linked Complaint.
    - Citizens: own complaints and non-internal evidence only.
    - Field Crews: only evidence on complaints or work orders assigned to them.
    - Municipal Members: strictly scoped to their own department membership.
    - Path traversal outside configured storage root/keys is blocked.
    - Works identically across local and private S3/R2 storage backends.
    """
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    complaint: Optional[Complaint] = attachment.complaint
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated complaint not found")

    if user.role == UserRole.CITIZEN.value:
        if complaint.citizen_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Cannot access evidence belonging to another citizen",
            )
        if attachment.is_internal:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Internal municipal investigation record",
            )

    elif user.role == UserRole.FIELD_CREW.value:
        has_work_order = (
            db.query(WorkOrder)
            .filter(WorkOrder.complaint_id == complaint.id, WorkOrder.crew_id == user.id)
            .first()
        )
        if complaint.assigned_crew_id != user.id and not has_work_order:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not assigned to this complaint",
            )

    elif user.role == UserRole.MUNICIPAL_MEMBER.value:
        enforce_complaint_department_scope(user, complaint)

    elif user.role != UserRole.GOVERNMENT_ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    provider = getattr(attachment, "storage_provider", None) or "local"
    object_key = getattr(attachment, "storage_object_key", None)

    try:
        meta = storage_service.head_object(
            file_path=attachment.file_path,
            storage_provider=provider,
            storage_object_key=object_key,
        )
    except HTTPException:
        raise
    except StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evidence storage service is temporarily unavailable",
        ) from exc

    if meta is None or not meta.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence file not found in storage")

    return attachment, meta


def serve_authorized_attachment_response(
    attachment: ComplaintAttachment,
    signed: bool = False,
):
    """
    Delivers authorized evidence safely either by streaming chunks through the backend
    (with no-store cache headers) or issuing a short-lived signed URL after RBAC authorization.
    """
    provider = getattr(attachment, "storage_provider", None) or "local"
    object_key = getattr(attachment, "storage_object_key", None)
    safe_filename = Path(attachment.file_name).name.replace('"', "")

    if signed:
        if provider == "local":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signed URLs are only available for cloud object storage backends",
            )
        try:
            signed_url = storage_service.generate_signed_url(
                file_path=attachment.file_path,
                storage_provider=provider,
                storage_object_key=object_key,
                download_filename=safe_filename,
                expires_in=settings.STORAGE_PRESIGNED_TTL_SECONDS,
            )
            return JSONResponse(
                content={
                    "signed_url": signed_url,
                    "expires_in": settings.STORAGE_PRESIGNED_TTL_SECONDS,
                },
                headers={"Cache-Control": "private, no-store"},
            )
        except StorageUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to generate signed evidence URL",
            ) from exc

    try:
        chunks = storage_service.stream_object(
            file_path=attachment.file_path,
            storage_provider=provider,
            storage_object_key=object_key,
        )
    except StorageObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence file not found in storage",
        ) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evidence storage service is temporarily unavailable",
        ) from exc

    return StreamingResponse(
        chunks,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{safe_filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{attachment_id}")
def get_secure_evidence(
    attachment_id: str,
    signed: bool = Query(False, description="When true and stored on R2/S3, returns short-lived presigned URL JSON"),
    user: User = Depends(resolve_evidence_user),
    db: Session = Depends(get_db),
):
    """Secured evidence delivery endpoint enforcing strict role/ownership authorization."""
    attachment = db.query(ComplaintAttachment).filter(ComplaintAttachment.id == attachment_id).first()
    att, _meta = authorize_and_resolve_attachment(db=db, user=user, attachment=attachment)
    return serve_authorized_attachment_response(att, signed=signed)
