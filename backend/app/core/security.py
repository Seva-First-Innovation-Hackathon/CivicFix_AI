from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any, Optional, Tuple, Union
import uuid
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from app.core.config import settings

ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16
)

def get_password_hash(password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    return ph.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, Exception):
        return False

def hash_token(raw_token: str) -> str:
    """Computes a cryptographic SHA-256 digest of a token so raw tokens are never stored in DB."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

def verify_token_hash(raw_token: str, expected_hash: str) -> bool:
    """Constant-time verification of a token against its stored SHA-256 hash."""
    return hmac.compare_digest(hash_token(raw_token), expected_hash or "")

def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
    role: Optional[str] = None
) -> str:
    """Creates a signed short-lived JWT access token with unique jti."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": str(subject),
        "jti": uuid.uuid4().hex,
        "type": "access",
    }
    if role:
        to_encode["role"] = role

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token_with_meta(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
    family_id: Optional[str] = None,
    jti: Optional[str] = None,
) -> Tuple[str, str, str, datetime]:
    """Creates a signed JWT refresh token plus (jti, family_id, expires_at) metadata."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    token_jti = jti or uuid.uuid4().hex
    token_family = family_id or uuid.uuid4().hex

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": str(subject),
        "jti": token_jti,
        "fid": token_family,
        "type": "refresh",
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt, token_jti, token_family, expire

def create_refresh_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
    family_id: Optional[str] = None,
    jti: Optional[str] = None,
) -> str:
    """Creates a signed JWT refresh token."""
    token, _, _, _ = create_refresh_token_with_meta(
        subject=subject,
        expires_delta=expires_delta,
        family_id=family_id,
        jti=jti,
    )
    return token

def decode_token(token: str) -> Optional[dict]:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
