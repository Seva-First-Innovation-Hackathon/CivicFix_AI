import json
import logging
import os
import secrets
from pathlib import Path
from typing import List, Union, Optional, Annotated
from urllib.parse import urlparse
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode

BASE_DIR = Path(__file__).resolve().parent.parent.parent
logger = logging.getLogger(__name__)

PRODUCTION_FRONTEND_ORIGIN = "https://civic-fix-ai-plum.vercel.app"
DEFAULT_DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
]
_WEAK_SECRET_VALUES = {
    "",
    "civicfix-super-secret-key-change-in-production-min32chars",
    "change-this-in-production-min-32-chars-long-secret-key-2026",
    "civicfix-production-secret-key-min-32-chars-long-2026",
    "changeme",
    "secret",
}
_EPHEMERAL_DEV_SECRET = secrets.token_urlsafe(48)

def clean_and_validate_origin(origin: str) -> str:
    """
    Validates and normalizes a CORS origin string.
    Ensures scheme is http/https, host is present, no trailing slashes or path/query/fragment.
    Strictly forbids wildcard '*' when credentials are used.
    """
    cleaned = origin.strip().rstrip('/')
    if not cleaned:
        raise ValueError("CORS origin entry cannot be empty.")
    if cleaned == '*':
        raise ValueError("Wildcard origin '*' is not permitted when allow_credentials=True.")
    parsed = urlparse(cleaned)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Invalid CORS origin scheme: {origin!r}. Must use http or https.")
    if not parsed.netloc:
        raise ValueError(f"Invalid CORS origin: {origin!r}. Missing host/domain.")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError(f"Invalid CORS origin: {origin!r}. Origin must not contain path, query parameters, or fragments.")
    return f"{parsed.scheme}://{parsed.netloc}"

def parse_cors_origins(v: Union[str, List[str], None]) -> List[str]:
    """
    Parses CORS origins from JSON array string, comma-separated string, or list.
    Safely rejects malformed JSON and invalid origins.
    """
    if v is None:
        return []
    raw_list: List[str] = []
    if isinstance(v, str):
        v_str = v.strip()
        if not v_str:
            return []
        if v_str.startswith('[') or v_str.endswith(']'):
            try:
                parsed_json = json.loads(v_str)
            except Exception as e:
                raise ValueError(f"Invalid JSON array format in CORS origins: {e}")
            if not isinstance(parsed_json, list):
                raise ValueError("CORS origins JSON must be an array of strings.")
            raw_list = [str(x) for x in parsed_json]
        else:
            raw_list = [x for x in v_str.split(',')]
    elif isinstance(v, list):
        raw_list = [str(x) for x in v]
    else:
        raise ValueError(f"Unsupported CORS origins type: {type(v)}")

    validated: List[str] = []
    for item in raw_list:
        stripped = item.strip()
        if not stripped:
            continue
        valid_origin = clean_and_validate_origin(stripped)
        if valid_origin not in validated:
            validated.append(valid_origin)
    return validated

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    APP_NAME: str = "CivicFix AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    PUBLIC_APP_URL: str = "http://localhost:5173"

    # Security
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    BACKEND_CORS_ORIGINS: Annotated[List[str], NoDecode] = []
    FRONTEND_ORIGINS: Optional[str] = None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str], None]) -> List[str]:
        origins = parse_cors_origins(v)
        fe_env = os.getenv("FRONTEND_ORIGINS", "")
        if fe_env:
            for item in parse_cors_origins(fe_env):
                if item not in origins:
                    origins.append(item)
        return origins

    def get_effective_cors_origins(self) -> List[str]:
        """
        Returns strictly validated CORS origins tailored to the active environment:
        - Production: explicit trusted allowlist only (no localhost fallback, no wildcards).
        - Development/Testing: configured origins or explicit local dev defaults.
        """
        is_prod = self.ENVIRONMENT.lower() == "production"
        configured = [o for o in self.BACKEND_CORS_ORIGINS if o and o != "*"]
        if is_prod:
            explicit_non_local = [
                o for o in configured
                if not any(h in o for h in ("localhost", "127.0.0.1", "0.0.0.0"))
            ]
            if explicit_non_local:
                return explicit_non_local
            return configured if configured else [PRODUCTION_FRONTEND_ORIGIN]
        return configured if configured else list(DEFAULT_DEV_CORS_ORIGINS)

    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'civicfix.db'}"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean.startswith("postgres://"):
                v_clean = v_clean.replace("postgres://", "postgresql://", 1)
            if v_clean.startswith("postgresql://"):
                return v_clean.replace("postgresql://", "postgresql+psycopg2://", 1)
            return v_clean
        return v

    # Storage (local or S3-compatible / Cloudflare R2)
    STORAGE_BACKEND: str = "local"  # "local", "r2", "s3"
    REQUIRE_DURABLE_STORAGE: bool = False
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    R2_ACCOUNT_ID: str = ""
    R2_BUCKET_NAME: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_ENDPOINT_URL: str = ""
    R2_REGION: str = "auto"
    STORAGE_PRESIGNED_TTL_SECONDS: int = 300
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    ALLOWED_AUDIO_TYPES: List[str] = ["audio/mpeg", "audio/wav", "audio/webm", "audio/ogg"]

    # Rate Limiting & Durable Queue / Redis Configuration
    QUEUE_BACKEND: str = "inline"  # "inline" (dev/test) or "redis" / "arq" (production worker queue)
    REDIS_URL: str = ""
    REQUIRE_REDIS: bool = False
    WORKER_MAX_JOBS: int = 10
    JOB_MAX_ATTEMPTS: int = 3
    JOB_RETRY_BASE_SECONDS: int = 15
    SLA_MONITOR_INTERVAL_MINUTES: int = 5

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "3/minute"
    RATE_LIMIT_COMPLAINT_CREATE: str = "10/minute"
    RATE_LIMIT_AI_ANALYSIS: str = "10/minute"
    RATE_LIMIT_EMAIL_VERIFY: str = "3/minute"
    RATE_LIMIT_STORAGE_URL: str = "memory://"
    BEHIND_TRUSTED_PROXY: bool = False
    TRUSTED_PROXY_IPS: Annotated[List[str], NoDecode] = ["127.0.0.1", "::1"]

    @field_validator("TRUSTED_PROXY_IPS", mode="before")
    @classmethod
    def assemble_trusted_proxies(cls, v: Union[str, List[str], None]) -> List[str]:
        if v is None:
            return ["127.0.0.1", "::1"]
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                return ["127.0.0.1", "::1"]
            if v_str.startswith("["):
                try:
                    parsed = json.loads(v_str)
                    return [str(i).strip() for i in parsed if str(i).strip()]
                except Exception:
                    pass
            return [i.strip() for i in v_str.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        return ["127.0.0.1", "::1"]

    # AI Intelligence Layer
    AI_PROVIDER: str = "mock"  # "mock", "gemini"
    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""  # Backward compatibility alias
    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_CONFIDENCE_THRESHOLD: float = 0.70
    AI_HIGH_CONFIDENCE_THRESHOLD: float = 0.80
    AI_MEDIUM_CONFIDENCE_THRESHOLD: float = 0.55
    AI_REQUEST_TIMEOUT_SECONDS: int = 30
    AI_MAX_RETRIES: int = 2
    DUPLICATE_RADIUS_METERS: float = 100.0
    DUPLICATE_TIME_WINDOW_DAYS: int = 14

    # Real SMTP Email Configuration
    EMAIL_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@civicfix.gov"
    SMTP_FROM_NAME: str = "CivicFix AI"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: int = 15

    @model_validator(mode="after")
    def validate_smtp_and_ai_settings(self):
        # Validate mutually incompatible TLS/SSL settings
        if self.SMTP_USE_TLS and self.SMTP_USE_SSL:
            raise ValueError(
                "Incompatible SMTP configuration: SMTP_USE_TLS and SMTP_USE_SSL cannot both be True. "
                "Choose SMTP_USE_TLS=True for port 587 STARTTLS, or SMTP_USE_SSL=True for port 465 SSL/TLS."
            )
        # Harmonize GOOGLE_API_KEY and GEMINI_API_KEY
        if not self.GOOGLE_API_KEY and self.GEMINI_API_KEY:
            self.GOOGLE_API_KEY = self.GEMINI_API_KEY
        elif self.GOOGLE_API_KEY and not self.GEMINI_API_KEY:
            self.GEMINI_API_KEY = self.GOOGLE_API_KEY

        is_prod = self.ENVIRONMENT.lower() == "production"

        # Enforce strong, non-default SECRET_KEY and bounded access-token TTL in production
        raw_secret = (self.SECRET_KEY or "").strip()
        if is_prod:
            if len(raw_secret) < 32 or raw_secret in _WEAK_SECRET_VALUES:
                raise ValueError(
                    "Production environment requires a strong, unique SECRET_KEY (at least 32 characters) "
                    "supplied via environment variables."
                )
            if not (1 <= self.ACCESS_TOKEN_EXPIRE_MINUTES <= 60):
                raise ValueError(
                    "ACCESS_TOKEN_EXPIRE_MINUTES in production must be between 1 and 60 minutes."
                )
        elif not raw_secret:
            logger.warning(
                "SECRET_KEY is not set; using an ephemeral per-process development signing key."
            )
            self.SECRET_KEY = _EPHEMERAL_DEV_SECRET

        # Normalize default CORS origins when neither BACKEND_CORS_ORIGINS nor FRONTEND_ORIGINS was set
        if "BACKEND_CORS_ORIGINS" not in self.model_fields_set:
            base_defaults = [PRODUCTION_FRONTEND_ORIGIN] if is_prod else list(DEFAULT_DEV_CORS_ORIGINS)
            fe_env = os.getenv("FRONTEND_ORIGINS", "")
            if fe_env:
                for item in parse_cors_origins(fe_env):
                    if item not in base_defaults:
                        base_defaults.append(item)
            self.BACKEND_CORS_ORIGINS = base_defaults

        # Enforce no production SQLite fallback
        if is_prod and self.DATABASE_URL.startswith("sqlite"):
            raise ValueError(
                "Production environment requires a PostgreSQL database connection. "
                "DATABASE_URL cannot fall back to SQLite in production."
            )

        # Normalize and validate storage backend (no silent local fallback when durable R2/S3 is configured/required)
        self.STORAGE_BACKEND = (self.STORAGE_BACKEND or "local").strip().lower()
        if self.STORAGE_BACKEND not in {"local", "r2", "s3"}:
            raise ValueError(
                f"Invalid STORAGE_BACKEND '{self.STORAGE_BACKEND}'. Allowed values: local, r2, s3."
            )

        if self.STORAGE_BACKEND in {"r2", "s3"}:
            if self.STORAGE_BACKEND == "r2" and not (self.R2_ENDPOINT_URL or "").strip() and (self.R2_ACCOUNT_ID or "").strip():
                self.R2_ENDPOINT_URL = f"https://{self.R2_ACCOUNT_ID.strip()}.r2.cloudflarestorage.com"

            missing_storage_fields = [
                field_name
                for field_name, val in (
                    ("R2_BUCKET_NAME", self.R2_BUCKET_NAME),
                    ("R2_ACCESS_KEY_ID", self.R2_ACCESS_KEY_ID),
                    ("R2_SECRET_ACCESS_KEY", self.R2_SECRET_ACCESS_KEY),
                    ("R2_ENDPOINT_URL", self.R2_ENDPOINT_URL),
                )
                if not (val or "").strip()
            ]
            if missing_storage_fields:
                raise ValueError(
                    f"STORAGE_BACKEND='{self.STORAGE_BACKEND}' requires non-empty credentials/endpoint: "
                    f"{', '.join(missing_storage_fields)}"
                )
            endpoint_clean = self.R2_ENDPOINT_URL.strip()
            if not (endpoint_clean.startswith("https://") or endpoint_clean.startswith("http://")):
                raise ValueError("R2_ENDPOINT_URL must start with https:// or http://")
            self.R2_ENDPOINT_URL = endpoint_clean.rstrip("/")
            if not (10 <= self.STORAGE_PRESIGNED_TTL_SECONDS <= 3600):
                raise ValueError("STORAGE_PRESIGNED_TTL_SECONDS must be between 10 and 3600 seconds.")
        elif is_prod and self.REQUIRE_DURABLE_STORAGE:
            raise ValueError(
                "Production configuration requires durable object storage (STORAGE_BACKEND=r2 or s3) "
                "when REQUIRE_DURABLE_STORAGE=True."
            )

        # Normalize and validate queue / Redis configuration (single Redis URI for queue + rate limit)
        self.QUEUE_BACKEND = (self.QUEUE_BACKEND or "inline").strip().lower()
        if self.QUEUE_BACKEND not in {"inline", "redis", "arq"}:
            raise ValueError(
                f"Invalid QUEUE_BACKEND '{self.QUEUE_BACKEND}'. Allowed values: inline, redis, arq."
            )

        redis_clean = (self.REDIS_URL or "").strip()
        if redis_clean:
            if not (redis_clean.startswith("redis://") or redis_clean.startswith("rediss://")):
                raise ValueError("REDIS_URL must start with redis:// or rediss://")
            self.REDIS_URL = redis_clean
            if "RATE_LIMIT_STORAGE_URL" not in self.model_fields_set or self.RATE_LIMIT_STORAGE_URL == "memory://":
                self.RATE_LIMIT_STORAGE_URL = redis_clean
        else:
            if self.QUEUE_BACKEND in {"redis", "arq"}:
                raise ValueError(
                    f"QUEUE_BACKEND='{self.QUEUE_BACKEND}' requires a configured REDIS_URL."
                )
            if is_prod and self.REQUIRE_REDIS:
                raise ValueError(
                    "Production environment requires REDIS_URL for durable background queue and rate limiting "
                    "when REQUIRE_REDIS=True."
                )

        if self.JOB_MAX_ATTEMPTS < 1 or self.JOB_MAX_ATTEMPTS > 10:
            raise ValueError("JOB_MAX_ATTEMPTS must be between 1 and 10.")

        return self

    # Map & Spatial Geocoding Configuration
    MAP_GEOCODING_PROVIDER: str = "disabled"  # "disabled", "nominatim", "maptiler"
    MAP_GEOCODING_API_KEY: str = ""
    MAP_GEOCODING_USER_AGENT: str = "CivicFix-AI-Platform/1.0 (contact: support@civicfix.gov)"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    MAP_DEFAULT_CENTER_LAT: float = 17.4399
    MAP_DEFAULT_CENTER_LON: float = 78.4983
    MAP_DEFAULT_ZOOM: int = 12

    # Initial Admin Bootstrap (can be passed via CLI or ENV)
    INITIAL_ADMIN_EMAIL: str = "admin@civicfix.gov"
    INITIAL_ADMIN_PASSWORD: str = ""
    INITIAL_ADMIN_NAME: str = "Municipal Administrator"

    # SLAs in hours
    SLA_HOURS_P1: int = 12
    SLA_HOURS_P2: int = 24
    SLA_HOURS_P3: int = 72
    SLA_HOURS_P4: int = 168

settings = Settings()
