# CivicFix AI — Intelligent Municipal Complaint Resolution Platform

> **"Report. Resolve. Rebuild Trust."**

CivicFix AI is a full-stack municipal civic complaint management and accountability platform connecting citizens, municipal officers, field crews, and the municipality's sole Government Administrator through AI-assisted triage, priority policies, field work orders, and citizen-verified resolutions.

---

## Key Features

- **Four Separated Roles & Server-Side RBAC**:
  - `CITIZEN`: Submit issues, track live status, inspect repair evidence, confirm resolution, or reopen tickets.
  - `MUNICIPAL_MEMBER`: Department-scoped triage review, AI overrides with mandatory reason, work-order dispatch, completion evidence review.
  - `FIELD_CREW`: Assigned work-order execution, progress/blocker updates (`IN_PROGRESS`, `BLOCKED`), and completion evidence upload.
  - `GOVERNMENT_ADMIN`: Sole municipality administrator managing departments, staff provisioning, audit logs, and system administration.
- **Single-Admin Invariant**: Strictly one `GOVERNMENT_ADMIN` account per municipality, enforced via CLI bootstrap and admin user API.
- **Asynchronous AI Triage Pipeline**: Non-blocking FastAPI background processing with persistent job state (`PENDING` / `PROCESSING` / `COMPLETED` / `FAILED`), Gemini 2.5 Flash structured JSON integration or deterministic offline `MockAIProvider`, and explicit retry via `/reanalyze-ai`.
- **Two-Stage Resolution Verification**: Non-admin staff and crews cannot unilaterally close tickets as `RESOLVED`; closure requires citizen confirmation (`AWAITING_CITIZEN_CONFIRMATION -> RESOLVED`) or documented reopening (`REOPENED`).
- **Hardened Security**:
  - Argon2id password hashing (`argon2-cffi`).
  - Short-lived JWT access tokens (`15` minutes) + database-tracked refresh tokens with `jti` rotation, family reuse detection, and logout revocation.
  - Strict Anti-IDOR checks across complaints and private `/api/v1/evidence/{id}` / `/uploads/{folder}/{filename}` endpoints.
  - Server-side Pillow EXIF scrubbing (10MB limit) and SlowAPI rate limiting.
- **Interactive Keyless Esri/Leaflet Mapping**: Dual-coded shape+color priority markers, GPS pin selection, and manual coordinate fallback.

---

## Security & Credential Management Notice

- **Zero Static Production Passwords**: Production deployments must NEVER use hardcoded passwords or repository-committed secrets.
- Configure `SECRET_KEY`, `DATABASE_URL`, and `INITIAL_ADMIN_PASSWORD` exclusively via protected environment variables or secret stores (e.g., Render Environment Variables).
- Generate strong JWT signing keys with: `openssl rand -hex 32`.
- Production CORS origins must explicitly list trusted origins (`https://civic-fix-ai-plum.vercel.app`) rather than wildcards.

---

## Quick Start Guide

### Option A: Local Development

#### 1. Backend Setup
```bash
# Configure environment variables from template
cp .env.example backend/.env
# Edit backend/.env to set a strong dev SECRET_KEY and opt-in demo passwords if needed

# Create and activate Python virtual environment
python -m venv backend/.venv
# Windows:
.\backend\.venv\Scripts\Activate.ps1
# Linux/macOS:
source backend/.venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Apply Alembic schema migrations (single schema authority)
python backend/migrate.py

# Provision initial Government Admin (supply password via env or prompt/CLI, never commit secrets)
python backend/bootstrap.py --email admin@civicfix.gov --password "<STRONG_ADMIN_PASSWORD>" --name "Municipal Commissioner"

# Optional opt-in local demo data (disabled in production)
ALLOW_DEMO_SEEDING=true python backend/seed.py --demo-seed

# Run isolated automated backend tests
pytest backend/tests/ -v

# Start FastAPI server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --app-dir backend
```

#### 2. Frontend Setup
```bash
cd frontend
npm ci
npm test -- --run
npm run build
npm run dev
```

---

### Option B: Docker Compose (PostgreSQL + PostGIS)

Set required secrets in a local `.env` file alongside `infrastructure/docker-compose.yml` (`POSTGRES_PASSWORD`, `SECRET_KEY`, `INITIAL_ADMIN_PASSWORD`), then run:

```bash
docker compose -f infrastructure/docker-compose.yml up --build -d
```

---

## Documentation

- [System Architecture](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/architecture.md)
- [REST API Specification](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/api.md)
- [Database Architecture](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/database.md)
- [Security & Access Control](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/security.md)
- [Deployment Guide](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/deployment.md)
- [Demo Walkthrough Guide](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/demo-guide.md)
