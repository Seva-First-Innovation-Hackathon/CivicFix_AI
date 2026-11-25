from datetime import datetime, timezone
import logging

from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
import app.db.session as db_session
from app.services.ai.service import recover_interrupted_ai_jobs
from app.services.jobs.queue import (
    execute_job_by_id,
    recover_stale_running_jobs,
    sweep_pending_outbox_jobs,
)
from app.services.sla.monitor import monitor_sla_deadlines

logger = logging.getLogger(__name__)

WORKER_HEARTBEAT_KEY = "civicfix:worker:last_heartbeat"


async def execute_background_job(ctx: dict, job_id: str):
    """ARQ worker entrypoint executing persisted BackgroundJob rows with independent DB sessions."""
    result = await execute_job_by_id(job_id=job_id)
    outcome = result.get("outcome")
    if outcome == "retry":
        defer_sec = int(result.get("defer_seconds", 15))
        raise Retry(defer=defer_sec)
    return result


async def sweep_outbox_cron(ctx: dict):
    """Periodic task recovering PENDING_DISPATCH / due RETRY_SCHEDULED jobs."""
    redis_pool = ctx.get("redis")
    count = await sweep_pending_outbox_jobs(redis_pool=redis_pool, limit=50)
    if redis_pool is not None:
        try:
            await redis_pool.set(WORKER_HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=300)
        except Exception:
            pass
    return {"dispatched": count}


async def monitor_sla_cron(ctx: dict):
    """Periodic SLA deadline breach detector run independently inside worker."""
    db = db_session.SessionLocal()
    try:
        summary = monitor_sla_deadlines(db=db, enqueue_emails=True)
        redis_pool = ctx.get("redis")
        if redis_pool is not None:
            await sweep_pending_outbox_jobs(redis_pool=redis_pool, limit=25)
            await redis_pool.set(WORKER_HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=300)
        return summary
    finally:
        db.close()


async def on_startup(ctx: dict):
    logger.info("Starting CivicFix ARQ worker (max_jobs=%d)...", settings.WORKER_MAX_JOBS)
    recover_stale_running_jobs()
    recover_interrupted_ai_jobs()
    redis_pool = ctx.get("redis")
    if redis_pool is not None:
        try:
            await redis_pool.set(WORKER_HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=300)
        except Exception as exc:
            logger.warning("Worker heartbeat registration skipped: %s", exc)
    await sweep_pending_outbox_jobs(redis_pool=redis_pool, limit=50)


async def on_shutdown(ctx: dict):
    logger.info("CivicFix ARQ worker shutting down gracefully.")


class WorkerSettings:
    functions = [execute_background_job]
    cron_jobs = [
        cron(sweep_outbox_cron, minute=set(range(0, 60)), second=0),
        cron(monitor_sla_cron, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, second=15),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = settings.WORKER_MAX_JOBS
    job_timeout = max(60, settings.AI_REQUEST_TIMEOUT_SECONDS * 2 + 30)
    keep_result = 300
    redis_settings = (
        RedisSettings.from_dsn(settings.REDIS_URL)
        if (settings.REDIS_URL or "").strip()
        else RedisSettings(host="localhost", port=6379)
    )
