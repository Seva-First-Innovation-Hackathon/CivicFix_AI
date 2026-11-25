from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any, Callable, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
import app.db.session as db_session
from app.models.entities import BackgroundJob

logger = logging.getLogger(__name__)

_SECRET_PATTERN = re.compile(
    r"(AIza[0-9A-Za-z\-_]{10,}|key=[^\s&]+|Bearer\s+[A-Za-z0-9\.\-_]+|redis[s]?://[^\s@]+@)",
    re.IGNORECASE,
)

ACTIVE_JOB_STATUSES = ("PENDING_DISPATCH", "QUEUED", "RUNNING", "RETRY_SCHEDULED")


def sanitize_job_error(exc: Exception) -> str:
    msg = _SECRET_PATTERN.sub("[REDACTED]", f"{type(exc).__name__}: {exc}")
    return msg[:480]


def compute_backoff_seconds(attempt_number: int) -> int:
    base = max(1, settings.JOB_RETRY_BASE_SECONDS)
    return min(300, base * (2 ** max(0, attempt_number - 1)))


def create_outbox_job(
    db: Session,
    job_type: str,
    payload: Optional[Dict[str, Any]] = None,
    complaint_id: Optional[str] = None,
    dedup_key: Optional[str] = None,
    max_attempts: Optional[int] = None,
    commit: bool = False,
) -> BackgroundJob:
    """
    Persists a background job in the transactional outbox table.
    Deduplicates against still-active jobs sharing the same dedup_key so redeliveries
    or concurrent clicks never queue duplicate work.
    """
    if dedup_key:
        existing = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.dedup_key == dedup_key,
                BackgroundJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .first()
        )
        if existing:
            return existing

    job = BackgroundJob(
        job_type=job_type,
        dedup_key=dedup_key,
        complaint_id=complaint_id,
        payload_json=json.dumps(payload or {}, sort_keys=True),
        status="PENDING_DISPATCH",
        attempts=0,
        max_attempts=max_attempts or settings.JOB_MAX_ATTEMPTS,
        next_run_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.flush()
    if commit:
        db.commit()
        db.refresh(job)
    return job


async def _get_arq_pool():
    from arq import create_pool
    from arq.connections import RedisSettings

    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


async def dispatch_outbox_job(
    db: Session,
    job: BackgroundJob,
    redis_pool=None,
) -> str:
    """
    Dispatches an outbox job to Redis/ARQ when enabled.
    CRITICAL RELIABILITY INVARIANT: Only marks status='QUEUED' AFTER Redis confirms enqueue.
    If Redis enqueue fails, preserves status='PENDING_DISPATCH' so the outbox sweeper recovers it.
    """
    queue_mode = (settings.QUEUE_BACKEND or "inline").strip().lower()
    if queue_mode not in {"redis", "arq"}:
        return job.status

    created_local_pool = False
    pool = redis_pool
    try:
        if pool is None:
            pool = await _get_arq_pool()
            created_local_pool = True

        defer_until = None
        if job.next_run_at:
            next_run_utc = (
                job.next_run_at.replace(tzinfo=timezone.utc)
                if job.next_run_at.tzinfo is None
                else job.next_run_at.astimezone(timezone.utc)
            )
            if next_run_utc > datetime.now(timezone.utc):
                defer_until = next_run_utc

        arq_job = await pool.enqueue_job(
            "execute_background_job",
            job.id,
            _job_id=f"cf-{job.id}-try-{job.attempts + 1}",
            _defer_until=defer_until,
        )
        job.status = "QUEUED"
        job.dispatched_at = datetime.now(timezone.utc)
        job.redis_job_id = getattr(arq_job, "job_id", f"cf-{job.id}")
        db.commit()
        return job.status
    except Exception as exc:
        logger.warning(
            "Redis/ARQ enqueue failed for outbox job %s (%s); retaining PENDING_DISPATCH for recovery: %s",
            job.id,
            job.job_type,
            sanitize_job_error(exc),
        )
        job.status = "PENDING_DISPATCH"
        job.last_error = sanitize_job_error(exc)
        db.commit()
        return job.status
    finally:
        if created_local_pool and pool is not None and hasattr(pool, "aclose"):
            await pool.aclose()


async def _run_send_email_job(payload: Dict[str, Any]) -> None:
    from app.services.email.service import email_service

    template = payload.get("template")
    if template == "submission_acknowledgment":
        ok = await email_service.send_submission_acknowledgment(
            to_email=payload["to_email"],
            citizen_name=payload.get("citizen_name", "Citizen"),
            reference_number=payload["reference_number"],
            title=payload.get("title", ""),
            category=payload.get("category", ""),
            complaint_id=payload["complaint_id"],
        )
    elif template == "status_update":
        ok = await email_service.send_status_update(
            to_email=payload["to_email"],
            recipient_name=payload.get("recipient_name", "Citizen"),
            reference_number=payload["reference_number"],
            old_status=payload["old_status"],
            new_status=payload["new_status"],
            reason=payload.get("reason"),
            complaint_id=payload["complaint_id"],
        )
    elif template == "resolution_ready":
        ok = await email_service.send_resolution_awaiting_verification(
            to_email=payload["to_email"],
            citizen_name=payload.get("citizen_name", "Citizen"),
            reference_number=payload["reference_number"],
            completion_notes=payload.get("completion_notes", ""),
            complaint_id=payload["complaint_id"],
        )
    elif template == "resolution_verified":
        ok = await email_service.send_resolution_confirmed_or_reopened(
            to_email=payload["to_email"],
            recipient_name=payload.get("recipient_name", "Citizen"),
            reference_number=payload["reference_number"],
            is_satisfied=bool(payload.get("is_satisfied", True)),
            notes=payload.get("notes"),
            complaint_id=payload["complaint_id"],
        )
    elif template == "sla_breach":
        ok = await email_service.send_sla_breach_alert(
            to_email=payload["to_email"],
            recipient_name=payload.get("recipient_name", "Municipal Officer"),
            reference_number=payload["reference_number"],
            priority=payload.get("priority", "P3"),
            hours_overdue=float(payload.get("hours_overdue", 0.0)),
            complaint_id=payload["complaint_id"],
        )
    else:
        raise ValueError(f"Unsupported email outbox template: {template}")

    if not ok:
        raise RuntimeError(f"Email delivery failed for template={template}")


async def execute_job_by_id(
    job_id: str,
    session_factory: Optional[Callable[[], Session]] = None,
) -> Dict[str, Any]:
    """
    Executes an outbox job inside an isolated SessionLocal with atomic claim, idempotency,
    and bounded exponential retry scheduling on failure.
    """
    factory = session_factory or db_session.SessionLocal
    db = factory()
    try:
        now = datetime.now(timezone.utc)
        claimable = ("PENDING_DISPATCH", "QUEUED", "RETRY_SCHEDULED")
        claimed = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.id == job_id,
                BackgroundJob.status.in_(claimable),
            )
            .update(
                {
                    BackgroundJob.status: "RUNNING",
                    BackgroundJob.started_at: now,
                    BackgroundJob.attempts: BackgroundJob.attempts + 1,
                    BackgroundJob.last_error: None,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if claimed != 1:
            return {"job_id": job_id, "outcome": "skipped_already_claimed"}

        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if not job:
            return {"job_id": job_id, "outcome": "not_found"}

        payload = json.loads(job.payload_json or "{}")
        attempt = job.attempts

        try:
            if job.job_type == "ai_triage":
                from app.services.ai.service import ai_service

                cid = payload.get("complaint_id") or job.complaint_id
                force = bool(payload.get("force", False))
                final_attempt = attempt >= job.max_attempts
                await ai_service.process_complaint_by_id(
                    complaint_id=cid,
                    session_factory=factory,
                    force=force or attempt > 1,
                    raise_on_failure=not final_attempt,
                )
            elif job.job_type == "send_email":
                await _run_send_email_job(payload)
            elif job.job_type == "sla_monitor":
                from app.services.sla.monitor import monitor_sla_deadlines

                monitor_sla_deadlines(db=db)
            else:
                raise ValueError(f"Unknown background job_type: {job.job_type}")

            job.status = "SUCCEEDED"
            job.completed_at = datetime.now(timezone.utc)
            job.last_error = None
            db.commit()
            return {"job_id": job.id, "job_type": job.job_type, "outcome": "succeeded", "attempts": attempt}

        except Exception as exc:
            err_msg = sanitize_job_error(exc)
            now_fail = datetime.now(timezone.utc)
            if attempt < job.max_attempts:
                delay_sec = compute_backoff_seconds(attempt)
                job.status = "RETRY_SCHEDULED"
                job.next_run_at = now_fail + timedelta(seconds=delay_sec)
                job.last_error = err_msg
                db.commit()
                logger.warning(
                    "Job %s (%s) attempt %d/%d failed (%s); scheduled retry in %ds.",
                    job.id,
                    job.job_type,
                    attempt,
                    job.max_attempts,
                    err_msg,
                    delay_sec,
                )
                return {
                    "job_id": job.id,
                    "job_type": job.job_type,
                    "outcome": "retry",
                    "defer_seconds": delay_sec,
                    "error": err_msg,
                }

            job.status = "DEAD_LETTER"
            job.completed_at = now_fail
            job.last_error = err_msg
            db.commit()
            logger.error(
                "Job %s (%s) moved to DEAD_LETTER after %d attempts: %s",
                job.id,
                job.job_type,
                attempt,
                err_msg,
            )
            return {
                "job_id": job.id,
                "job_type": job.job_type,
                "outcome": "dead_letter",
                "attempts": attempt,
                "error": err_msg,
            }
    finally:
        db.close()


async def run_outbox_job_background(
    job_id: str,
    session_factory: Optional[Callable[[], Session]] = None,
) -> Dict[str, Any]:
    """FastAPI BackgroundTasks adapter for inline (non-Redis) execution mode."""
    return await execute_job_by_id(job_id=job_id, session_factory=session_factory)


async def dispatch_or_execute_outbox_job(
    job_id: str,
    session_factory: Optional[Callable[[], Session]] = None,
) -> None:
    """
    Unified post-commit dispatcher used by sync and async API routes alike:
    - When QUEUE_BACKEND is redis/arq: dispatches the committed outbox row to Redis.
    - When QUEUE_BACKEND is inline: executes via isolated SessionLocal worker helper.
    """
    factory = session_factory or db_session.SessionLocal
    queue_mode = (settings.QUEUE_BACKEND or "inline").strip().lower()
    if queue_mode in {"redis", "arq"}:
        db = factory()
        try:
            job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
            if job:
                await dispatch_outbox_job(db=db, job=job)
        finally:
            db.close()
    else:
        await execute_job_by_id(job_id=job_id, session_factory=factory)


async def sweep_pending_outbox_jobs(
    session_factory: Optional[Callable[[], Session]] = None,
    redis_pool=None,
    limit: int = 50,
) -> int:
    """
    Re-enqueues missed PENDING_DISPATCH jobs (e.g. after temporary Redis unavailability)
    and due RETRY_SCHEDULED jobs.
    """
    factory = session_factory or db_session.SessionLocal
    db = factory()
    dispatched = 0
    try:
        now = datetime.now(timezone.utc)
        jobs = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.status.in_(("PENDING_DISPATCH", "RETRY_SCHEDULED")),
                BackgroundJob.next_run_at <= now,
            )
            .order_by(BackgroundJob.created_at.asc())
            .limit(limit)
            .all()
        )
        queue_mode = (settings.QUEUE_BACKEND or "inline").strip().lower()
        for job in jobs:
            if queue_mode in {"redis", "arq"}:
                new_status = await dispatch_outbox_job(db=db, job=job, redis_pool=redis_pool)
                if new_status == "QUEUED":
                    dispatched += 1
            else:
                res = await execute_job_by_id(job_id=job.id, session_factory=factory)
                if res.get("outcome") == "succeeded":
                    dispatched += 1
        return dispatched
    finally:
        db.close()


def recover_stale_running_jobs(
    session_factory: Optional[Callable[[], Session]] = None,
    stale_minutes: int = 10,
) -> int:
    """
    Recovers background jobs left stuck in RUNNING after a sudden worker crash or restart.
    """
    factory = session_factory or db_session.SessionLocal
    db = factory()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=max(1, stale_minutes))
        stuck = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.status == "RUNNING",
                BackgroundJob.started_at.isnot(None),
                BackgroundJob.started_at < cutoff,
            )
            .all()
        )
        recovered = 0
        for job in stuck:
            if job.attempts < job.max_attempts:
                job.status = "RETRY_SCHEDULED"
                job.next_run_at = now
                job.last_error = "Recovered after interrupted worker execution."
            else:
                job.status = "DEAD_LETTER"
                job.completed_at = now
                job.last_error = "Worker interrupted on final allowed attempt."
            recovered += 1
        if recovered:
            db.commit()
            logger.warning("Recovered %d stale RUNNING background jobs.", recovered)
        return recovered
    except Exception as exc:
        logger.warning("Skipping stale job recovery: %s", exc)
        db.rollback()
        return 0
    finally:
        db.close()


def get_queue_status_summary(db: Session) -> Dict[str, Any]:
    counts_raw = (
        db.query(BackgroundJob.status, func.count(BackgroundJob.id))
        .group_by(BackgroundJob.status)
        .all()
    )
    by_status = {status_name: int(cnt) for status_name, cnt in counts_raw}
    backlog = (
        by_status.get("PENDING_DISPATCH", 0)
        + by_status.get("QUEUED", 0)
        + by_status.get("RETRY_SCHEDULED", 0)
    )
    return {
        "queue_backend": (settings.QUEUE_BACKEND or "inline").lower(),
        "redis_configured": bool((settings.REDIS_URL or "").strip()),
        "backlog_count": backlog,
        "by_status": by_status,
    }


def check_queue_and_worker_health(
    db: Session,
    redis_client=None,
) -> Dict[str, Any]:
    """
    Evaluates honest runtime readiness of Redis, ARQ worker heartbeat, rate-limiter backend,
    and production durability guarantees without exposing secrets.
    Never reports durable queue readiness as healthy in production when Redis or worker is absent.
    """
    from app.core import limiter as limiter_module

    queue_summary = get_queue_status_summary(db)
    queue_backend = queue_summary["queue_backend"]
    is_prod = settings.ENVIRONMENT.lower() == "production"
    redis_configured = queue_summary["redis_configured"]

    redis_connected: Optional[bool] = None
    worker_alive: Optional[bool] = None
    worker_last_heartbeat: Optional[str] = None
    warnings = []

    if redis_configured or redis_client is not None:
        try:
            client = redis_client
            if client is None:
                import redis
                client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            redis_connected = bool(client.ping())
            raw_hb = client.get("civicfix:worker:last_heartbeat")
            if raw_hb:
                hb_str = raw_hb.decode("utf-8") if isinstance(raw_hb, (bytes, bytearray)) else str(raw_hb)
                worker_last_heartbeat = hb_str
                try:
                    hb_dt = datetime.fromisoformat(hb_str)
                    if hb_dt.tzinfo is None:
                        hb_dt = hb_dt.replace(tzinfo=timezone.utc)
                    worker_alive = (datetime.now(timezone.utc) - hb_dt).total_seconds() <= 300
                except ValueError:
                    worker_alive = False
            else:
                worker_alive = False
        except Exception:
            redis_connected = False
            worker_alive = False

    durable_queue = bool(
        queue_backend in {"redis", "arq"} and redis_connected is True and worker_alive is True
    )

    if queue_backend in {"redis", "arq"}:
        if not redis_connected:
            warnings.append("Configured Redis queue backend is unreachable.")
        elif not worker_alive:
            warnings.append("ARQ worker heartbeat missing or stale (>300s); queued jobs will not execute until worker.py runs.")
    elif is_prod:
        warnings.append("Production running with QUEUE_BACKEND=inline (in-process fallback; non-durable across deploys).")

    if is_prod and limiter_module.RATE_LIMITER_MODE != "redis":
        warnings.append(f"Rate limiter mode is '{limiter_module.RATE_LIMITER_MODE}' instead of distributed Redis.")

    if is_prod:
        overall_status = "healthy" if (durable_queue and limiter_module.RATE_LIMITER_MODE == "redis") else "degraded"
    else:
        overall_status = "degraded" if (queue_backend in {"redis", "arq"} and not durable_queue) else "healthy"

    return {
        "status": overall_status,
        "durable_queue": durable_queue,
        "queue": queue_summary,
        "redis_connected": redis_connected,
        "worker_alive": worker_alive,
        "worker_last_heartbeat": worker_last_heartbeat,
        "rate_limiter_mode": limiter_module.RATE_LIMITER_MODE,
        "warnings": warnings,
    }
