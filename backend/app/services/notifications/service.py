from typing import Optional
from sqlalchemy.orm import Session
from app.models.entities import Notification, NotificationPreference
from app.models.enums import NotificationType

def send_notification(
    db: Session,
    user_id: str,
    title: str,
    message: str,
    notification_type: str = NotificationType.SYSTEM.value,
    complaint_id: Optional[str] = None
) -> Notification:
    """Dispatches in-app notification and respects user notification preferences."""
    pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).first()
    
    if pref and not pref.in_app_enabled:
        return None

    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        complaint_id=complaint_id,
        is_read=False
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification

