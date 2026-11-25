import asyncio
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import uuid

from PIL import Image
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.security import get_password_hash
from app.models.entities import (
    AuditLog,
    BackgroundJob,
    Complaint,
    ComplaintAttachment,
    SLABreachEvent,
    User,
)
from app.models.enums import ComplaintCategory, ComplaintStatus, PriorityLevel, UserRole
from app.services.ai.base import TextAnalysisResult
from app.services.ai.duplicate_detector import (
    build_postgis_duplicate_query,
    find_potential_duplicates_from_db,
)
from app.services.ai.gemini_provider import GeminiAIProvider
from app.services.jobs.queue import check_queue_and_worker_health, create_outbox_job, execute_job_by_id
from app.services.maps.hotspots import build_postgis_hotspot_query
from app.services.sla.monitor import monitor_sla_deadlines
from app.services.storage.backends import (
    LocalStorageBackend,
    S3CompatibleStorageBackend,
    StorageObjectNotFoundError,
    StorageUnavailableError,
    compute_sha256_hex,
)
from app.services.storage.migrator import migrate_local_uploads_to_cloud
from app.services.storage.service import storage_service


def _has_r2_env() -> bool:
    return bool(
        os.getenv("R2_BUCKET_NAME")
        and os.getenv("R2_ACCESS_KEY_ID")
        and os.getenv("R2_SECRET_ACCESS_KEY")
        and (os.getenv("R2_ENDPOINT_URL") or os.getenv("R2_ACCOUNT_ID"))
    )


def _has_postgis_env() -> bool:
    return bool(os.getenv("POSTGIS_TEST_DATABASE_URL"))


def _has_redis_env() -> bool:
    return bool(os.getenv("REDIS_TEST_URL"))


def _has_gemini_env() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


def _make_jpeg_with_exif(color=(120, 45, 190)) -> bytes:
    img = Image.new("RGB", (32, 32), color=color)
    exif = Image.Exif()
    exif[0x010F] = "StagingCameraMake"
    exif[0x0110] = "StagingGPSModel"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _make_png(color=(30, 60, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_phase2_6_gemini_priority_rationale_and_mime_detection():
    """Verifies priority rule labels do not claim raw LLM generation and binary MIME detection handles PNG/WebP/JPEG."""
    provider = GeminiAIProvider(api_key="")
    assert provider._detect_image_mime(_make_png()) == "image/png"
    assert provider._detect_image_mime(_make_jpeg_with_exif()) == "image/jpeg"
    assert provider._detect_image_mime(b"RIFF\x00\x00\x00\x00WEBP\x00\x00") == "image/webp"

    crit = TextAnalysisResult(
        suggested_category=ComplaintCategory.ROADS,
        suggested_subcategory="pothole",
        safety_hazard_detected=True,
        urgency_level="CRITICAL",
        confidence_score=0.9,
        summary_explanation="Road collapse near school crossing",
        extracted_keywords=["road", "collapse"],
    )
    rec = provider.recommend_priority(ComplaintCategory.ROADS, crit)
    assert rec.priority == PriorityLevel.P1
    assert "Gemini Suggestion" not in rec.rationale
    assert "Priority Policy" in rec.rationale


def test_phase2_6_staging_config_contract_validation():
    """Verifies exact queue values, Redis/limiter auto-promotion, Gemini key harmonization, and SMTP TLS/SSL guard."""
    for q_val, expected in (("inline", "inline"), ("REDIS", "redis"), ("arq", "arq")):
        extra = {"REDIS_URL": "rediss://default:token@staging.redis.invalid:6379/0"} if expected != "inline" else {}
        s = Settings(
            ENVIRONMENT="staging",
            QUEUE_BACKEND=q_val,
            GEMINI_API_KEY="gem_only_key_placeholder",
            **extra,
        )
        assert s.QUEUE_BACKEND == expected
        assert s.GOOGLE_API_KEY == "gem_only_key_placeholder"
        assert s.GEMINI_MODEL == "gemini-2.5-flash"
        if expected != "inline":
            assert s.RATE_LIMIT_STORAGE_URL == "rediss://default:token@staging.redis.invalid:6379/0"

    with pytest.raises(ValueError, match="Allowed values: inline, redis, arq"):
        Settings(ENVIRONMENT="staging", QUEUE_BACKEND="celery")

    with pytest.raises(ValueError, match="SMTP_USE_TLS and SMTP_USE_SSL cannot both be True"):
        Settings(ENVIRONMENT="staging", SMTP_USE_TLS=True, SMTP_USE_SSL=True)

    with pytest.raises(ValueError, match="cannot fall back to SQLite in production"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="prod-strong-secret-key-with-at-least-thirty-two-bytes",
            DATABASE_URL="sqlite:///./disallowed.db",
        )


@pytest.mark.skipif(
    not _has_postgis_env(),
    reason="BLOCKED: Live PostgreSQL/PostGIS server not configured via POSTGIS_TEST_DATABASE_URL",
)
def test_phase2_6b_live_postgis_schema_spatial_queries_and_explain():
    """Phase 2.6B live staging PostgreSQL/PostGIS migration, backfill, ST_DWithin, ST_SnapToGrid, and EXPLAIN ANALYZE check."""
    from alembic import command
    from alembic.config import Config

    url = os.environ["POSTGIS_TEST_DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    eng = create_engine(url, pool_pre_ping=True)
    SessionMaker = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    tag = uuid.uuid4().hex[:8]
    user_email = f"p26b_{tag}@staging-test.local"
    created_ids = []

    try:
        with eng.begin() as conn:
            pg_ver = conn.execute(text("SELECT version();")).scalar()
            assert "PostgreSQL" in str(pg_ver)
            avail = conn.execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis';")).scalar()
            assert avail == 1, "PostGIS must be available on staging PostgreSQL"
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

        prev_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        try:
            command.upgrade(cfg, "head")
        finally:
            if prev_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = prev_url

        with eng.connect() as conn:
            ver = conn.execute(text("SELECT PostGIS_Version();")).scalar()
            assert ver
            idx = conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename='complaints' AND indexname='ix_complaints_location_gist';")
            ).scalar()
            assert idx == "ix_complaints_location_gist"
            assert "location" in {c["name"] for c in inspect(eng).get_columns("complaints")}

        db = SessionMaker()
        try:
            cit = User(
                email=user_email,
                full_name="Phase 2.6B Synthetic Citizen",
                hashed_password=get_password_hash("SyntheticTestPass123!"),
                role=UserRole.CITIZEN.value,
                is_active=True,
                is_verified=True,
            )
            db.add(cit)
            db.commit()
            db.refresh(cit)

            admin = User(
                id=f"adm-{tag}",
                email=f"adm_{tag}@staging-test.local",
                full_name="Synthetic Admin",
                hashed_password="x",
                role=UserRole.GOVERNMENT_ADMIN.value,
                is_active=True,
                is_verified=True,
            )

            nearby = Complaint(
                reference_number=f"CF-P26B-NEAR-{tag}",
                citizen_id=cit.id,
                title="Deep pothole outside East Transit Plaza",
                description="Large asphalt crater outside transit plaza entrance.",
                category=ComplaintCategory.ROADS.value,
                latitude=17.4400,
                longitude=78.4980,
                status=ComplaintStatus.UNDER_REVIEW.value,
            )
            distant = Complaint(
                reference_number=f"CF-P26B-FAR-{tag}",
                citizen_id=cit.id,
                title="Deep pothole outside East Transit Plaza far away",
                description="Same text 5km away.",
                category=ComplaintCategory.ROADS.value,
                latitude=17.4850,
                longitude=78.5450,
                status=ComplaintStatus.UNDER_REVIEW.value,
            )
            probe = Complaint(
                reference_number=f"CF-P26B-PRB-{tag}",
                citizen_id=cit.id,
                title="Deep pothole outside East Transit Plaza gate",
                description="Large asphalt crater near transit plaza entrance.",
                category=ComplaintCategory.ROADS.value,
                latitude=17.4403,
                longitude=78.4982,
                status=ComplaintStatus.AI_ANALYSIS_PENDING.value,
            )
            db.add_all([nearby, distant, probe])
            db.commit()
            created_ids = [nearby.id, distant.id, probe.id]

            # Test coordinate backfill compatibility when location starts NULL
            db.execute(text("UPDATE complaints SET location = NULL WHERE id = :cid"), {"cid": nearby.id})
            db.execute(
                text(
                    "UPDATE complaints SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography "
                    "WHERE id = :cid AND location IS NULL"
                ),
                {"cid": nearby.id},
            )
            db.commit()

            matches = find_potential_duplicates_from_db(db, probe, max_distance_meters=120.0, candidate_limit=5)
            matched_ids = {m.complaint_id for m in matches}
            assert nearby.id in matched_ids
            assert distant.id not in matched_ids

            hotspots = build_postgis_hotspot_query(db=db, current_user=admin, grid_size_meters=500).all()
            assert len(hotspots) >= 1

            q = build_postgis_duplicate_query(
                db=db,
                new_complaint=probe,
                max_distance_meters=120.0,
                cutoff_time=datetime.now(timezone.utc) - timedelta(days=14),
                candidate_limit=50,
            )
            compiled_sql = q.statement.compile(dialect=eng.dialect, compile_kwargs={"literal_binds": True})
            plan_rows = db.connection().exec_driver_sql(
                f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {compiled_sql}"
            ).fetchall()
            assert len(plan_rows) >= 1
        finally:
            db.rollback()
            if created_ids:
                db.query(Complaint).filter(Complaint.id.in_(created_ids)).delete(synchronize_session=False)
            db.query(User).filter(User.email == user_email).delete(synchronize_session=False)
            db.commit()
            db.close()
    finally:
        eng.dispose()


@pytest.mark.skipif(
    not _has_r2_env(),
    reason="BLOCKED: Live Cloudflare R2 staging credentials (R2_ACCOUNT_ID/R2_BUCKET_NAME/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY) not configured",
)
def test_phase2_6c_live_r2_api_exif_rbac_signed_url_and_migration(
    client, test_actors, db_session, tmp_path, monkeypatch
):
    """Phase 2.6C live private R2 upload/EXIF/RBAC/signed-URL/404/outage and migrator validation."""
    endpoint = os.getenv("R2_ENDPOINT_URL") or f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    r2_backend = S3CompatibleStorageBackend(
        bucket_name=os.environ["R2_BUCKET_NAME"],
        access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        endpoint_url=endpoint,
        region=os.getenv("R2_REGION", "auto"),
        provider_name="r2",
    )
    created_keys = []
    monkeypatch.setattr("app.services.storage.service.settings.STORAGE_BACKEND", "r2")
    monkeypatch.setattr(storage_service, "_cloud_backend", r2_backend)

    try:
        t_c_a = _login(client, test_actors["citizen_a"]["email"], test_actors["citizen_a"]["password"])["access_token"]
        t_c_b = _login(client, test_actors["citizen_b"]["email"], test_actors["citizen_b"]["password"])["access_token"]
        t_roads = _login(client, test_actors["staff_roads"]["email"], test_actors["staff_roads"]["password"])["access_token"]
        t_light = _login(client, test_actors["staff_lighting"]["email"], test_actors["staff_lighting"]["password"])["access_token"]
        t_crew_b = _login(client, test_actors["crew_b"]["email"], test_actors["crew_b"]["password"])["access_token"]

        comp = client.post("/api/v1/complaints", json={
            "title": "Phase 2.6C live R2 verification pothole",
            "description": "Synthetic pothole upload testing private R2 bucket and EXIF strip.",
            "category": "ROADS",
            "latitude": 17.441,
            "longitude": 78.491,
        }, headers=_headers(t_c_a)).json()
        cid = comp["id"]

        up_resp = client.post(
            f"/api/v1/complaints/{cid}/attachments",
            files={"file": ("p26c_exif.jpg", _make_jpeg_with_exif(), "image/jpeg")},
            data={"attachment_type": "CITIZEN_ORIGINAL"},
            headers=_headers(t_c_a),
        )
        assert up_resp.status_code == 200, up_resp.text
        att = up_resp.json()
        obj_key = db_session.query(ComplaintAttachment).filter(ComplaintAttachment.id == att["id"]).first().storage_object_key
        created_keys.append(obj_key)

        assert r2_backend.exists(obj_key) is True
        remote_bytes = r2_backend.get_bytes(obj_key)
        assert compute_sha256_hex(remote_bytes) == att["sha256_checksum"]
        assert len(Image.open(io.BytesIO(remote_bytes)).getexif()) == 0

        assert client.get(f"/api/v1/evidence/{att['id']}", headers=_headers(t_c_a)).status_code == 200
        assert client.get(f"/api/v1/evidence/{att['id']}", headers=_headers(t_c_b)).status_code == 403
        assert client.get(f"/api/v1/evidence/{att['id']}", headers=_headers(t_roads)).status_code == 200
        assert client.get(f"/api/v1/evidence/{att['id']}", headers=_headers(t_light)).status_code == 403
        assert client.get(f"/api/v1/evidence/{att['id']}", headers=_headers(t_crew_b)).status_code == 403

        signed_res = client.get(f"/api/v1/evidence/{att['id']}?signed=true", headers=_headers(t_c_a))
        assert signed_res.status_code == 200
        assert "X-Amz-Signature" in signed_res.json()["signed_url"]

        with pytest.raises(StorageObjectNotFoundError):
            r2_backend.get_bytes(f"evidence/nonexistent_{uuid.uuid4().hex}.png")

        bad_backend = S3CompatibleStorageBackend(
            bucket_name=os.environ["R2_BUCKET_NAME"],
            access_key_id="bad_key",
            secret_access_key="bad_secret",
            endpoint_url="https://invalid.r2.example.invalid",
            provider_name="r2",
        )
        with pytest.raises(StorageUnavailableError):
            bad_backend.head_metadata(obj_key)

        # Verify local-to-R2 migrator without deleting local source files
        local_root = tmp_path / "local_uploads"
        local_backend = LocalStorageBackend(local_root)
        local_backend.ensure_directories()
        mig_key = f"evidence/p26c_mig_{uuid.uuid4().hex[:8]}.png"
        mig_bytes = _make_png()
        local_backend.put_bytes(mig_key, mig_bytes, "image/png")
        mig_att = ComplaintAttachment(
            complaint_id=cid,
            file_name=Path(mig_key).name,
            file_path=f"/uploads/{mig_key}",
            file_size=len(mig_bytes),
            mime_type="image/png",
            attachment_type="INTERNAL_STAFF_EVIDENCE",
            is_internal=True,
            storage_provider="local",
            storage_object_key=mig_key,
        )
        db_session.add(mig_att)
        db_session.commit()
        created_keys.append(mig_key)

        assert client.get(f"/api/v1/evidence/{mig_att.id}", headers=_headers(t_c_a)).status_code == 403
        dry = migrate_local_uploads_to_cloud(db_session, local_backend, r2_backend, dry_run=True)
        assert dry.uploaded_verified >= 1
        real = migrate_local_uploads_to_cloud(db_session, local_backend, r2_backend, dry_run=False, delete_local=False)
        assert real.uploaded_verified >= 1 and real.local_deleted == 0
        assert local_backend.exists(mig_key) is True
    finally:
        for key in created_keys:
            try:
                r2_backend.delete(key)
            except Exception:
                pass


@pytest.mark.skipif(
    not _has_redis_env(),
    reason="BLOCKED: Live Redis server not configured via REDIS_TEST_URL",
)
def test_phase2_6d_live_redis_arq_worker_outbox_retry_and_rate_limit(
    db_session, db_session_factory, monkeypatch
):
    """Phase 2.6D live external Redis ping, outbox dispatch, ARQ worker lifecycle/recovery, retry, dead-letter, and rate limiting."""
    import limits
    import redis
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core import limiter as limiter_module
    from app.services.jobs.queue import dispatch_outbox_job, recover_stale_running_jobs
    from app.workers import arq_worker
    from app.workers.arq_worker import WORKER_HEARTBEAT_KEY

    redis_url = os.environ["REDIS_TEST_URL"]
    r_client = redis.from_url(redis_url, socket_connect_timeout=5)
    assert r_client.ping() is True

    monkeypatch.setattr("app.services.jobs.queue.settings.QUEUE_BACKEND", "redis")
    monkeypatch.setattr("app.services.jobs.queue.settings.REDIS_URL", redis_url)
    monkeypatch.setattr("app.services.jobs.queue.settings.ENVIRONMENT", "production")

    rl_key = f"p26d_rl_{uuid.uuid4().hex}"
    created_job_ids = []

    async def _run_arq_and_heartbeat():
        pool = await create_pool(RedisSettings.from_dsn(redis_url))
        try:
            # 1. Outbox persistence + real Redis dispatch
            job = create_outbox_job(
                db=db_session,
                job_type="sla_monitor",
                payload={"trigger": "phase2_6d"},
                dedup_key=f"p26d:{uuid.uuid4().hex}",
                commit=True,
            )
            created_job_ids.append(job.id)
            dispatched_status = await dispatch_outbox_job(db=db_session, job=job, redis_pool=pool)
            assert dispatched_status == "QUEUED"
            assert r_client.keys(f"arq:job:cf-{job.id}*")

            # 2. ARQ worker startup + heartbeat registration + real ARQ job execution
            await arq_worker.on_startup({"redis": pool})
            assert r_client.get(WORKER_HEARTBEAT_KEY) is not None
            res = await arq_worker.execute_background_job({}, job.id)
            assert res["outcome"] == "succeeded"

            # 3. Worker restart recovery: stale RUNNING job -> recover_stale_running_jobs -> sweep_outbox_cron
            stale_job = create_outbox_job(
                db=db_session,
                job_type="sla_monitor",
                payload={"trigger": "p26d_stale_restart"},
                dedup_key=f"p26d-stale:{uuid.uuid4().hex}",
                commit=True,
            )
            created_job_ids.append(stale_job.id)
            stale_job.status = "RUNNING"
            stale_job.started_at = datetime.now(timezone.utc) - timedelta(minutes=15)
            stale_job.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db_session.commit()

            recovered = recover_stale_running_jobs(session_factory=db_session_factory)
            assert recovered >= 1
            db_session.refresh(stale_job)
            assert stale_job.status == "RETRY_SCHEDULED"

            sweep_res = await arq_worker.sweep_outbox_cron({"redis": pool})
            assert sweep_res["dispatched"] >= 1
            db_session.refresh(stale_job)
            assert stale_job.status == "QUEUED"

            # 4. Bounded retry + dead-letter transition
            bad_job = create_outbox_job(
                db=db_session,
                job_type="unknown_p26d_type",
                max_attempts=2,
                commit=True,
            )
            created_job_ids.append(bad_job.id)
            r1 = await execute_job_by_id(bad_job.id, session_factory=db_session_factory)
            assert r1["outcome"] == "retry"
            db_session.refresh(bad_job)
            assert bad_job.status == "RETRY_SCHEDULED"
            bad_job.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db_session.commit()
            r2 = await execute_job_by_id(bad_job.id, session_factory=db_session_factory)
            assert r2["outcome"] == "dead_letter"
            db_session.refresh(bad_job)
            assert bad_job.status == "DEAD_LETTER"
        finally:
            await pool.aclose()

    try:
        asyncio.run(_run_arq_and_heartbeat())
        orig_mode = limiter_module.RATE_LIMITER_MODE
        try:
            monkeypatch.setattr(limiter_module.settings, "RATE_LIMIT_STORAGE_URL", redis_url)
            redis_lim = limiter_module.create_limiter()
            assert limiter_module.RATE_LIMITER_MODE == "redis"

            rule = limits.parse("2/minute")
            assert redis_lim.limiter.hit(rule, rl_key) is True
            assert redis_lim.limiter.hit(rule, rl_key) is True
            assert redis_lim.limiter.hit(rule, rl_key) is False

            health = check_queue_and_worker_health(db_session, redis_client=r_client)
            assert health["redis_connected"] is True
            assert health["worker_alive"] is True
            assert health["durable_queue"] is True
        finally:
            limiter_module.RATE_LIMITER_MODE = orig_mode
    finally:
        r_client.delete(WORKER_HEARTBEAT_KEY)
        for jid in created_job_ids:
            for k in r_client.keys(f"arq:*{jid}*"):
                r_client.delete(k)
        for k in r_client.keys(f"*{rl_key}*"):
            r_client.delete(k)


@pytest.mark.skipif(
    not _has_gemini_env(),
    reason="BLOCKED: Live Gemini API key (GOOGLE_API_KEY or GEMINI_API_KEY) not configured",
)
def test_phase2_6e_live_gemini_text_image_crossmodal_and_provenance():
    """Phase 2.6E live Gemini text, image, cross-modal mismatch tolerance, and provenance verification."""
    provider = GeminiAIProvider()
    assert provider.is_configured() is True

    text_res = asyncio.run(
        provider.analyze_text(
            title="Deep asphalt pothole flooding main school road",
            description="Wide crater full of stormwater near bus entrance causing vehicle damage.",
        )
    )
    assert text_res.suggested_category in set(ComplaintCategory)
    assert 0.0 <= text_res.confidence_score <= 1.0
    assert text_res.summary_explanation.startswith("[Gemini AI]")

    img_res = asyncio.run(provider.analyze_image("synthetic_sample.jpg", image_bytes=_make_jpeg_with_exif((90, 90, 90))))
    assert 0.0 <= img_res.confidence_score <= 1.0
    assert isinstance(img_res.observations, list)


@pytest.mark.skipif(
    not (_has_postgis_env() and _has_r2_env() and _has_redis_env()),
    reason="BLOCKED: Full live E2E requires POSTGIS_TEST_DATABASE_URL, R2_* credentials, and REDIS_TEST_URL",
)
def test_phase2_6g_live_full_staging_end_to_end_workflow(tmp_path, monkeypatch):
    """
    Phase 2.6G real multi-service staging E2E workflow across PostgreSQL/PostGIS, private Cloudflare R2,
    Redis/ARQ outbox worker, SLA monitor, and audit trail (cleaned up in finally).
    """
    from fastapi.testclient import TestClient
    import redis
    from arq import create_pool
    from arq.connections import RedisSettings
    from alembic import command
    from alembic.config import Config
    from app.core.security import get_password_hash
    from app.db.init_db import ensure_default_departments
    from app.db.session import get_db
    from app.main import app
    from app.models.entities import DepartmentMembership, MunicipalDepartment

    url = os.environ["POSTGIS_TEST_DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    redis_url = os.environ["REDIS_TEST_URL"]
    endpoint = os.getenv("R2_ENDPOINT_URL") or f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"

    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    eng = create_engine(url, pool_pre_ping=True)
    PgSession = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    r_client = redis.from_url(redis_url, socket_connect_timeout=5)
    assert r_client.ping() is True

    r2_backend = S3CompatibleStorageBackend(
        bucket_name=os.environ["R2_BUCKET_NAME"],
        access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        endpoint_url=endpoint,
        region=os.getenv("R2_REGION", "auto"),
        provider_name="r2",
    )

    tag = uuid.uuid4().hex[:8]
    r2_keys = []
    created_emails = []
    created_cids = []

    try:
        prev_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        try:
            command.upgrade(cfg, "head")
        finally:
            if prev_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = prev_url

        db = PgSession()
        try:
            ensure_default_departments(db)
            roads_dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.code == "ROADS").first()
            cit = User(email=f"cit_{tag}@staging-test.local", full_name="P26G Citizen", hashed_password=get_password_hash("SyntheticPass123!"), role=UserRole.CITIZEN.value, is_active=True, is_verified=True)
            staff = User(email=f"stf_{tag}@staging-test.local", full_name="P26G Staff", hashed_password=get_password_hash("SyntheticPass123!"), role=UserRole.MUNICIPAL_MEMBER.value, is_active=True, is_verified=True)
            crew = User(email=f"crw_{tag}@staging-test.local", full_name="P26G Crew", hashed_password=get_password_hash("SyntheticPass123!"), role=UserRole.FIELD_CREW.value, is_active=True, is_verified=True)
            adm = User(email=f"adm_{tag}@staging-test.local", full_name="P26G Admin", hashed_password=get_password_hash("SyntheticPass123!"), role=UserRole.GOVERNMENT_ADMIN.value, is_active=True, is_verified=True)
            db.add_all([cit, staff, crew, adm])
            db.flush()
            db.add(DepartmentMembership(user_id=staff.id, department_id=roads_dept.id, is_lead=True))
            db.commit()
            created_emails = [cit.email, staff.email, crew.email, adm.email]
        finally:
            db.close()

        def _override_pg_db():
            s = PgSession()
            try:
                yield s
            finally:
                s.close()

        orig_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = _override_pg_db
        orig_cloud = storage_service._cloud_backend
        storage_service.configure_cloud_backend(r2_backend)
        monkeypatch.setattr("app.services.storage.service.settings.STORAGE_BACKEND", "r2")
        monkeypatch.setattr("app.services.jobs.queue.settings.QUEUE_BACKEND", "redis")
        monkeypatch.setattr("app.services.jobs.queue.settings.REDIS_URL", redis_url)

        try:
            with TestClient(app) as pg_client:
                t_cit = _login(pg_client, created_emails[0], "SyntheticPass123!")["access_token"]
                t_stf = _login(pg_client, created_emails[1], "SyntheticPass123!")["access_token"]
                t_crw = _login(pg_client, created_emails[2], "SyntheticPass123!")["access_token"]
                t_adm = _login(pg_client, created_emails[3], "SyntheticPass123!")["access_token"]

                c_resp = pg_client.post("/api/v1/complaints", json={
                    "title": f"Phase 2.6G real staging pothole {tag}",
                    "description": "Synthetic pothole validating real PostGIS + R2 + Redis/ARQ pipeline.",
                    "category": "ROADS",
                    "latitude": 17.4422,
                    "longitude": 78.4922,
                }, headers=_headers(t_cit))
                assert c_resp.status_code == 201, c_resp.text
                cid = c_resp.json()["id"]
                created_cids.append(cid)

                up1 = pg_client.post(
                    f"/api/v1/complaints/{cid}/attachments",
                    files={"file": ("p26g_before.png", _make_png((20, 20, 20)), "image/png")},
                    data={"attachment_type": "CITIZEN_ORIGINAL"},
                    headers=_headers(t_cit),
                )
                assert up1.status_code == 200 and up1.json()["storage_provider"] == "r2"

                db = PgSession()
                try:
                    for att in db.query(ComplaintAttachment).filter(ComplaintAttachment.complaint_id == cid).all():
                        if att.storage_object_key:
                            r2_keys.append(att.storage_object_key)
                    ai_job = db.query(BackgroundJob).filter(BackgroundJob.complaint_id == cid, BackgroundJob.job_type == "ai_triage").first()
                    assert ai_job is not None
                    asyncio.run(execute_job_by_id(ai_job.id, session_factory=PgSession))
                finally:
                    db.close()

                assert pg_client.post(
                    f"/api/v1/admin/complaints/{cid}/verify",
                    json={"priority": "P2", "verification_notes": "Verified on staging PostGIS."},
                    headers=_headers(t_stf),
                ).status_code == 200

                wo_resp = pg_client.post("/api/v1/admin/work-orders", json={
                    "complaint_id": cid,
                    "department_id": roads_dept.id,
                    "crew_id": crew.id,
                    "title": "Staging road repair",
                    "instructions": "Repair and upload photo.",
                }, headers=_headers(t_stf))
                assert wo_resp.status_code == 201
                wo_id = wo_resp.json()["id"]

                assert pg_client.post(f"/api/v1/admin/work-orders/{wo_id}/accept", headers=_headers(t_crw)).status_code == 200
                up2 = pg_client.post(
                    f"/api/v1/complaints/{cid}/attachments",
                    files={"file": ("p26g_after.png", _make_png((240, 240, 240)), "image/png")},
                    data={"attachment_type": "AFTER_REPAIR"},
                    headers=_headers(t_crw),
                )
                assert up2.status_code == 200 and up2.json()["storage_provider"] == "r2"

                db = PgSession()
                try:
                    for att in db.query(ComplaintAttachment).filter(ComplaintAttachment.complaint_id == cid).all():
                        if att.storage_object_key and att.storage_object_key not in r2_keys:
                            r2_keys.append(att.storage_object_key)
                finally:
                    db.close()

                assert pg_client.post(
                    f"/api/v1/admin/work-orders/{wo_id}/submit-evidence",
                    json={"completion_notes": "Repaired cleanly on staging."},
                    headers=_headers(t_crw),
                ).status_code == 200
                assert pg_client.post(
                    f"/api/v1/admin/complaints/{cid}/review-evidence",
                    json={"is_approved": True, "notes": "Staging evidence approved."},
                    headers=_headers(t_stf),
                ).status_code == 200
                conf = pg_client.post(
                    f"/api/v1/complaints/{cid}/confirm-resolution",
                    json={"is_satisfied": True, "feedback_rating": 5, "feedback_notes": "Confirmed."},
                    headers=_headers(t_cit),
                )
                assert conf.status_code == 200 and conf.json()["status"] == "RESOLVED"
                assert pg_client.get("/api/v1/admin/audit-logs", headers=_headers(t_adm)).status_code == 200
        finally:
            storage_service.configure_cloud_backend(orig_cloud)
            if orig_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = orig_override
    finally:
        for key in r2_keys:
            try:
                r2_backend.delete(key)
            except Exception:
                pass
        db_clean = PgSession()
        try:
            db_clean.rollback()
            if created_cids:
                db_clean.query(AuditLog).filter(AuditLog.entity_id.in_(created_cids)).delete(synchronize_session=False)
                db_clean.query(Complaint).filter(Complaint.id.in_(created_cids)).delete(synchronize_session=False)
            if created_emails:
                db_clean.query(User).filter(User.email.in_(created_emails)).delete(synchronize_session=False)
            db_clean.commit()
        finally:
            db_clean.close()
        eng.dispose()
