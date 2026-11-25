"""
CivicFix AI — Safe Database Migration Runner
Applies Alembic migrations idempotently without data loss or dropping tables.
Handles existing populated databases and fresh databases safely.
"""
import sys
import logging
from pathlib import Path
from sqlalchemy import inspect, text

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings
from app.db.session import engine
from alembic.config import Config
from alembic import command

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("civicfix.migrations")


def _detect_unstamped_baseline_revision(inspector) -> str:
    """
    Determines the highest Alembic revision already reflected on an unstamped legacy database
    so stamping never skips unapplied migrations.
    """
    tables = set(inspector.get_table_names())
    complaint_cols = {c["name"] for c in inspector.get_columns("complaints")} if "complaints" in tables else set()
    att_cols = (
        {c["name"] for c in inspector.get_columns("complaint_attachments")}
        if "complaint_attachments" in tables
        else set()
    )

    if "resolution_comparisons" in tables and "ai_feedback_records" in tables:
        return "d4d7b1f5c436"
    if "sla_breach_events" in tables and "background_jobs" in tables:
        return "d3c6a0e4b327"
    if "location" in complaint_cols:
        return "d2b5f9d3a218"
    if "storage_provider" in att_cols:
        return "d1a4e8c2f109"
    if "refresh_tokens" in tables and "ai_processing_status" in complaint_cols:
        return "b4e2d9c1f8a3"
    if "complaint_comments" in tables:
        return "adca60ea77e0"
    return "6b691e58bfaa"


def run_migrations():
    logger.info("Initializing Alembic migration check for database dialect: %s", engine.dialect.name)

    # Enable PostGIS if PostgreSQL
    if engine.dialect.name == "postgresql":
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
                conn.commit()
                logger.info("PostGIS extension checked/enabled successfully.")
        except Exception as exc:
            logger.warning("Could not enable PostGIS extension (may lack superuser privileges): %s", exc)

    ini_path = BASE_DIR / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    has_alembic_table = "alembic_version" in tables
    has_users = "users" in tables
    has_version_row = False

    if has_alembic_table:
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                if res and res[0]:
                    has_version_row = True
        except Exception:
            has_version_row = False

    if not has_version_row and has_users:
        baseline_rev = _detect_unstamped_baseline_revision(inspector)
        logger.info(
            "Existing unstamped database detected. Stamping baseline revision '%s' before upgrading to head...",
            baseline_rev,
        )
        command.stamp(alembic_cfg, baseline_rev)

    logger.info("Applying pending Alembic migrations to head...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations completed successfully.")


if __name__ == "__main__":
    try:
        run_migrations()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
