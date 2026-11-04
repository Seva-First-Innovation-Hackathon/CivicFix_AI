# CivicFix AI — Intelligent Municipal Complaint Resolution Platform

> **"Report. Resolve. Rebuild Trust."**

CivicFix AI is an enterprise-grade, full-stack municipal civic complaint management and accountability platform. It bridges the gap between citizens and local government authorities using AI-assisted issue triage, transparent priority policies, accountable field crew dispatch, and citizen-verified resolutions.

---

## 🌟 Key Features

- **Four Separated Roles & RBAC**:
  - `CITIZEN`: Submit issues, track live status, inspect repair evidence, confirm resolution, or reopen tickets.
  - `MUNICIPAL_MEMBER`: Triage complaints, review/override AI assessments, dispatch work orders to field crews.
  - `FIELD_CREW`: Mobile-first task view, status updates (`IN_PROGRESS`, `BLOCKED`), before/after photo submission, and materials logging.
  - `GOVERNMENT_ADMIN`: Super-admin oversight, department configuration, staff account provisioning, system settings, and immutable audit logs.
- **Single-Admin Invariant**:
  - Strict architectural guarantee enforcing that only **one** Government Admin account exists per instance. Creation of a second administrator is blocked at the CLI, database, and API layers.
- **AI-Powered Automated Triage**:
  - NLP Text Classification: Automatically maps citizen narratives to standard municipal categories (`POTHOLE`, `GARBAGE`, `STREETLIGHT`, `WATER_LEAKAGE`, etc.).
  - Computer Vision Damage Assessment: Evaluates physical structural damage on a 1.0 to 10.0 scale.
  - Transparent Priority Recommendation ($P_1$ to $P_4$) with natural language explainability.
  - Dynamic SLA deadline calculation based on severity and public safety hazard level.
- **Spatial Proximity & Duplicate Detection**:
  - Automatically identifies duplicate reports within 100 meters using Haversine spherical math (SQLite/Local) and PostGIS `ST_DWithin` spatial indexes (PostgreSQL/Production), preventing redundant field dispatches.
- **Two-Stage Resolution Verification**:
  - Eliminates "paper-only" closures. When field crews submit repair evidence, complaints enter `AWAITING_CITIZEN_CONFIRMATION`.
  - The ticket cannot be marked `RESOLVED` until the reporting citizen approves the repair evidence, or they may `REOPEN` it with dispute notes.
- **Strict Anti-IDOR & Security Hardening**:
  - Argon2id password hashing (`argon2-cffi`).
  - Short-lived JWT access tokens (15m) + secure refresh tokens (7d).
  - Strict ownership checks preventing horizontal data access or cross-citizen ticket manipulation.
  - File upload sanitization: MIME validation, size caps (10MB), and UUID-prefixed storage paths.
- **Multi-Language Support (i18n)**:
  - Full interface localization in **English**, **Telugu (తెలుగు)**, and **Hindi (हिंदी)**.
- **Interactive Geospatial Mapping**:
  - OpenStreetMap & Leaflet integration with GPS browser location acquisition, pin dropping, and priority-colored markers.
- **Public Impact Dashboard**:
  - Anonymized aggregate civic metrics, resolution rates, and ward summaries preserving citizen privacy.

---

## 🏗️ Technology Stack

| Component | Technologies |
| :--- | :--- |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, React Router v6, TanStack Query, Lucide React, Leaflet & React-Leaflet, Vitest |
| **Backend** | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2, Argon2id, PyJWT, Starlette, Pytest |
| **Database** | PostgreSQL 16 + PostGIS 3.4 (Production / Docker) & SQLite with Haversine math (Local / Testing) |
| **Infrastructure** | Docker Compose, Nginx, Uvicorn ASGI Server |

---

## 👥 Seeded Demo Accounts

The database comes pre-seeded with test accounts across all roles:

| Role | Email | Password | Purpose |
| :--- | :--- | :--- | :--- |
| **Government Admin** | `admin@civicfix.gov` | `AdminSecure2026!` | Super-admin oversight, staff provisioning, audit logs |
| **Municipal Officer** | `officer.sharma@civicfix.gov` | `StaffSecure2026!` | Review AI triage, assign departments, dispatch work orders |
| **Field Crew** | `crew.patel@civicfix.gov` | `CrewSecure2026!` | Field mobile view, update progress, upload repair evidence |
| **Citizen (Arjun)** | `citizen.arjun@example.com` | `CitizenPass2026!` | File complaints, inspect resolution, confirm satisfaction |
| **Citizen (Priya)** | `citizen.priya@example.com` | `CitizenPass2026!` | Test duplicate reporting & Anti-IDOR security checks |

---

## ☁️ Production Cloud Deployment (Render + Vercel)

CivicFix AI is configured for one-click production deployment:
- **Backend & Database**: Render (FastAPI Web Service + Managed PostgreSQL) via `render.yaml` Blueprint.
- **Frontend**: Vercel (React 18 + Vite SPA) via `frontend/vercel.json` rewrites.

### 1. Backend & PostgreSQL Deployment on Render
1. Push this repository to GitHub.
2. Sign in to [Render](https://render.com) and click **New +** -> **Blueprint**.
3. Connect your GitHub repository. Render reads `render.yaml` and provisions:
   - A managed **PostgreSQL** database (`civicfix-postgres`).
   - A Python 3.12 Web Service (`civicfix-backend`).
4. Build command: `pip install -r requirements.txt`.
5. Start command: `sh -c 'python bootstrap.py && python seed.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT'`.
6. Health check: `/health` (probes API and database connectivity).

### 2. Frontend Deployment on Vercel
1. Sign in to [Vercel](https://vercel.com) and click **Add New** -> **Project**.
2. Import the same GitHub repository.
3. Configure project settings:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Environment Variables:
   - `VITE_API_BASE_URL`: Your Render backend URL (e.g., `https://civicfix-backend.onrender.com`).
5. Click **Deploy**. Vercel will build the frontend and serve it with clean SPA route rewrites via `vercel.json`.

### 3. Connect Frontend and Backend
1. Copy your Vercel deployment URL (e.g. `https://civicfix-ai.vercel.app`).
2. In the Render Dashboard under `civicfix-backend` -> **Environment**, ensure `BACKEND_CORS_ORIGINS` includes your Vercel URL.
   *(The backend also automatically allows all `https://*.vercel.app` preview deployments via regex).*

---

## 🚀 Quick Start Guide

### Option A: Local Development (Fastest)

#### 1. Backend Setup
```bash
# Create and activate Python virtual environment
python -m venv backend/.venv
# Windows:
.\backend\.venv\Scripts\Activate.ps1
# Linux/macOS:
source backend/.venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Provision initial Government Admin (Enforces Single-Admin Invariant)
python backend/bootstrap.py --email admin@civicfix.gov --password "CivicFixAdmin2026!" --name "Chief Municipal Administrator"

# Seed initial departments, staff, and complaints
python backend/seed.py

# Run backend automated tests (7/7 suites)
pytest backend/tests/test_civicfix.py

# Start FastAPI development server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --app-dir backend
```
Backend API will be running at `http://127.0.0.1:8000` with Swagger docs at `http://127.0.0.1:8000/docs`.

#### 2. Frontend Setup
```bash
cd frontend

# Install npm dependencies
npm install

# Run frontend unit tests (vitest)
npm test

# Verify production build
npm run build

# Start Vite development server
npm run dev
```
Frontend will be running at `http://localhost:5173`.

---

### Option B: Docker Compose (Full Stack with PostGIS)

```bash
# 1. Build and launch all services in detached mode
docker compose -f infrastructure/docker-compose.yml up --build -d

# 2. Provision initial admin and seed data
docker compose -f infrastructure/docker-compose.yml exec backend python bootstrap.py --email admin@civicfix.gov --password "CivicFixAdmin2026!" --name "Chief Municipal Administrator"
docker compose -f infrastructure/docker-compose.yml exec backend python seed.py
```
Open your browser at `http://localhost:80`.

---

## 🧪 Verification & Automated Testing

### Backend Test Suite
Run the comprehensive security, IDOR, invariant, and lifecycle tests:
```bash
pytest backend/tests/test_civicfix.py -v
```
Test Coverage Includes:
- `test_health_endpoint`: API health and uptime check.
- `test_citizen_registration_and_login`: Citizen auth token generation.
- `test_public_admin_registration_is_impossible`: Proves non-citizen registration is blocked with 400.
- `test_idor_protection_citizen_complaint_access`: Proves Citizen B cannot access or modify Citizen A's ticket (403 Forbidden).
- `test_single_admin_invariant_and_staff_creation`: Proves only one Government Admin can exist and staff creation works via admin.
- `test_two_stage_verification_lifecycle`: Full lifecycle from `SUBMITTED` -> `CREW_ASSIGNED` -> `AWAITING_CITIZEN_CONFIRMATION` -> `RESOLVED`.
- `test_haversine_spatial_and_text_similarity`: Spatial duplicate detection within 100 meters.

### Frontend Test Suite
Run the component and translation tests:
```bash
cd frontend
npm test
```

---

## 📚 Technical Documentation

Detailed documentation is available in the `docs/` folder:

- [System Architecture](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/architecture.md) — Multi-tier topology, AI triage flow, and operational lifecycle.
- [REST API Specification](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/api.md) — Comprehensive endpoint catalogue, schemas, and error codes.
- [Database Architecture](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/database.md) — 18 normalized tables, ER diagram, constraints, and PostGIS spatial queries.
- [Security & Access Control](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/security.md) — Argon2id, JWT token rotation, RBAC, Single-Admin invariant, Anti-IDOR, and audit trails.
- [Deployment Guide](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/deployment.md) — Local development, Docker Compose, and production hardening checklist.
- [18-Step Live Demo Guide](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/demo-guide.md) — Reproducible walkthrough script for complete end-to-end evaluation.

---

## 🛡️ License

Built for public sector transparency and municipal excellence. Released under the MIT License.

