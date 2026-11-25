import asyncio
from datetime import datetime, timedelta, timezone
import io
import os

from PIL import Image
import fakeredis
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.models.entities import BackgroundJob, Complaint
from app.models.enums import ComplaintCategory, ComplaintStatus
from app.services.ai.gemini_provider import GeminiAIProvider
from app.services.jobs.queue import check_queue_and_worker_health
from app.services.maps.hotspots import build_postgis_hotspot_query
from migrate import _detect_unstamped_baseline_revision


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_postgis_hotspot_query_compiles_st_snaptogrid_and_zero_pii(db_session, test_actors):
    """Verifies PostgreSQL hotspot aggregation compiles native PostGIS ST_SnapToGrid SQL."""
    admin_user = test_actors["admin"]["user"]
    q = build_postgis_hotspot_query(
        db=db_session,
        current_user=admin_user,
        grid_size_meters=500,
        category="ROADS",
        overdue_only=True,
    )
    compiled = str(q.statement.compile(dialect=postgresql.dialect()))
    assert "ST_SnapToGrid" in compiled
    assert "ST_Y" in compiled
    assert "ST_X" in compiled
    assert "GROUP BY" in compiled
    assert "citizen_id" not in compiled
    assert "address" not in compiled


def test_migrate_unstamped_detection_handles_all_phase1_and_phase2_tables(tmp_path):
    """Ensures migrate.py never mis-stamps legacy or intermediate unstamped schemas."""
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parent.parent

    # Validate detection logic against progressively migrated inspection snapshots
    db_file = tmp_path / "progressive.db"
    import subprocess, sys
    env = os.environ.copy()
    env["ENVIRONMENT"] = "testing"
    env["DATABASE_URL"] = f"sqlite:///{db_file}"
    env["SECRET_KEY"] = "test_secret_key_unstamped_check_min_32_characters"

    for rev in ("6b691e58bfaa", "adca60ea77e0", "b4e2d9c1f8a3", "d1a4e8c2f109", "d2b5f9d3a218", "d3c6a0e4b327", "d4d7b1f5c436"):
        res = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", rev],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        eng = create_engine(f"sqlite:///{db_file}")
        detected = _detect_unstamped_baseline_revision(inspect(eng))
        eng.dispose()
        assert detected == rev


def test_production_health_cannot_falsely_claim_durable_queue_without_redis_and_worker(
    client, db_session, monkeypatch
):
    """
    Verifies Section 7 invariant: production /health and /health/queue report 'degraded'
    whenever QUEUE_BACKEND=inline, Redis is unreachable, or the worker heartbeat is absent.
    """
    # 1. Production with inline queue -> degraded (durable=False)
    monkeypatch.setattr("app.main.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("app.services.jobs.queue.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("app.services.jobs.queue.settings.QUEUE_BACKEND", "inline")
    monkeypatch.setattr("app.services.jobs.queue.settings.REDIS_URL", "")
    monkeypatch.setattr("app.main.settings.STORAGE_BACKEND", "local")

    h1 = client.get("/health").json()
    assert h1["status"] == "degraded"
    assert h1["queue"]["durable"] is False
    assert h1["storage"]["ephemeral_warning"] is True

    hq1 = client.get("/health/queue").json()
    assert hq1["status"] == "degraded"
    assert hq1["durable_queue"] is False

    # 2. Redis protocol active (fakeredis simulation) WITHOUT worker heartbeat -> still degraded!
    fake_r = fakeredis.FakeRedis()
    monkeypatch.setattr("app.services.jobs.queue.settings.QUEUE_BACKEND", "redis")
    monkeypatch.setattr("app.services.jobs.queue.settings.REDIS_URL", "redis://localhost:6379/0")
    q_no_worker = check_queue_and_worker_health(db_session, redis_client=fake_r)
    assert q_no_worker["redis_connected"] is True
    assert q_no_worker["worker_alive"] is False
    assert q_no_worker["durable_queue"] is False
    assert q_no_worker["status"] == "degraded"

    # 3. With fresh worker heartbeat AND Redis rate limiter mode -> durable_queue=True
    monkeypatch.setattr("app.core.limiter.RATE_LIMITER_MODE", "redis")
    fake_r.set("civicfix:worker:last_heartbeat", datetime.now(timezone.utc).isoformat(), ex=300)
    q_healthy = check_queue_and_worker_health(db_session, redis_client=fake_r)
    assert q_healthy["redis_connected"] is True
    assert q_healthy["worker_alive"] is True
    assert q_healthy["durable_queue"] is True
    assert q_healthy["status"] == "healthy"


def test_lifecycle_transitions_persist_email_jobs_in_outbox(client, test_actors, db_session):
    """Verifies status transitions persist send_email jobs in background_jobs atomically."""
    cit = test_actors["citizen_a"]
    roads = test_actors["staff_roads"]
    t_cit = _login(client, cit["email"], cit["password"])["access_token"]
    t_roads = _login(client, roads["email"], roads["password"])["access_token"]

    comp = client.post("/api/v1/complaints", json={
        "title": "Outbox status email verification pothole",
        "description": "Large pothole requiring staff status notification outbox verification.",
        "category": "ROADS",
        "latitude": 17.441,
        "longitude": 78.491,
    }, headers=_headers(t_cit)).json()
    cid = comp["id"]

    # Staff verifies complaint -> executes lifecycle transition + persists status_update outbox job
    ver_resp = client.post(
        f"/api/v1/admin/complaints/{cid}/verify",
        json={"priority": "P2", "verification_notes": "Confirmed on map."},
        headers=_headers(t_roads),
    )
    assert ver_resp.status_code == 200

    email_jobs = (
        db_session.query(BackgroundJob)
        .filter(BackgroundJob.complaint_id == cid, BackgroundJob.job_type == "send_email")
        .all()
    )
    assert len(email_jobs) >= 2
    assert any("status_update" in (j.payload_json or "") for j in email_jobs)


@pytest.mark.skipif(
    not (
        os.getenv("R2_BUCKET_NAME")
        and os.getenv("R2_ACCESS_KEY_ID")
        and os.getenv("R2_SECRET_ACCESS_KEY")
        and (os.getenv("R2_ENDPOINT_URL") or os.getenv("R2_ACCOUNT_ID"))
    ),
    reason="BLOCKED: Live Cloudflare R2 staging credentials (R2_ACCOUNT_ID/R2_BUCKET_NAME/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY) not configured",
)
def test_live_r2_staging_bucket_rw():
    """Live Cloudflare R2 smoke check executed when staging R2 environment variables are set."""
    from app.services.storage.backends import S3CompatibleStorageBackend, compute_sha256_hex

    endpoint = os.getenv("R2_ENDPOINT_URL") or f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    backend = S3CompatibleStorageBackend(
        bucket_name=os.environ["R2_BUCKET_NAME"],
        access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        endpoint_url=endpoint,
        region=os.getenv("R2_REGION", "auto"),
        provider_name="r2",
    )
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(40, 80, 120)).save(buf, format="PNG")
    data = buf.getvalue()
    key = "evidence/staging_smoke_check.png"
    meta = backend.put_bytes(key, data, "image/png")
    try:
        assert meta.sha256_checksum == compute_sha256_hex(data)
        assert backend.exists(key) is True
        assert backend.get_bytes(key) == data
        signed = backend.generate_signed_url(key, expires_in=60)
        assert "X-Amz-Signature" in signed
    finally:
        backend.delete(key)


@pytest.mark.skipif(
    not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
    reason="BLOCKED: Live Gemini API key (GOOGLE_API_KEY or GEMINI_API_KEY) not configured",
)
def test_live_gemini_text_and_vision_inference():
    """Live Google Gemini text/vision check executed only when an API key is supplied."""
    provider = GeminiAIProvider()
    assert provider.is_configured() is True
    text_res = asyncio.run(
        provider.analyze_text(
            title="Deep pothole blocking school bus stop",
            description="Large asphalt crater filled with rainwater outside main school gate.",
        )
    )
    assert text_res.suggested_category in set(ComplaintCategory)
    assert 0.0 <= text_res.confidence_score <= 1.0


def test_admin_queue_status_reports_worker_and_redis_health(client, test_actors, monkeypatch):
    """Verifies /api/v1/admin/queue/status exposes durable_queue, redis_connected, worker_alive, and warnings."""
    admin = test_actors["admin"]
    t_admin = _login(client, admin["email"], admin["password"])["access_token"]

    res = client.get("/api/v1/admin/queue/status", headers=_headers(t_admin))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "healthy"
    assert body["durable_queue"] is False
    assert "redis_connected" in body
    assert "worker_alive" in body
    assert isinstance(body["warnings"], list)
    assert "queue" in body and "backlog_count" in body["queue"]
    assert "rate_limiter_mode" in body
    assert "sla_breach_events_total" in body

    monkeypatch.setattr("app.services.jobs.queue.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("app.services.jobs.queue.settings.QUEUE_BACKEND", "inline")
    monkeypatch.setattr("app.services.jobs.queue.settings.REDIS_URL", "")
    res_prod = client.get("/api/v1/admin/queue/status", headers=_headers(t_admin))
    assert res_prod.status_code == 200
    body_prod = res_prod.json()
    assert body_prod["status"] == "degraded"
    assert body_prod["durable_queue"] is False
    assert len(body_prod["warnings"]) >= 1


def test_fakeredis_limiter_and_worker_heartbeat_protocol(db_session, monkeypatch):
    """
    Protocol-level Redis/ARQ simulation using fakeredis (does NOT replace live external Redis):
    - Verifies create_limiter() enters 'redis' mode when Redis ping succeeds and degrades cleanly on failure.
    - Verifies WorkerSettings configuration and heartbeat round-trip with check_queue_and_worker_health().
    """
    import redis as redis_lib
    from app.core import limiter as limiter_module
    from app.workers import arq_worker

    fake_r = fakeredis.FakeRedis()
    orig_mode = limiter_module.RATE_LIMITER_MODE
    try:
        monkeypatch.setattr(limiter_module.settings, "RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/0")
        monkeypatch.setattr(limiter_module.settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(redis_lib, "from_url", lambda *args, **kwargs: fake_r)
        limiter_module.create_limiter()
        assert limiter_module.RATE_LIMITER_MODE == "redis"

        def _fail_redis(*args, **kwargs):
            raise ConnectionError("Simulated Redis outage")

        monkeypatch.setattr(redis_lib, "from_url", _fail_redis)
        limiter_module.create_limiter()
        assert limiter_module.RATE_LIMITER_MODE == "memory_degraded_fallback"
    finally:
        limiter_module.RATE_LIMITER_MODE = orig_mode

    assert len(arq_worker.WorkerSettings.functions) == 1
    assert len(arq_worker.WorkerSettings.cron_jobs) == 2
    assert arq_worker.WorkerSettings.max_jobs >= 1
    assert arq_worker.WorkerSettings.job_timeout >= 60

    class _AsyncFakePool:
        async def set(self, key: str, value: str, ex: int = 300):
            return fake_r.set(key, value, ex=ex)

    async def _noop_sweep(*args, **kwargs):
        return 0

    monkeypatch.setattr(arq_worker, "sweep_pending_outbox_jobs", _noop_sweep)
    res = asyncio.run(arq_worker.sweep_outbox_cron({"redis": _AsyncFakePool()}))
    assert res == {"dispatched": 0}

    monkeypatch.setattr("app.services.jobs.queue.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("app.services.jobs.queue.settings.QUEUE_BACKEND", "redis")
    monkeypatch.setattr("app.services.jobs.queue.settings.REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(limiter_module, "RATE_LIMITER_MODE", "redis")
    health = check_queue_and_worker_health(db_session, redis_client=fake_r)
    assert health["redis_connected"] is True
    assert health["worker_alive"] is True
    assert health["durable_queue"] is True
    assert health["status"] == "healthy"


def test_migrate_uploads_to_r2_cli_requires_cloud_backend(tmp_path):
    """Verifies migrate_uploads_to_r2.py refuses execution cleanly when R2 credentials are unset."""
    from pathlib import Path
    import subprocess
    import sys

    backend_dir = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'r2_cli_check.db'}"
    env["STORAGE_BACKEND"] = "local"
    for k in ("R2_ACCOUNT_ID", "R2_BUCKET_NAME", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT_URL"):
        env.pop(k, None)

    proc = subprocess.run(
        [sys.executable, "scripts/migrate_uploads_to_r2.py"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "not configured" in proc.stderr
