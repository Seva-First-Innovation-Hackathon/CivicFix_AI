import json
from typing import Optional, Any
from sqlalchemy.orm import Session
from app.models.entities import AuditLog

def log_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: str,
    user_id: Optional[str] = None,
    details: Optional[Any] = None,
    ip_address: Optional[str] = None
) -> AuditLog:
    """Creates an immutable audit log entry for regulatory and administrative tracking."""
    details_str = None
    if details is not None:
        if isinstance(details, str):
            details_str = details
        else:
            try:
                details_str = json.dumps(details)
            except Exception:
                details_str = str(details)

    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details_str,
        ip_address=ip_address
    )
    db.add(log_entry)
    db.commit()
    return log_entry

