"""
Dedicated CivicFix AI background worker entrypoint.

Runs ARQ worker consuming Redis-backed AI triage, SMTP email, and periodic SLA monitoring jobs:
    python worker.py

Diagnostic single-cycle recovery/SLA check (no daemon loop):
    python worker.py --run-maintenance-once
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
import app.db.session as db_session
from app.services.ai.service import recover_interrupted_ai_jobs
from app.services.jobs.queue import recover_stale_running_jobs, sweep_pending_outbox_jobs
from app.services.sla.monitor import monitor_sla_deadlines

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("civicfix.worker")


async def _run_maintenance_once() -> dict:
    stale = recover_stale_running_jobs()
    ai_rec = recover_interrupted_ai_jobs()
    db = db_session.SessionLocal()
    try:
        sla = monitor_sla_deadlines(db=db)
    finally:
        db.close()
    dispatched = await sweep_pending_outbox_jobs()
    return {
        "stale_jobs_recovered": stale,
        "interrupted_ai_recovered": ai_rec,
        "sla_summary": sla,
        "outbox_processed": dispatched,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CivicFix AI ARQ background worker")
    parser.add_argument(
        "--run-maintenance-once",
        action="store_true",
        help="Run stale job recovery, SLA scan, and pending outbox sweep once and exit.",
    )
    args = parser.parse_args()

    if args.run_maintenance_once:
        result = asyncio.run(_run_maintenance_once())
        print(json.dumps(result, indent=2))
        return 0

    if not (settings.REDIS_URL or "").strip():
        logger.error("Cannot start ARQ worker daemon: REDIS_URL is not configured.")
        return 1

    from arq.worker import run_worker
    from app.workers.arq_worker import WorkerSettings

    run_worker(WorkerSettings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
