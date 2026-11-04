from typing import Generator, Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import decode_token
from app.models.entities import User
from app.models.enums import UserRole
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False
)

def get_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme)
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
        
    return user

def require_roles(*allowed_roles: UserRole):
    """Factory dependency for RBAC checking on endpoints."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        role_values = [r.value for r in allowed_roles]
        if current_user.role not in role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {', '.join(role_values)}"
            )
        return current_user
    return role_checker

# Predefined role dependencies
require_government_admin = require_roles(UserRole.GOVERNMENT_ADMIN)
require_municipal_staff = require_roles(UserRole.GOVERNMENT_ADMIN, UserRole.MUNICIPAL_MEMBER)
require_any_staff = require_roles(UserRole.GOVERNMENT_ADMIN, UserRole.MUNICIPAL_MEMBER, UserRole.FIELD_CREW)
require_citizen = require_roles(UserRole.CITIZEN)

def enforce_single_admin_invariant(db: Session):
    """
    Ensures that only exactly one Government Admin can ever exist in the system.
    Raises HTTPException 400 if an admin already exists.
    """
    admin_count = db.query(User).filter(User.role == UserRole.GOVERNMENT_ADMIN.value).count()
    if admin_count >= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Violation of Single-Admin Invariant: A Government Admin account already exists in this municipality."
        )

