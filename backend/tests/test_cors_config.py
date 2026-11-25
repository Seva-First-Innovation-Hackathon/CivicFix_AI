import pytest
from pydantic import ValidationError
from app.core.config import Settings, clean_and_validate_origin, parse_cors_origins


def test_cors_origins_comma_separated_format(monkeypatch):
    """Verifies that comma-separated origin strings parse and normalize correctly."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://example.vercel.app, http://localhost:5173")
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    settings = Settings()
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://example.vercel.app",
        "http://localhost:5173"
    ]


def test_cors_origins_json_array_format(monkeypatch):
    """Verifies that JSON array strings parse and normalize correctly."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["https://example.vercel.app", "http://localhost:5173"]')
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    settings = Settings()
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://example.vercel.app",
        "http://localhost:5173"
    ]


def test_cors_origins_empty_values(monkeypatch):
    """Verifies that empty strings and empty JSON arrays evaluate to an empty list."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "   ")
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    s1 = Settings()
    assert s1.BACKEND_CORS_ORIGINS == []

    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "[]")
    s2 = Settings()
    assert s2.BACKEND_CORS_ORIGINS == []


def test_cors_origins_whitespace_and_trailing_slashes(monkeypatch):
    """Verifies whitespace trimming and trailing slash removal for standard web origins."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", " https://civic-fix-ai-plum.vercel.app/ , http://localhost:5173/ ")
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    settings = Settings()
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://civic-fix-ai-plum.vercel.app",
        "http://localhost:5173"
    ]


def test_cors_origins_rejects_malformed_json(monkeypatch):
    """Verifies that malformed JSON strings raise a descriptive ValidationError."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["https://example.vercel.app"')
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "Invalid JSON array format" in str(exc_info.value)


def test_cors_origins_rejects_wildcard(monkeypatch):
    """Verifies that wildcard origins '*' are rejected to prevent insecure credentialed CORS."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "*")
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "Wildcard origin '*' is not permitted" in str(exc_info.value)


@pytest.mark.parametrize("invalid_origin", [
    "not-a-valid-origin",
    "ftp://insecure-scheme.com",
    "https://example.com/api/v1",
    "https://example.com?query=1",
    "http://",
])
def test_cors_origins_rejects_invalid_urls(monkeypatch, invalid_origin):
    """Verifies that invalid URL formats, paths, queries, and unsupported schemes are rejected."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", invalid_origin)
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_cors_origins_merges_frontend_origins(monkeypatch):
    """Verifies that FRONTEND_ORIGINS alias is merged cleanly without duplicates."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://civic-fix-ai-plum.vercel.app")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://civic-fix-ai-plum.vercel.app, https://preview.example.com")
    settings = Settings()
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://civic-fix-ai-plum.vercel.app",
        "https://preview.example.com"
    ]


def test_render_exact_env_reproduction(monkeypatch):
    """Simulates Render production environment variables with explicit trusted origin & strong secret."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://civicfix_user:secret@dpg-xxx:5432/civicfix_db")
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://civic-fix-ai-plum.vercel.app")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://civic-fix-ai-plum.vercel.app")
    settings = Settings()
    assert settings.get_effective_cors_origins() == ["https://civic-fix-ai-plum.vercel.app"]
    assert "http://localhost:5173" not in settings.get_effective_cors_origins()


def test_production_defaults_exclude_localhost_and_require_secret(monkeypatch):
    """Verifies production omits localhost defaults and fails cleanly when SECRET_KEY is missing or weak."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://civicfix_user:secret@dpg-xxx:5432/civicfix_db")
    monkeypatch.delenv("BACKEND_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)

    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("SECRET_KEY", "a_very_strong_random_production_signing_secret_2026_verified")
    s = Settings()
    assert s.get_effective_cors_origins() == ["https://civic-fix-ai-plum.vercel.app"]
