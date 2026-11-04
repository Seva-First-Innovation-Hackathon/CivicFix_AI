from typing import List, Union, Optional
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

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
    SECRET_KEY: str = "civicfix-super-secret-key-change-in-production-min32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours for seamless development
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    FRONTEND_ORIGINS: Optional[str] = None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        origins = []
        if isinstance(v, str) and not v.startswith("["):
            origins = [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            origins = [str(i).strip() for i in v if str(i).strip()]
        
        # Check FRONTEND_ORIGINS environment variable as an alias
        fe_env = os.getenv("FRONTEND_ORIGINS", "")
        if fe_env:
            for item in fe_env.split(","):
                item_clean = item.strip()
                if item_clean and item_clean not in origins:
                    origins.append(item_clean)

        return origins if origins else [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
        ]

    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'civicfix.db'}"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean.startswith("postgres://"):
                return v_clean.replace("postgres://", "postgresql://", 1)
            return v_clean
        return v

    # Storage
    STORAGE_TYPE: str = "local"
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    ALLOWED_AUDIO_TYPES: List[str] = ["audio/mpeg", "audio/wav", "audio/webm", "audio/ogg"]

    # Rate Limiting Configuration
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "3/minute"
    RATE_LIMIT_COMPLAINT_CREATE: str = "10/minute"
    RATE_LIMIT_AI_ANALYSIS: str = "10/minute"
    RATE_LIMIT_EMAIL_VERIFY: str = "3/minute"
    RATE_LIMIT_STORAGE_URL: str = "memory://"
    BEHIND_TRUSTED_PROXY: bool = False
    TRUSTED_PROXY_IPS: List[str] = ["127.0.0.1", "::1"]

    @field_validator("TRUSTED_PROXY_IPS", mode="before")
    @classmethod
    def assemble_trusted_proxies(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return ["127.0.0.1", "::1"]

    # AI Intelligence Layer
    AI_PROVIDER: str = "mock"  # "mock", "gemini"
    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""  # Backward compatibility alias
    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_CONFIDENCE_THRESHOLD: float = 0.70
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

        # Enforce no production SQLite fallback
        if self.ENVIRONMENT.lower() == "production" and self.DATABASE_URL.startswith("sqlite"):
            raise ValueError(
                "Production environment requires a PostgreSQL database connection. "
                "DATABASE_URL cannot fall back to SQLite in production."
            )
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

# Ensure upload directories exist
os.makedirs(os.path.join(settings.UPLOAD_DIR, "complaints"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "resolutions"), exist_ok=True)
