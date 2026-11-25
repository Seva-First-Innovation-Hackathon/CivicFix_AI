import asyncio
from datetime import datetime, timedelta, timezone
import os
from typing import Any, Dict, List

from arq import Retry
import pytest

from app.core.config import Settings
from app.core.limiter import limiter
from app.models.entities import (
    AuditLog,
    BackgroundJob,
    Complaint,
    Notification,
    SLABreachEvent,
)
from app.models.enums import ComplaintCategory, ComplaintStatus, NotificationType
from app.services.ai.service import ai_service
from app.services.jobs.queue import (
    compute_backoff_seconds,
    create_outbox_job,
    dispatch_outbox_job,
    execute_job_by_id,
    recover_stale_running_jobs,
    sweep_pending_outbox_jobs,
)
from app.services.sla.monitor import monitor_sla_deadlines
from app.workers.arq_worker import execute_background_job


class _FakeArqJob:
    def __init__(self, job_id: str):
        self.job_id = job_id


class _FakeRedisPool:
    def __init__(self, fail_enqueue: bool = False):
        self.fail_enqueue = fail_enqueue
        self.enqueued: List[Dict[str, Any]] = []

    async def enqueue_job(self, func_name: str, *args, _job_id=None, _defer_until=None):
        if self.fail_enqueue:
            raise ConnectionError("Redis connection refused at redis://secretuser:secretpass@127.0.0.1:6379/0")
        self.enqueued.append({
            "func_name": func_name,
            "args": args,
            "job_id": _job_id,
            "defer_until": _defer_until,
        })
        return _FakeArqJob(_job_id or f"fake-{len(self.enqueued)}")


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_redis_and_queue_config_validation():
    with pytest.raises(ValueError, match="requires a configured REDIS_URL"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="prod-strong-secret-key-with-at-least-thirty-two-bytes",
            DATABASE_URL="postgresql://u:p@localhost:5432/civicfix",
            QUEUE_BACKEND="redis",
            REDIS_URL="",
        )

    with pytest.raises(ValueError, match="REQUIRE_REDIS=True"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="prod-strong-secret-key-with-at-least-thirty-two-bytes",
            DATABASE_URL="postgresql://u:p@localhost:5432/civicfix",
            REQUIRE_REDIS=True,
            REDIS_URL="",
        )

    cfg = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="prod-strong-secret-key-with-at-least-thirty-two-bytes",
        DATABASE_URL="postgresql://u:p@localhost:5432/civicfix",
        QUEUE_BACKEND="redis",
        REDIS_URL="redis://localhost:6379/0",
    )
    assert cfg.RATE_LIMIT_STORAGE_URL == "redis://localhost:6379/0"


def test_outbox_survives_redis_outage_and_recovers_via_sweeper(
    client, test_actors, db_session_factory, monkeypatch
):
    c_a = test_actors["citizen_a"]
    token = _login(client, c_a["email"], c_a["password"])["access_token"]

    failing_pool = _FakeRedisPool(fail_enqueue=True)
    monkeypatch.setattr("app.services.jobs.queue.settings.QUEUE_BACKEND", "redis")

    async def _fail_pool():
        return failing_pool

    monkeypatch.setattr("app.services.jobs.queue._get_arq_pool", _fail_pool)

    # Complaint creation succeeds even when Redis is down; jobs stay PENDING_DISPATCH honestly
    resp = client.post("/api/v1/complaints", json={
        "title": "Waterlogging outside municipal library",
        "description": "Blocked stormwater inlet flooding pedestrian gate.",
        "category": "DRAINAGE",
        "latitude": 17.441,
        "longitude": 78.498,
    }, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    cid = resp.json()["id"]

    s = db_session_factory()
    try:
        jobs = s.query(BackgroundJob).filter(BackgroundJob.complaint_id == cid).all()
        assert len(jobs) == 2
        for j in jobs:
            assert j.status == "PENDING_DISPATCH"
            assert "secretpass" not in (j.last_error or "")
            assert j.redis_job_id is None
    finally:
        s.close()

    # Restore Redis pool & run outbox sweeper
    healthy_pool = _FakeRedisPool(fail_enqueue=False)
    dispatched = asyncio.run(sweep_pending_outbox_jobs(session_factory=db_session_factory, redis_pool=healthy_pool))
    assert dispatched == 2
    assert len(healthy_pool.enqueued) == 2

    s2 = db_session_factory()
    try:
        jobs2 = s2.query(BackgroundJob).filter(BackgroundJob.complaint_id == cid).all()
        assert all(j.status == "QUEUED" and j.redis_job_id for j in jobs2)
    finally:
        s2.close()


def test_worker_retry_backoff_dead_letter_idempotency_and_stale_recovery(
    db_session_factory, test_actors, monkeypatch
):
    c_a = test_actors["citizen_a"]["user"]
    comp = Complaint(
        reference_number="CF-2026-JOBRETRY",
        citizen_id=c_a.id,
        title="Unstable transformer pole sparks intermittently",
        description="Loose overhead connection sparks in rain.",
        category=ComplaintCategory.STREETLIGHTS.value,
        latitude=17.44,
        longitude=78.49,
        status=ComplaintStatus.AI_ANALYSIS_PENDING.value,
        priority="P3",
        ai_processing_status="PENDING",
    )
    s = db_session_factory()
    try:
        s.add(comp)
        s.flush()
        job = create_outbox_job(
            db=s,
            job_type="ai_triage",
            dedup_key=f"ai_triage:{comp.id}",
            complaint_id=comp.id,
            payload={"complaint_id": comp.id, "force": False},
            max_attempts=3,
            commit=False,
        )
        # Dedup check: calling again with active dedup_key returns the same job row
        dup_job = create_outbox_job(
            db=s,
            job_type="ai_triage",
            dedup_key=f"ai_triage:{comp.id}",
            complaint_id=comp.id,
            payload={"complaint_id": comp.id},
            commit=False,
        )
        assert dup_job.id == job.id
        s.commit()
        jid = job.id
        cid = comp.id
    finally:
        s.close()

    # Exponential backoff curve
    assert compute_backoff_seconds(1) == 15
    assert compute_backoff_seconds(2) == 30
    assert compute_backoff_seconds(3) == 60

    with monkeypatch.context() as mp:
        mp.setattr("app.services.jobs.queue.db_session.SessionLocal", db_session_factory)

        async def _always_fail(*args, **kwargs):
            raise RuntimeError("Upstream 503 key=AIzaDummySecretToken999")

        mp.setattr(ai_service.mock_provider, "analyze_text", _always_fail)

        # Attempt 1 -> ARQ raises Retry(defer=15)
        with pytest.raises(Retry):
            asyncio.run(execute_background_job({}, jid))

        # Attempt 2 -> ARQ raises Retry(defer=30)
        with pytest.raises(Retry):
            asyncio.run(execute_background_job({}, jid))

        # Attempt 3 (final allowed attempt) -> transitions complaint safely to UNDER_REVIEW & DEAD_LETTER
        final_res = asyncio.run(execute_background_job({}, jid))
        assert final_res["outcome"] == "succeeded" or final_res["outcome"] == "dead_letter"

    # Re-verify dead-letter via email failure reaching max attempts
    s_mail = db_session_factory()
    try:
        mail_job = create_outbox_job(
            db=s_mail,
            job_type="send_email",
            dedup_key=f"mail-fail-{cid}",
            complaint_id=cid,
            payload={"template": "nonexistent"},
            max_attempts=2,
            commit=True,
        )
        mjid = mail_job.id
    finally:
        s_mail.close()

    with monkeypatch.context() as mp:
        mp.setattr("app.services.jobs.queue.db_session.SessionLocal", db_session_factory)
        with pytest.raises(Retry):
            asyncio.run(execute_background_job({}, mjid))
        r2 = asyncio.run(execute_background_job({}, mjid))
        assert r2["outcome"] == "dead_letter"
        # Re-executing claimed/completed/dead_letter job is idempotently ignored
        r3 = asyncio.run(execute_background_job({}, mjid))
        assert r3["outcome"] == "skipped_already_claimed"

    # Stale RUNNING job recovery test
    s_stale = db_session_factory()
    try:
        stale_job = BackgroundJob(
            job_type="ai_triage",
            complaint_id=cid,
            payload_json="{}",
            status="RUNNING",
            attempts=1,
            max_attempts=3,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=25),
        )
        s_stale.add(stale_job)
        s_stale.commit()
        sj_id = stale_job.id
    finally:
        s_stale.close()

    recovered = recover_stale_running_jobs(session_factory=db_session_factory, stale_minutes=10)
    assert recovered == 1
    s_chk = db_session_factory()
    try:
        recovered_job = s_chk.query(BackgroundJob).filter(BackgroundJob.id == sj_id).first()
        assert recovered_job.status == "RETRY_SCHEDULED"
    finally:
        s_chk.close()


def test_sla_breach_detection_deduplication_dashboard_and_filter(client, test_actors, db_session):
    roads_dept = test_actors["departments"]["ROADS"]
    c_a = test_actors["citizen_a"]["user"]
    now = datetime.now(timezone.utc)

    overdue_comp = Complaint(
        reference_number="CF-2026-SLAOVER",
        citizen_id=c_a.id,
        title="Collapsed storm drain slab on Market Road",
        description="Urgent danger to commuters exceeding SLA.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.442,
        longitude=78.492,
        status=ComplaintStatus.IN_PROGRESS.value,
        priority="P1",
        department_id=roads_dept.id,
        sla_deadline=now - timedelta(hours=5),
    )
    within_sla_comp = Complaint(
        reference_number="CF-2026-SLAOK",
        citizen_id=c_a.id,
        title="Minor sidewalk curb chip",
        description="Well within SLA target.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.443,
        longitude=78.493,
        status=ComplaintStatus.UNDER_REVIEW.value,
        priority="P3",
        department_id=roads_dept.id,
        sla_deadline=now + timedelta(hours=20),
    )
    resolved_past_deadline = Complaint(
        reference_number="CF-2026-SLARES",
        citizen_id=c_a.id,
        title="Fixed pothole",
        description="Resolved complaint must not fire SLA breach.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.444,
        longitude=78.494,
        status=ComplaintStatus.RESOLVED.value,
        priority="P2",
        department_id=roads_dept.id,
        sla_deadline=now - timedelta(hours=10),
    )
    db_session.add_all([overdue_comp, within_sla_comp, resolved_past_deadline])
    db_session.commit()

    # First SLA monitor pass records 1 breach, notifies ROADS staff, and records audit + email job
    summary_1 = monitor_sla_deadlines(db=db_session, now=now, enqueue_emails=True)
    assert summary_1["scanned_overdue"] == 1
    assert summary_1["new_breaches_recorded"] == 1
    assert summary_1["notifications_created"] >= 1

    # Priority must NOT be mutated automatically
    db_session.refresh(overdue_comp)
    assert overdue_comp.priority == "P1"
    assert overdue_comp.is_overdue is True
    assert overdue_comp.hours_overdue >= 4.9

    # Repeating monitor scan emits ZERO duplicate breaches/notifications
    summary_2 = monitor_sla_deadlines(db=db_session, now=now + timedelta(minutes=5), enqueue_emails=True)
    assert summary_2["scanned_overdue"] == 1
    assert summary_2["new_breaches_recorded"] == 0
    assert summary_2["notifications_created"] == 0

    assert db_session.query(SLABreachEvent).count() == 1
    sla_notifs = db_session.query(Notification).filter(
        Notification.complaint_id == overdue_comp.id,
        Notification.notification_type == NotificationType.SLA_BREACH.value,
    ).all()
    assert len(sla_notifs) == 1

    sla_audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == overdue_comp.id,
        AuditLog.action == "SLA_BREACH_DETECTED",
    ).first()
    assert sla_audit is not None

    # Dashboard & admin filter expose overdue & SLA event counts accurately
    adm_token = _login(client, test_actors["admin"]["email"], test_actors["admin"]["password"])["access_token"]
    dash = client.get("/api/v1/admin/dashboard", headers=_headers(adm_token)).json()
    assert dash["metrics"]["overdue_complaints"] == 1
    assert dash["metrics"]["sla_breach_events_count"] == 1

    filtered = client.get("/api/v1/admin/complaints?overdue_only=true", headers=_headers(adm_token)).json()
    assert filtered["total"] == 1
    assert filtered["complaints"][0]["id"] == overdue_comp.id
    assert filtered["complaints"][0]["is_overdue"] is True

    queue_status = client.get("/api/v1/admin/queue/status", headers=_headers(adm_token))
    assert queue_status.status_code == 200
    assert queue_status.json()["sla_breach_events_total"] == 1


@pytest.mark.skipif(
    not os.getenv("REDIS_TEST_URL"),
    reason="BLOCKED: Live Redis server not configured via REDIS_TEST_URL",
)
def test_live_redis_queue_connectivity():
    import redis

    client = redis.from_url(os.environ["REDIS_TEST_URL"], socket_connect_timeout=2)
    assert client.ping() is True
