from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, decode_token
)
from app.models.entities import User, CitizenProfile, NotificationPreference
from app.models.enums import UserRole
from app.schemas.user import (
    CitizenRegisterRequest, LoginRequest, TokenResponse,
    RefreshTokenRequest, UserResponse
)
from app.api.deps import get_current_user
from app.services.audit import log_audit
from app.core.config import settings
from app.core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register_citizen(request: Request, data: CitizenRegisterRequest, db: Session = Depends(get_db)):

    """
    Public registration endpoint for citizens.
    Explicitly restricted to CITIZEN role only.
    """
    # Check for existing email
    existing_user = db.query(User).filter(User.email == data.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists"
        )

    # Hash password with Argon2id
    hashed_pwd = get_password_hash(data.password)

    # Create citizen user
    user = User(
        email=data.email.lower(),
        full_name=data.full_name,
        phone_number=data.phone_number,
        hashed_password=hashed_pwd,
        role=UserRole.CITIZEN.value,
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.flush()

    # Create citizen profile
    profile = CitizenProfile(
        user_id=user.id,
        preferred_language=data.preferred_language or "en"
    )
    db.add(profile)

    # Create default notification preferences
    notif_pref = NotificationPreference(
        user_id=user.id,
        in_app_enabled=True,
        email_enabled=True,
        sms_enabled=False
    )
    db.add(notif_pref)

    db.commit()
    db.refresh(user)

    # Audit log
    log_audit(
        db=db,
        action="CITIZEN_REGISTRATION",
        entity_type="USER",
        entity_id=user.id,
        user_id=user.id,
        ip_address=request.client.host if request.client else None
    )

    access_token = create_access_token(subject=user.id, role=user.role)
    refresh_token = create_refresh_token(subject=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role
    )

@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    """
    Unified secure login for all roles.
    Validates user existence, active status, and password hash.
    """
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact administration."
        )

    # Audit login
    log_audit(
        db=db,
        action="USER_LOGIN",
        entity_type="USER",
        entity_id=user.id,
        user_id=user.id,
        ip_address=request.client.host if request.client else None
    )

    access_token = create_access_token(subject=user.id, role=user.role)
    refresh_token = create_refresh_token(subject=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role
    )

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
def refresh_token(request: Request, data: RefreshTokenRequest, db: Session = Depends(get_db)):

    """Refreshes an expired access token using a valid refresh token."""
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer active or found"
        )

    new_access_token = create_access_token(subject=user.id, role=user.role)
    new_refresh_token = create_refresh_token(subject=user.id)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role
    )

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns the authenticated user's profile with role-specific context."""
    return current_user

@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Logs out the user and records audit trail."""
    log_audit(
        db=db,
        action="USER_LOGOUT",
        entity_type="USER",
        entity_id=current_user.id,
        user_id=current_user.id
    )
    return {"message": "Successfully logged out"}

