import os
import json
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
    # 1. Empty string
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "   ")
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    s1 = Settings()
    assert s1.BACKEND_CORS_ORIGINS == []

    # 2. Empty JSON array
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "[]")
    s2 = Settings()
    assert s2.BACKEND_CORS_ORIGINS == []


def test_cors_origins_whitespace_and_trailing_slashes(monkeypatch):
    """Verifies whitespace trimming and trailing slash removal for standard web origins."""
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", " https://civicfix.vercel.app/ , http://localhost:5173/ ")
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    settings = Settings()
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://civicfix.vercel.app",
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
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://civicfix-ai.vercel.app")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://civicfix-ai.vercel.app, https://preview.vercel.app")
    settings = Settings()
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://civicfix-ai.vercel.app",
        "https://preview.vercel.app"
    ]


def test_render_exact_env_reproduction(monkeypatch):
    """Simulates the exact Render production environment variables to verify successful startup."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://civicfix_user:secret@dpg-xxx:5432/civicfix_db")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://civicfix-ai.vercel.app,http://localhost:5173")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://civicfix-ai.vercel.app")
    settings = Settings()
    assert "https://civicfix-ai.vercel.app" in settings.BACKEND_CORS_ORIGINS
    assert "http://localhost:5173" in settings.BACKEND_CORS_ORIGINS
