from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import (
    verify_password, get_password_hash, hash_token, verify_token_hash,
    create_access_token, create_refresh_token_with_meta, decode_token
)
from app.models.entities import User, CitizenProfile, NotificationPreference, RefreshToken
from app.models.enums import UserRole
from app.schemas.user import (
    CitizenRegisterRequest, LoginRequest, TokenResponse,
    RefreshTokenRequest, LogoutRequest, UserResponse
)
from app.api.deps import get_current_user
from app.services.audit import log_audit
from app.core.config import settings
from app.core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _issue_session_tokens(db: Session, user: User) -> tuple[str, str]:
    """Issues a short-lived access token + persisted hashed refresh token with unique jti & family_id."""
    access_token = create_access_token(subject=user.id, role=user.role)
    refresh_token, jti, family_id, expires_at = create_refresh_token_with_meta(subject=user.id)

    rt_record = RefreshToken(
        jti=jti,
        token_hash=hash_token(refresh_token),
        family_id=family_id,
        user_id=user.id,
        is_revoked=False,
        expires_at=expires_at,
    )
    db.add(rt_record)
    return access_token, refresh_token


def _revoke_token_family(db: Session, family_id: str, reason: str) -> None:
    now = datetime.now(timezone.utc)
    (
        db.query(RefreshToken)
        .filter(RefreshToken.family_id == family_id, RefreshToken.is_revoked == False)
        .update(
            {
                RefreshToken.is_revoked: True,
                RefreshToken.revoked_at: now,
                RefreshToken.revoked_reason: reason,
            },
            synchronize_session=False,
        )
    )


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register_citizen(request: Request, data: CitizenRegisterRequest, db: Session = Depends(get_db)):
    """
    Public registration endpoint for citizens.
    Explicitly restricted to CITIZEN role only.
    """
    existing_user = db.query(User).filter(User.email == data.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists"
        )

    hashed_pwd = get_password_hash(data.password)
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

    db.add(CitizenProfile(
        user_id=user.id,
        preferred_language=data.preferred_language or "en"
    ))
    db.add(NotificationPreference(
        user_id=user.id,
        in_app_enabled=True,
        email_enabled=True,
        sms_enabled=False
    ))

    access_token, refresh_token = _issue_session_tokens(db, user)

    log_audit(
        db=db,
        action="CITIZEN_REGISTRATION",
        entity_type="USER",
        entity_id=user.id,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        commit=False,
    )
    db.commit()
    db.refresh(user)

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
    Validates user existence, active status, and Argon2id password hash.
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

    access_token, refresh_token = _issue_session_tokens(db, user)

    log_audit(
        db=db,
        action="USER_LOGIN",
        entity_type="USER",
        entity_id=user.id,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        commit=False,
    )
    db.commit()

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
    """
    Rotates an active refresh token into a fresh token pair.
    Reuses of already-rotated/revoked refresh tokens trigger immediate family-wide revocation.
    """
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing required tracking claims"
        )

    rt = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if not rt or rt.user_id != user_id or not verify_token_hash(data.refresh_token, rt.token_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unrecognized or invalid refresh token"
        )

    now = datetime.now(timezone.utc)

    # Reuse / Replay Detection
    if rt.is_revoked:
        _revoke_token_family(db, rt.family_id, reason="refresh_token_reuse_detected")
        log_audit(
            db=db,
            action="REFRESH_TOKEN_REUSE_DETECTED",
            entity_type="USER",
            entity_id=rt.user_id,
            user_id=rt.user_id,
            details={"reused_jti": rt.jti, "family_id": rt.family_id},
            ip_address=request.client.host if request.client else None,
            commit=False,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked or reused. Please sign in again."
        )

    if _as_utc(rt.expires_at) <= now:
        rt.is_revoked = True
        rt.revoked_at = now
        rt.revoked_reason = "expired"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        _revoke_token_family(db, rt.family_id, reason="account_inactive_or_missing")
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer active or found"
        )

    # Issue rotated pair in the same token family and invalidate previous token
    new_access_token = create_access_token(subject=user.id, role=user.role)
    new_refresh_token, new_jti, _, new_exp = create_refresh_token_with_meta(
        subject=user.id,
        family_id=rt.family_id,
    )

    rt.is_revoked = True
    rt.revoked_at = now
    rt.revoked_reason = "rotated"
    rt.replaced_by_jti = new_jti

    db.add(RefreshToken(
        jti=new_jti,
        token_hash=hash_token(new_refresh_token),
        family_id=rt.family_id,
        parent_jti=rt.jti,
        user_id=user.id,
        is_revoked=False,
        expires_at=new_exp,
    ))
    db.commit()

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
def logout(
    data: Optional[LogoutRequest] = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Logs out the authenticated user, revoking active refresh capability
    (for the supplied token family, or all active user sessions if omitted),
    and records the audit trail.
    """
    now = datetime.now(timezone.utc)
    if data and data.refresh_token:
        target_hash = hash_token(data.refresh_token)
        rt = db.query(RefreshToken).filter(
            RefreshToken.token_hash == target_hash,
            RefreshToken.user_id == current_user.id
        ).first()
        if rt:
            _revoke_token_family(db, rt.family_id, reason="user_logout")
        else:
            payload = decode_token(data.refresh_token)
            if payload and payload.get("sub") == current_user.id and payload.get("fid"):
                _revoke_token_family(db, payload["fid"], reason="user_logout")
    else:
        (
            db.query(RefreshToken)
            .filter(RefreshToken.user_id == current_user.id, RefreshToken.is_revoked == False)
            .update(
                {
                    RefreshToken.is_revoked: True,
                    RefreshToken.revoked_at: now,
                    RefreshToken.revoked_reason: "user_logout_all",
                },
                synchronize_session=False,
            )
        )

    log_audit(
        db=db,
        action="USER_LOGOUT",
        entity_type="USER",
        entity_id=current_user.id,
        user_id=current_user.id,
        commit=False,
    )
    db.commit()
    return {"message": "Successfully logged out"}
