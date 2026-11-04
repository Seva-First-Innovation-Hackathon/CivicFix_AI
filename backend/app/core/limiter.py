import logging
from typing import Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)

def get_client_ip(request: Request) -> str:
    """
    Safely resolves client IP address.
    Strictly uses request.client.host unless explicitly configured behind a trusted proxy.
    """
    if settings.BEHIND_TRUSTED_PROXY:
        # Check X-Forwarded-For header if behind a trusted proxy
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            # Client IP is the first entry in the chain
            parts = [p.strip() for p in x_forwarded_for.split(",") if p.strip()]
            if parts:
                return parts[0]
        
        x_real_ip = request.headers.get("X-Real-IP")
        if x_real_ip:
            return x_real_ip.strip()

    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

def create_limiter() -> Limiter:
    """
    Initializes Limiter with configured storage backend (Redis in production, Memory locally).
    Fails safely: if production Redis is unreachable, falls back to in-memory to ensure
    protection is never silently disabled.
    """
    storage_uri = settings.RATE_LIMIT_STORAGE_URL
    
    if storage_uri.startswith("redis://") or storage_uri.startswith("rediss://"):
        try:
            import redis
            # Quick connectivity verification
            r = redis.from_url(storage_uri, socket_connect_timeout=2)
            r.ping()
            logger.info("Rate limiter successfully connected to Redis storage: %s", storage_uri)
        except Exception as exc:
            logger.warning(
                "Configured Redis storage (%s) is unavailable: %s. "
                "Failing safely by falling back to 'memory://' so rate limiting remains ACTIVE.",
                storage_uri, exc
            )
            storage_uri = "memory://"

    return Limiter(
        key_func=get_client_ip,
        default_limits=[],
        storage_uri=storage_uri,
        enabled=settings.RATE_LIMIT_ENABLED,
        headers_enabled=False,
    )


limiter = create_limiter()

def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Generates a consistent, safe HTTP 429 Too Many Requests response.
    Includes Retry-After header and informative JSON payload without leaking internal state.
    """
    retry_after = getattr(exc, "retry_after", 60)
    limit_detail = exc.detail or "Rate limit exceeded"
    
    response = JSONResponse(
        status_code=429,
        content={
            "detail": f"Rate limit exceeded: {limit_detail}. Please try again later.",
            "error_code": "RATE_LIMIT_EXCEEDED",
            "retry_after_seconds": retry_after,
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Exceeded": "true"
        }
    )
    return response
