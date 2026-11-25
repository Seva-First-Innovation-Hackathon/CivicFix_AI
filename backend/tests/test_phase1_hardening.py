import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import io
import os
from pathlib import Path
import subprocess
import sys
import uuid

from PIL import Image
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.core.config import Settings, PRODUCTION_FRONTEND_ORIGIN
from app.core.limiter import limiter
from app.core.security import hash_token
from app.models.entities import (
    AuditLog, Complaint, ComplaintAttachment, ComplaintStatusHistory,
    DepartmentMembership, RefreshToken, ResolutionVerification, User
)
from app.models.enums import ComplaintCategory, ComplaintStatus, UserRole
from app.services.ai.service import ai_service, recover_interrupted_ai_jobs, run_ai_triage_background
from app.services.storage.service import storage_service


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_tiny_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (12, 12), color=(30, 80, 160)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# A1 + A3: Async AI Processing, Fresh DB Session, Status History & Failure Handling
# ---------------------------------------------------------------------------

def test_a1_a3_async_submission_deferred_then_completed_clean_history(
    client, test_actors, db_session_factory, monkeypatch
):
    """
    Proves:
    1. POST /complaints commits immediately and returns AI_ANALYSIS_PENDING before AI finishes.
    2. Background task uses its own fresh SessionLocal, transitions AI_ANALYSIS_PENDING -> UNDER_REVIEW.
    3. Status history captures accurate from_status -> to_status without UNDER_REVIEW -> UNDER_REVIEW duplicates.
    4. Concurrent claim prevents duplicate simultaneous execution, and /reanalyze-ai rejects in-flight (409).
    """
    dispatched_ids = []

    async def _capture_bg(complaint_id: str, force: bool = False):
        dispatched_ids.append((complaint_id, force))

    monkeypatch.setattr("app.api.v1.complaints.run_ai_triage_background", _capture_bg)

    c_a = test_actors["citizen_a"]
    token = _login(client, c_a["email"], c_a["password"])["access_token"]

    create_resp = client.post("/api/v1/complaints", json={
        "title": "Deep pothole near school bus gate",
        "description": "Large crater across main asphalt road lane endangering commuters.",
        "category": "ROADS",
        "latitude": 17.4415,
        "longitude": 78.4920,
    }, headers=_headers(token))
    assert create_resp.status_code == 201
    created = create_resp.json()
    cid = created["id"]

    assert created["status"] == ComplaintStatus.AI_ANALYSIS_PENDING.value
    assert created["ai_processing_status"] == "PENDING"
    assert dispatched_ids == [(cid, False)]

    # Run background AI triage explicitly using independent fresh session factory
    asyncio.run(ai_service.process_complaint_by_id(cid, session_factory=db_session_factory))

    detail = client.get(f"/api/v1/complaints/{cid}", headers=_headers(token)).json()
    assert detail["status"] == ComplaintStatus.UNDER_REVIEW.value
    assert detail["ai_processing_status"] == "COMPLETED"
    assert detail["ai_processing_attempts"] == 1
    assert detail["ai_analysis"] is not None

    timeline = client.get(f"/api/v1/complaints/{cid}/timeline", headers=_headers(token)).json()
    pairs = [(row["from_status"], row["to_status"]) for row in timeline]
    assert (None, "SUBMITTED") in pairs
    assert ("SUBMITTED", "AI_ANALYSIS_PENDING") in pairs
    assert ("AI_ANALYSIS_PENDING", "UNDER_REVIEW") in pairs
    assert ("UNDER_REVIEW", "UNDER_REVIEW") not in pairs

    # Repeating non-forced processing must be idempotent and add zero extra history entries
    asyncio.run(ai_service.process_complaint_by_id(cid, session_factory=db_session_factory, force=False))
    timeline_after = client.get(f"/api/v1/complaints/{cid}/timeline", headers=_headers(token)).json()
    assert len(timeline_after) == len(timeline)

    # Simulate active PROCESSING state: claim blocked and HTTP /reanalyze-ai returns 409 Conflict
    s = db_session_factory()
    try:
        comp = s.query(Complaint).filter(Complaint.id == cid).first()
        comp.ai_processing_status = "PROCESSING"
        comp.ai_processing_started_at = datetime.now(timezone.utc)
        s.commit()
        assert ai_service.try_claim_processing(s, cid, force=True) is False
    finally:
        s.close()

    conflict_resp = client.post(f"/api/v1/complaints/{cid}/reanalyze-ai", headers=_headers(token))
    assert conflict_resp.status_code == 409


def test_a3_ai_failure_handling_sanitizes_errors_and_recovers(
    client, test_actors, db_session_factory, monkeypatch
):
    """Proves AI timeout/exception preserves complaint in UNDER_REVIEW cleanly without leaking secrets."""
    c_a = test_actors["citizen_a"]
    token = _login(client, c_a["email"], c_a["password"])["access_token"]

    with monkeypatch.context() as mp:
        async def _noop_bg(complaint_id: str, force: bool = False):
            return None

        mp.setattr("app.api.v1.complaints.run_ai_triage_background", _noop_bg)

        comp = client.post("/api/v1/complaints", json={
            "title": "Waterlogging blocking main drainage culvert",
            "description": "Heavy water accumulation obstructing lane traffic outside metro exit.",
            "category": "DRAINAGE",
            "latitude": 17.4388,
            "longitude": 78.4944,
        }, headers=_headers(token)).json()
        cid = comp["id"]

        async def _failing_analyze(*args, **kwargs):
            raise RuntimeError("Upstream 503 https://generativelanguage.googleapis.com?key=AIzaFakeSecretKey987654321")

        mp.setattr(ai_service.mock_provider, "analyze_text", _failing_analyze)
        asyncio.run(ai_service.process_complaint_by_id(cid, session_factory=db_session_factory))

    detail = client.get(f"/api/v1/complaints/{cid}", headers=_headers(token)).json()
    assert detail["status"] == ComplaintStatus.UNDER_REVIEW.value
    assert detail["ai_processing_status"] == "FAILED"
    assert "AIzaFakeSecretKey" not in (detail["ai_processing_error"] or "")
    assert "[REDACTED]" in (detail["ai_processing_error"] or "")

    # Verify audit failure logged without leaking secret
    s = db_session_factory()
    try:
        fail_log = s.query(AuditLog).filter(AuditLog.entity_id == cid, AuditLog.action == "AI_TRIAGE_FAILED").first()
        assert fail_log is not None
        assert "AIzaFakeSecretKey" not in (fail_log.details or "")
    finally:
        s.close()

    # Trigger retry via /reanalyze-ai now that context restored real AI provider & background dispatcher
    reanalyze_resp = client.post(f"/api/v1/complaints/{cid}/reanalyze-ai", headers=_headers(token))
    assert reanalyze_resp.status_code == 200
    after_retry = client.get(f"/api/v1/complaints/{cid}", headers=_headers(token)).json()
    assert after_retry["ai_processing_status"] == "COMPLETED"


def test_a3_interrupted_job_startup_recovery(db_session_factory, test_actors):
    """Proves recover_interrupted_ai_jobs recovers stale interrupted AI_ANALYSIS_PENDING records."""
    c_a = test_actors["citizen_a"]["user"]
    comp = Complaint(
        reference_number=f"CF-2026-{uuid.uuid4().hex[:8].upper()}",
        citizen_id=c_a.id,
        title="Interrupted AI crash scenario",
        description="Simulating interrupted process restart while processing AI.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.44,
        longitude=78.49,
        status=ComplaintStatus.AI_ANALYSIS_PENDING.value,
        priority="P3",
        ai_processing_status="PROCESSING",
        ai_processing_started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    s = db_session_factory()
    try:
        s.add(comp)
        s.commit()
        cid = comp.id
    finally:
        s.close()

    recovered_count = recover_interrupted_ai_jobs(session_factory=db_session_factory)
    assert recovered_count == 1

    s2 = db_session_factory()
    try:
        updated = s2.query(Complaint).filter(Complaint.id == cid).first()
        assert updated.status == ComplaintStatus.UNDER_REVIEW.value
        assert updated.ai_processing_status == "FAILED"
    finally:
        s2.close()


# ---------------------------------------------------------------------------
# A2: Import-Time Startup Safety & Reversible Alembic Migrations
# ---------------------------------------------------------------------------

def test_a2_importing_app_main_executes_zero_ddl_and_zero_db_connect():
    """
    Runs a clean subprocess importing app.main while blocking SQLAlchemy engine connections
    to guarantee importing app.main performs ZERO DDL or database queries at import time.
    """
    backend_dir = Path(__file__).resolve().parent.parent
    script = "\n".join([
        "import os, sqlalchemy.engine.base",
        "os.environ['ENVIRONMENT'] = 'testing'",
        "def _boom(*a, **k):",
        "    raise AssertionError('DB connect attempted on import!')",
        "sqlalchemy.engine.base.Engine.connect = _boom",
        "import app.main",
        "assert app.main.app is not None",
        "print('IMPORT_CLEAN_OK')",
    ])
    res = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Import triggered unexpected DB operation: {res.stderr}"
    assert "IMPORT_CLEAN_OK" in res.stdout


def test_a2_alembic_upgrade_downgrade_and_postgres_sql(tmp_path):
    """Verifies Alembic upgrade/downgrade chain on isolated DB and offline PostgreSQL DDL compilation."""
    backend_dir = Path(__file__).resolve().parent.parent
    mig_db = tmp_path / "alembic_roundtrip.db"

    env = os.environ.copy()
    env["ENVIRONMENT"] = "testing"
    env["DATABASE_URL"] = f"sqlite:///{mig_db}"
    env["SECRET_KEY"] = "test_secret_key_for_alembic_verification_min_32_chars"

    up_res = subprocess.run(
        [sys.executable, "migrate.py"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    assert up_res.returncode == 0, up_res.stderr

    eng = create_engine(f"sqlite:///{mig_db}")
    insp = inspect(eng)
    assert "refresh_tokens" in insp.get_table_names()
    comp_cols = {c["name"] for c in insp.get_columns("complaints")}
    assert {"ai_processing_status", "ai_processing_error", "ai_processing_attempts"}.issubset(comp_cols)
    eng.dispose()

    down_res = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "adca60ea77e0"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    assert down_res.returncode == 0, down_res.stderr

    eng2 = create_engine(f"sqlite:///{mig_db}")
    insp2 = inspect(eng2)
    assert "refresh_tokens" not in insp2.get_table_names()
    assert "ai_processing_status" not in {c["name"] for c in insp2.get_columns("complaints")}
    eng2.dispose()

    reup_res = subprocess.run(
        [sys.executable, "migrate.py"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    assert reup_res.returncode == 0, reup_res.stderr

    # Offline PostgreSQL SQL compile verification (no live postgres required)
    pg_env = env.copy()
    pg_env["ENVIRONMENT"] = "production"
    pg_env["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"
    pg_sql = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "6b691e58bfaa:head", "--sql"],
        cwd=str(backend_dir),
        env=pg_env,
        capture_output=True,
        text=True,
    )
    assert pg_sql.returncode == 0, pg_sql.stderr
    assert "CREATE TABLE refresh_tokens" in pg_sql.stdout


# ---------------------------------------------------------------------------
# A4: Concurrent Collision-Safe Reference Number Generation
# ---------------------------------------------------------------------------

def test_a4_concurrent_reference_generation_and_integrity_retry(
    client, test_actors, db_session_factory, monkeypatch
):
    """
    Verifies concurrent complaint submissions allocate distinct CF-YYYY-... reference numbers
    AND bounded IntegrityError retry recovers automatically on forced reference collision.
    """
    c_a = test_actors["citizen_a"]
    token = _login(client, c_a["email"], c_a["password"])["access_token"]

    # Temporarily raise complaint rate limit in settings only for high-concurrency stress
    monkeypatch.setattr(limiter, "enabled", False)

    def _submit_one(idx: int):
        c = TestClient(client.app)
        return c.post("/api/v1/complaints", json={
            "title": f"Concurrent hazard report #{idx}",
            "description": "Concurrent pothole test submission across threads.",
            "category": "ROADS",
            "latitude": 17.440 + idx * 0.0001,
            "longitude": 78.490 + idx * 0.0001,
        }, headers=_headers(token))

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(_submit_one, range(12)))

    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    refs = [r.json()["reference_number"] for r in responses]
    assert len(set(refs)) == 12
    assert all(ref.startswith("CF-") for ref in refs)

    # Now force a collision on first attempt to verify IntegrityError retry recovers cleanly
    colliding_ref = refs[0]
    fresh_ref = f"CF-2026-{uuid.uuid4().hex[:8].upper()}"
    seq = iter([colliding_ref, fresh_ref])
    monkeypatch.setattr("app.api.v1.complaints.generate_reference_number", lambda: next(seq))

    retry_resp = client.post("/api/v1/complaints", json={
        "title": "Forced reference collision recovery",
        "description": "First generated reference collides and retries with a unique reference.",
        "category": "ROADS",
        "latitude": 17.449,
        "longitude": 78.499,
    }, headers=_headers(token))
    assert retry_resp.status_code == 201
    assert retry_resp.json()["reference_number"] == fresh_ref


# ---------------------------------------------------------------------------
# B1: CORS Production Restriction
# ---------------------------------------------------------------------------

def test_b1_cors_allows_supplied_prod_domain_and_blocks_arbitrary_vercel(monkeypatch):
    """Confirms middleware permits exact supplied Vercel domain and rejects attacker *.vercel.app."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/civicfix")
    monkeypatch.setenv("SECRET_KEY", "z" * 48)
    monkeypatch.delenv("BACKEND_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)

    prod_settings = Settings()
    allowed = prod_settings.get_effective_cors_origins()
    assert allowed == [PRODUCTION_FRONTEND_ORIGIN]

    # Check live app middleware rejects arbitrary vercel subdomain and allows actual production domain
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    probe_app = FastAPI()
    probe_app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @probe_app.get("/ping")
    def _ping():
        return {"ok": True}

    probe_client = TestClient(probe_app)

    good = probe_client.options(
        "/ping",
        headers={"Origin": "https://civic-fix-ai-plum.vercel.app", "Access-Control-Request-Method": "GET"},
    )
    assert good.headers.get("access-control-allow-origin") == "https://civic-fix-ai-plum.vercel.app"

    for untrusted in [
        "https://evil-clone.vercel.app",
        "https://attacker.example.com",
        "http://localhost:5173",
    ]:
        bad = probe_client.options(
            "/ping",
            headers={"Origin": untrusted, "Access-Control-Request-Method": "GET"},
        )
        assert bad.headers.get("access-control-allow-origin") is None


# ---------------------------------------------------------------------------
# B2: Complete Evidence File Authorization + Traversal Protection
# ---------------------------------------------------------------------------

def test_b2_evidence_authorization_all_roles_and_traversal_guards(client, test_actors, db_session):
    """
    Tests:
    - Unregistered physical files rejected (404) even for GOVERNMENT_ADMIN / MUNICIPAL_MEMBER.
    - Path traversal & unapproved folders rejected (400/404).
    - Citizens only view own non-internal attachments (internal & cross-citizen blocked with 403).
    - Field crew restricted strictly to assigned complaints/work orders.
    - Municipal member strictly restricted to matching department; member with NO membership denied (403).
    """
    adm = test_actors["admin"]
    staff_roads = test_actors["staff_roads"]
    staff_lighting = test_actors["staff_lighting"]
    crew_a = test_actors["crew_a"]
    crew_b = test_actors["crew_b"]
    c_a = test_actors["citizen_a"]
    c_b = test_actors["citizen_b"]

    t_adm = _login(client, adm["email"], adm["password"])["access_token"]
    t_roads = _login(client, staff_roads["email"], staff_roads["password"])["access_token"]
    t_light = _login(client, staff_lighting["email"], staff_lighting["password"])["access_token"]
    t_crew_a = _login(client, crew_a["email"], crew_a["password"])["access_token"]
    t_crew_b = _login(client, crew_b["email"], crew_b["password"])["access_token"]
    limiter._storage.reset()
    t_c_a = _login(client, c_a["email"], c_a["password"])["access_token"]
    t_c_b = _login(client, c_b["email"], c_b["password"])["access_token"]

    # Create a staff member with NO department membership
    no_dept_staff = User(
        email="orphan.staff@civicfix.gov",
        full_name="Unassigned Officer",
        hashed_password=adm["user"].hashed_password,
        role=UserRole.MUNICIPAL_MEMBER.value,
        is_active=True,
        is_verified=True,
    )
    db_session.add(no_dept_staff)
    db_session.commit()
    t_no_dept = _login(client, no_dept_staff.email, adm["password"])["access_token"]

    # Unregistered file on disk MUST return 404 even for Government Admin!
    rogue_file = storage_service.complaint_dir / "unregistered_secret.png"
    rogue_file.write_bytes(_make_tiny_png_bytes())
    assert client.get("/uploads/complaints/unregistered_secret.png", headers=_headers(t_adm)).status_code == 404
    assert client.get("/uploads/complaints/unregistered_secret.png", headers=_headers(t_roads)).status_code == 404

    # Path traversal & disallowed folder blocked
    assert client.get("/uploads/invalidfolder/secret.png", headers=_headers(t_adm)).status_code == 400
    assert client.get("/uploads/complaints/..secret.png", headers=_headers(t_adm)).status_code == 400

    # Citizen A submits ROADS complaint and attaches photo + internal staff attachment
    comp = client.post("/api/v1/complaints", json={
        "title": "Road cave-in outside depot",
        "description": "Large pavement subsidence along bus depot road.",
        "category": "ROADS",
        "latitude": 17.44,
        "longitude": 78.49,
    }, headers=_headers(t_c_a)).json()
    cid = comp["id"]

    # Assign work order to Crew A
    roads_dept_id = test_actors["departments"]["ROADS"].id
    client.post("/api/v1/admin/work-orders", json={
        "complaint_id": cid,
        "department_id": roads_dept_id,
        "crew_id": crew_a["user"].id,
        "title": "Repair subsidence",
        "instructions": "Rebuild base and seal.",
    }, headers=_headers(t_roads))

    att = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("pothole.png", _make_tiny_png_bytes(), "image/png")},
        data={"attachment_type": "CITIZEN_ORIGINAL"},
        headers=_headers(t_c_a),
    ).json()

    # Also add an internal staff attachment in DB for internal privacy check
    internal_bytes = _make_tiny_png_bytes()
    internal_path = storage_service.evidence_dir / "internal_only.png"
    internal_path.write_bytes(internal_bytes)
    internal_att = ComplaintAttachment(
        complaint_id=cid,
        file_name="internal_only.png",
        file_path="/uploads/evidence/internal_only.png",
        file_size=len(internal_bytes),
        mime_type="image/png",
        attachment_type="INTERNAL_STAFF_EVIDENCE",
        is_internal=True,
        uploaded_by_id=staff_roads["user"].id,
    )
    db_session.add(internal_att)
    db_session.commit()

    # Check both /api/v1/evidence/{id} and /uploads/... endpoints identically
    for url in [f"/api/v1/evidence/{att['id']}", att["file_path"]]:
        assert client.get(url).status_code == 401
        assert client.get(url, headers=_headers(t_c_a)).status_code == 200
        assert client.get(url, headers=_headers(t_c_b)).status_code == 403
        assert client.get(url, headers=_headers(t_crew_a)).status_code == 200
        assert client.get(url, headers=_headers(t_crew_b)).status_code == 403
        assert client.get(url, headers=_headers(t_roads)).status_code == 200
        assert client.get(url, headers=_headers(t_light)).status_code == 403
        assert client.get(url, headers=_headers(t_no_dept)).status_code == 403
        assert client.get(url, headers=_headers(t_adm)).status_code == 200

    # Internal evidence must be blocked for Citizen A (even on own complaint) & open to authorized staff
    for url in [f"/api/v1/evidence/{internal_att.id}", internal_att.file_path]:
        assert client.get(url, headers=_headers(t_c_a)).status_code == 403
        assert client.get(url, headers=_headers(t_roads)).status_code == 200
        assert client.get(url, headers=_headers(t_light)).status_code == 403


# ---------------------------------------------------------------------------
# B3: Refresh-Token Rotation, Logout Revocation & Reuse Detection
# ---------------------------------------------------------------------------

def test_b3_refresh_token_rotation_revocation_and_reuse_detection(client, test_actors, db_session):
    """
    Tests:
    - Raw refresh tokens are NEVER stored plaintext (SHA-256 hash in refresh_tokens).
    - Successful /auth/refresh rotates pair and revokes previous token.
    - Replay of rotated/revoked refresh token returns 401, revokes whole token family, and logs audit.
    - Logout revokes refresh capability.
    - Deactivated user cannot refresh.
    """
    c_a = test_actors["citizen_a"]
    login_data = _login(client, c_a["email"], c_a["password"])
    rt1 = login_data["refresh_token"]
    at1 = login_data["access_token"]

    stored = db_session.query(RefreshToken).filter(RefreshToken.user_id == c_a["user"].id).first()
    assert stored is not None
    assert stored.token_hash != rt1
    assert stored.token_hash == hash_token(rt1)
    assert stored.is_revoked is False

    # Rotate RT1 -> RT2
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
    assert r1.status_code == 200
    rt2 = r1.json()["refresh_token"]
    at2 = r1.json()["access_token"]
    assert rt2 != rt1
    assert at2 != at1

    # Replay of RT1 must fail with 401 AND revoke the entire family (including RT2!)
    replay_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
    assert replay_resp.status_code == 401

    rt2_after_reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": rt2})
    assert rt2_after_reuse.status_code == 401

    reuse_audit = db_session.query(AuditLog).filter(
        AuditLog.user_id == c_a["user"].id,
        AuditLog.action == "REFRESH_TOKEN_REUSE_DETECTED",
    ).first()
    assert reuse_audit is not None

    # Fresh login -> logout invalidates refresh capability
    limiter._storage.reset()
    sess2 = _login(client, c_a["email"], c_a["password"])
    rt_logout = sess2["refresh_token"]
    at_logout = sess2["access_token"]

    logout_resp = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": rt_logout},
        headers=_headers(at_logout),
    )
    assert logout_resp.status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rt_logout}).status_code == 401

    # Empty-body logout also invalidates active refresh tokens
    limiter._storage.reset()
    sess3 = _login(client, c_a["email"], c_a["password"])
    client.post("/api/v1/auth/logout", headers=_headers(sess3["access_token"]))
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": sess3["refresh_token"]}).status_code == 401

    # Deactivated account cannot refresh
    limiter._storage.reset()
    staff = test_actors["staff_lighting"]
    staff_sess = _login(client, staff["email"], staff["password"])
    adm = test_actors["admin"]
    t_adm = _login(client, adm["email"], adm["password"])["access_token"]

    deact = client.post(f"/api/v1/admin/users/{staff['user'].id}/deactivate", headers=_headers(t_adm))
    assert deact.status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": staff_sess["refresh_token"]}).status_code == 401


# ---------------------------------------------------------------------------
# B4: Bootstrap & Opt-In Seed Safety
# ---------------------------------------------------------------------------

def test_b4_bootstrap_and_seed_security_guards(db_session_factory, monkeypatch, capsys):
    """Verifies bootstrap refuses missing/short passwords and seed_demo_data requires explicit non-prod opt-in."""
    from bootstrap import bootstrap_admin
    from seed import seed_demo_data
    from app.core.config import settings

    with pytest.raises(ValueError):
        bootstrap_admin(email="admin@civicfix.gov", password="", full_name="Admin")
    with pytest.raises(ValueError):
        bootstrap_admin(email="admin@civicfix.gov", password="short", full_name="Admin")

    # Seed disabled in production
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEMO_SEEDING", "true")
    seed_demo_data(explicit_opt_in=True)
    s = db_session_factory()
    try:
        assert s.query(User).count() == 0
    finally:
        s.close()

    # Seed disabled in development without opt-in
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.delenv("ALLOW_DEMO_SEEDING", raising=False)
    seed_demo_data(explicit_opt_in=False)
    s2 = db_session_factory()
    try:
        assert s2.query(User).count() == 0
    finally:
        s2.close()

    # Opt-in seeding in non-prod never prints passwords
    monkeypatch.setenv("DEMO_CITIZEN_PASSWORD", "EphemeralTestOnlySecret99!")
    seed_demo_data(explicit_opt_in=True)
    captured = capsys.readouterr()
    assert "EphemeralTestOnlySecret99" not in captured.out
    assert "AdminSecure2026" not in captured.out


# ---------------------------------------------------------------------------
# D1 + D2: Public Metrics Real Calculation, Grouped Department Analytics & Scoping
# ---------------------------------------------------------------------------

def test_d1_public_impact_real_resolution_hours(client, test_actors, db_session):
    """Proves public /impact returns None when zero resolved tickets exist, and real computed hours otherwise."""
    empty_resp = client.get("/api/v1/public/impact")
    assert empty_resp.status_code == 200
    assert empty_resp.json()["average_resolution_hours"] is None

    now = datetime.now(timezone.utc)
    c1 = Complaint(
        reference_number=f"CF-2026-{uuid.uuid4().hex[:8].upper()}",
        citizen_id=test_actors["citizen_a"]["user"].id,
        title="Resolved streetlamp",
        description="Fixed 6 hours after report.",
        category=ComplaintCategory.STREETLIGHTS.value,
        latitude=17.44,
        longitude=78.49,
        status=ComplaintStatus.RESOLVED.value,
        priority="P2",
        ai_processing_status="COMPLETED",
        created_at=now - timedelta(hours=6),
        updated_at=now,
    )
    db_session.add(c1)
    db_session.flush()
    db_session.add(ResolutionVerification(
        complaint_id=c1.id,
        citizen_id=test_actors["citizen_a"]["user"].id,
        is_satisfied=True,
        feedback_rating=5,
        verified_at=now,
    ))
    db_session.commit()

    pop_resp = client.get("/api/v1/public/impact")
    assert pop_resp.status_code == 200
    assert pop_resp.json()["complaints_resolved"] == 1
    assert pop_resp.json()["average_resolution_hours"] == 6.0


def test_d2_grouped_department_analytics_and_cross_department_blocks(client, test_actors, db_session):
    """Verifies grouped analytics queries match expected semantics and cross-dept enforcement."""
    adm = test_actors["admin"]
    staff_roads = test_actors["staff_roads"]
    staff_lighting = test_actors["staff_lighting"]
    crew_b = test_actors["crew_b"]
    depts = test_actors["departments"]

    roads_id = depts["ROADS"].id
    light_id = depts["LIGHTING"].id

    # Seed controlled complaints across departments cleanly
    c_roads_open = Complaint(
        reference_number=f"CF-2026-{uuid.uuid4().hex[:8].upper()}",
        citizen_id=test_actors["citizen_a"]["user"].id,
        title="Open Roads Defect",
        description="Deep road crater awaiting repair.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.44,
        longitude=78.49,
        department_id=roads_id,
        status=ComplaintStatus.UNDER_REVIEW.value,
        priority="P1",
        ai_processing_status="COMPLETED",
    )
    c_roads_done = Complaint(
        reference_number=f"CF-2026-{uuid.uuid4().hex[:8].upper()}",
        citizen_id=test_actors["citizen_a"]["user"].id,
        title="Closed Roads Defect",
        description="Pothole repaired and confirmed.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.441,
        longitude=78.491,
        department_id=roads_id,
        status=ComplaintStatus.RESOLVED.value,
        priority="P2",
        ai_processing_status="COMPLETED",
    )
    c_light_open = Complaint(
        reference_number=f"CF-2026-{uuid.uuid4().hex[:8].upper()}",
        citizen_id=test_actors["citizen_b"]["user"].id,
        title="Dark Intersection Lamp",
        description="Streetlight pole off.",
        category=ComplaintCategory.STREETLIGHTS.value,
        latitude=17.442,
        longitude=78.492,
        department_id=light_id,
        status=ComplaintStatus.UNDER_REVIEW.value,
        priority="P2",
        ai_processing_status="COMPLETED",
    )
    db_session.add_all([c_roads_open, c_roads_done, c_light_open])
    db_session.commit()

    t_adm = _login(client, adm["email"], adm["password"])["access_token"]
    t_roads = _login(client, staff_roads["email"], staff_roads["password"])["access_token"]
    t_light = _login(client, staff_lighting["email"], staff_lighting["password"])["access_token"]
    t_crew_b = _login(client, crew_b["email"], crew_b["password"])["access_token"]

    # Check admin grouped analytics
    dash = client.get("/api/v1/admin/dashboard", headers=_headers(t_adm)).json()
    by_dept = {d["department_name"]: d for d in dash["by_department"]}
    assert by_dept[depts["ROADS"].name]["count"] == 2
    assert by_dept[depts["ROADS"].name]["resolved_count"] == 1
    assert by_dept[depts["ROADS"].name]["open_count"] == 1
    assert by_dept[depts["LIGHTING"].name]["count"] == 1
    assert by_dept[depts["LIGHTING"].name]["resolved_count"] == 0
    assert by_dept[depts["LIGHTING"].name]["open_count"] == 1

    # Check MUNICIPAL_MEMBER scoped dashboard only shows their department in by_department
    roads_dash = client.get("/api/v1/admin/dashboard", headers=_headers(t_roads)).json()
    assert [d["department_name"] for d in roads_dash["by_department"]] == [depts["ROADS"].name]

    # Check grouped /admin/departments counts
    dept_list = {d["code"]: d for d in client.get("/api/v1/admin/departments", headers=_headers(t_adm)).json()}
    assert dept_list["ROADS"]["member_count"] == 1
    assert dept_list["ROADS"]["crew_count"] == 1
    assert dept_list["ROADS"]["open_complaints_count"] == 1
    assert dept_list["LIGHTING"]["open_complaints_count"] == 1

    # Cross-department & unassigned crew mutation blocks (403)
    assert client.post(
        f"/api/v1/admin/complaints/{c_roads_open.id}/verify",
        json={"priority": "P1"},
        headers=_headers(t_light),
    ).status_code == 403
    assert client.post(
        f"/api/v1/admin/complaints/{c_roads_open.id}/assign",
        json={"department_id": light_id},
        headers=_headers(t_light),
    ).status_code == 403
    assert client.post(
        f"/api/v1/admin/complaints/{c_roads_open.id}/internal-note",
        json={"content": "Should be forbidden across departments"},
        headers=_headers(t_light),
    ).status_code == 403
    assert client.post(
        f"/api/v1/admin/complaints/{c_roads_open.id}/resolution",
        json={"resolution_notes": "Unassigned crew cannot submit resolution on another dept ticket."},
        headers=_headers(t_crew_b),
    ).status_code == 403
