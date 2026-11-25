from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.entities import ComplaintAttachment
from app.services.storage.backends import (
    LocalStorageBackend,
    StorageBackend,
    StorageUnavailableError,
    compute_sha256_hex,
    normalize_object_key,
)

logger = logging.getLogger(__name__)


@dataclass
class MigrationReport:
    dry_run: bool
    delete_local_requested: bool
    total_candidates: int = 0
    uploaded_verified: int = 0
    already_exists_verified: int = 0
    missing_local_source: int = 0
    failed: int = 0
    local_deleted: int = 0
    errors: List[str] = field(default_factory=list)
    missing_attachment_ids: List[str] = field(default_factory=list)


def migrate_local_uploads_to_cloud(
    db: Session,
    local_backend: LocalStorageBackend,
    target_backend: StorageBackend,
    dry_run: bool = True,
    delete_local: bool = False,
    approve_local_deletion: bool = False,
    limit: Optional[int] = None,
) -> MigrationReport:
    """
    Idempotently migrates local ComplaintAttachment files to durable cloud object storage.
    - Dry-run enabled by default (zero writes to cloud or DB).
    - Interrupted runs recover safely by checking cloud existence & SHA-256 checksum first.
    - Local files are NEVER deleted unless BOTH delete_local=True and approve_local_deletion=True
      and cloud checksum + size verification succeeded.
    """
    if delete_local and not approve_local_deletion:
        raise ValueError(
            "Local file deletion requires explicit approve_local_deletion=True after cloud verification."
        )
    if not target_backend.is_durable:
        raise ValueError("Target migration backend must be a durable cloud object storage backend.")

    report = MigrationReport(dry_run=dry_run, delete_local_requested=delete_local)

    query = (
        db.query(ComplaintAttachment)
        .filter(ComplaintAttachment.storage_provider == "local")
        .order_by(ComplaintAttachment.created_at.asc())
    )
    if limit is not None and limit > 0:
        query = query.limit(limit)

    attachments = query.all()
    report.total_candidates = len(attachments)

    for att in attachments:
        try:
            object_key = normalize_object_key(att.storage_object_key or att.file_path)
        except ValueError as exc:
            report.failed += 1
            report.errors.append(f"Attachment {att.id}: invalid path '{att.file_path}': {exc}")
            continue

        # Check local file presence first
        try:
            local_path = local_backend.resolve_path(object_key)
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"Attachment {att.id}: {exc}")
            continue

        local_exists = local_path.is_file()
        local_bytes = local_path.read_bytes() if local_exists else b""
        local_checksum = compute_sha256_hex(local_bytes) if local_exists else None

        # Check whether target cloud already holds verified object (safe recovery after interruption)
        try:
            remote_meta = target_backend.head_metadata(object_key)
        except StorageUnavailableError as exc:
            report.failed += 1
            report.errors.append(f"Attachment {att.id}: remote head check failed: {exc}")
            continue

        if remote_meta and remote_meta.exists:
            checksum_matches = (
                (not local_checksum and remote_meta.size_bytes == att.file_size)
                or (remote_meta.sha256_checksum == local_checksum and remote_meta.size_bytes == len(local_bytes))
            )
            if checksum_matches:
                report.already_exists_verified += 1
                if not dry_run:
                    att.storage_provider = target_backend.provider_name
                    att.storage_object_key = object_key
                    att.sha256_checksum = remote_meta.sha256_checksum or local_checksum or att.sha256_checksum
                    att.storage_verification_status = "VERIFIED"
                    att.storage_migrated_at = datetime.now(timezone.utc)
                    db.commit()
                    if delete_local and approve_local_deletion and local_exists:
                        local_backend.delete(object_key)
                        report.local_deleted += 1
                continue

        if not local_exists:
            report.missing_local_source += 1
            report.missing_attachment_ids.append(att.id)
            logger.warning(
                "Legacy upload missing on local disk for attachment %s (complaint %s, key=%s).",
                att.id, att.complaint_id, object_key,
            )
            if not dry_run:
                att.storage_object_key = object_key
                att.storage_verification_status = "MISSING_SOURCE"
                db.commit()
            continue

        if dry_run:
            report.uploaded_verified += 1
            continue

        try:
            target_backend.put_bytes(
                object_key=object_key,
                data=local_bytes,
                content_type=att.mime_type,
                metadata={"attachment-id": att.id, "complaint-id": att.complaint_id},
            )
            verified_meta = target_backend.head_metadata(object_key)
            if (
                not verified_meta
                or verified_meta.size_bytes != len(local_bytes)
                or (verified_meta.sha256_checksum and verified_meta.sha256_checksum != local_checksum)
            ):
                raise StorageUnavailableError("Post-upload checksum/size verification mismatch")

            att.storage_provider = target_backend.provider_name
            att.storage_object_key = object_key
            att.sha256_checksum = local_checksum
            att.storage_verification_status = "VERIFIED"
            att.storage_migrated_at = datetime.now(timezone.utc)
            db.commit()
            report.uploaded_verified += 1

            if delete_local and approve_local_deletion:
                local_backend.delete(object_key)
                report.local_deleted += 1
        except Exception as exc:
            db.rollback()
            report.failed += 1
            report.errors.append(f"Attachment {att.id}: upload/verify failed: {exc}")

    return report
