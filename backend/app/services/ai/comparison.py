import asyncio
import json
import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Complaint, ComplaintAttachment, ResolutionComparison, User
from app.services.ai.base import RepairComparisonResult
from app.services.ai.service import ai_service
from app.services.audit import log_audit
from app.services.storage.backends import StorageObjectNotFoundError, StorageUnavailableError
from app.services.storage.service import storage_service

logger = logging.getLogger(__name__)

BEFORE_TYPES = {"CITIZEN_ORIGINAL", "BEFORE_REPAIR"}
AFTER_TYPES = {"AFTER_REPAIR", "RESOLUTION_EVIDENCE"}


def _select_attachment_pair(
    complaint: Complaint,
    before_id: Optional[str] = None,
    after_id: Optional[str] = None,
) -> tuple[ComplaintAttachment, ComplaintAttachment]:
    by_id = {att.id: att for att in complaint.attachments}

    if before_id:
        before_att = by_id.get(before_id)
    else:
        before_candidates = [a for a in complaint.attachments if a.attachment_type in BEFORE_TYPES]
        before_att = before_candidates[-1] if before_candidates else None

    if after_id:
        after_att = by_id.get(after_id)
    else:
        after_candidates = [a for a in complaint.attachments if a.attachment_type in AFTER_TYPES]
        after_att = after_candidates[-1] if after_candidates else None

    if not before_att or not after_att:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both a before-repair citizen/original image and an after-repair/resolution image are required for comparison.",
        )
    if before_att.id == after_att.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Before and after evidence attachments must be distinct.",
        )
    return before_att, after_att


async def compare_complaint_evidence(
    db: Session,
    complaint: Complaint,
    requested_by: User,
    before_attachment_id: Optional[str] = None,
    after_attachment_id: Optional[str] = None,
) -> ResolutionComparison:
    """
    Generates an advisory AI visual diff between before-repair and after-repair images.
    Never automatically approves or resolves any complaint; municipal staff verification remains mandatory.
    """
    before_att, after_att = _select_attachment_pair(complaint, before_attachment_id, after_attachment_id)

    try:
        before_bytes = storage_service.read_bytes(
            file_path=before_att.file_path,
            storage_provider=getattr(before_att, "storage_provider", "local"),
            storage_object_key=getattr(before_att, "storage_object_key", None),
        )
        after_bytes = storage_service.read_bytes(
            file_path=after_att.file_path,
            storage_provider=getattr(after_att, "storage_provider", "local"),
            storage_object_key=getattr(after_att, "storage_object_key", None),
        )
    except StorageObjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence image object missing from storage") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Evidence storage temporarily unavailable") from exc

    provider, provider_name, _ = ai_service.get_provider()
    timeout_sec = max(5, settings.AI_REQUEST_TIMEOUT_SECONDS or 30)

    try:
        result: RepairComparisonResult = await asyncio.wait_for(
            provider.compare_before_after_images(
                before_bytes=before_bytes,
                after_bytes=after_bytes,
                context_title=complaint.title,
            ),
            timeout=timeout_sec,
        )
    except Exception as exc:
        logger.warning("Repair comparison via %s failed safely for complaint %s: %s", provider_name, complaint.id, exc)
        result = await ai_service.mock_provider.compare_before_after_images(
            before_bytes=before_bytes,
            after_bytes=after_bytes,
            context_title=complaint.title,
        )
        result.uncertainty_notes = f"Primary visual comparison unavailable; fallback structural inspection applied. {result.uncertainty_notes}"

    record = ResolutionComparison(
        complaint_id=complaint.id,
        before_attachment_id=before_att.id,
        after_attachment_id=after_att.id,
        requested_by_id=requested_by.id,
        provider=result.provider,
        model_name=result.model_name,
        changes_detected=result.changes_detected,
        visual_differences_json=json.dumps(result.visual_differences),
        summary=result.summary,
        uncertainty_notes=result.uncertainty_notes,
        requires_human_review=True,
    )
    db.add(record)
    db.flush()

    log_audit(
        db=db,
        action="EVIDENCE_BEFORE_AFTER_COMPARED",
        entity_type="RESOLUTION_COMPARISON",
        entity_id=record.id,
        user_id=requested_by.id,
        details={
            "complaint_id": complaint.id,
            "before_attachment_id": before_att.id,
            "after_attachment_id": after_att.id,
            "changes_detected": result.changes_detected,
            "requires_human_review": True,
        },
        commit=False,
    )
    db.commit()
    db.refresh(record)
    return record
