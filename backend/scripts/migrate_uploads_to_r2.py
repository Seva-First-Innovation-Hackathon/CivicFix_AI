"""
CLI utility to migrate legacy local attachment files to configured Cloudflare R2 / S3 storage.

Default mode is --dry-run (safe inspection, zero writes, zero deletions).
Deleting local files requires BOTH --execute AND --delete-local AND --confirm-delete-local.
"""
import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.storage.backends import LocalStorageBackend
from app.services.storage.migrator import migrate_local_uploads_to_cloud
from app.services.storage.service import storage_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate local CivicFix uploads to R2/S3 object storage.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform actual upload and database metadata updates (default is dry-run).",
    )
    parser.add_argument(
        "--delete-local",
        action="store_true",
        help="Delete verified local source files after confirmed cloud upload.",
    )
    parser.add_argument(
        "--confirm-delete-local",
        action="store_true",
        help="Explicit second acknowledgment required before removing any local source files.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum attachments to process.")
    args = parser.parse_args()

    cloud_backend = storage_service.get_cloud_backend()
    if cloud_backend is None:
        print("ERROR: R2/S3 storage backend is not configured (set STORAGE_BACKEND=r2 and R2_* env vars).", file=sys.stderr)
        return 1

    local_backend = LocalStorageBackend(settings.UPLOAD_DIR)
    db = SessionLocal()
    try:
        report = migrate_local_uploads_to_cloud(
            db=db,
            local_backend=local_backend,
            target_backend=cloud_backend,
            dry_run=not args.execute,
            delete_local=args.delete_local,
            approve_local_deletion=args.confirm_delete_local,
            limit=args.limit,
        )
        print(json.dumps({
            "dry_run": report.dry_run,
            "total_candidates": report.total_candidates,
            "uploaded_verified": report.uploaded_verified,
            "already_exists_verified": report.already_exists_verified,
            "missing_local_source": report.missing_local_source,
            "failed": report.failed,
            "local_deleted": report.local_deleted,
            "missing_attachment_ids": report.missing_attachment_ids,
            "errors": report.errors,
        }, indent=2))
        return 0 if report.failed == 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
