from datetime import datetime, timedelta, timezone
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql

from app.db.spatial_types import (
    format_geog_point_wkt,
    is_valid_coordinates,
    parse_wkt_point,
)
from app.models.entities import Complaint, PotentialDuplicate
from app.models.enums import ComplaintCategory, ComplaintStatus
from app.services.ai.duplicate_detector import (
    build_postgis_duplicate_query,
    find_potential_duplicates_from_db,
)


def test_coordinate_validation_sync_and_boundary_coords(db_session, test_actors):
    citizen = test_actors["citizen_a"]["user"]

    # Boundary WGS84 coordinates stay valid and sync WKT location on insert & update
    boundary = Complaint(
        reference_number="CF-2026-BOUND001",
        citizen_id=citizen.id,
        title="Extreme latitude pole check",
        description="Boundary check at South Pole and antimeridian.",
        category=ComplaintCategory.ROADS.value,
        latitude=-90.0,
        longitude=180.0,
        status=ComplaintStatus.UNDER_REVIEW.value,
        priority="P3",
    )
    db_session.add(boundary)
    db_session.commit()
    db_session.refresh(boundary)

    assert parse_wkt_point(boundary.location) == pytest.approx((-90.0, 180.0))

    boundary.latitude = 17.4412
    boundary.longitude = 78.4981
    db_session.commit()
    db_session.refresh(boundary)
    assert parse_wkt_point(boundary.location) == pytest.approx((17.4412, 78.4981))

    # Out-of-bounds / NaN / Null guards
    assert is_valid_coordinates(91.0, 78.0) is False
    assert is_valid_coordinates(17.0, -181.0) is False
    assert is_valid_coordinates(float("nan"), 78.0) is False
    assert is_valid_coordinates(None, 78.0) is False
    assert format_geog_point_wkt(95.0, 12.0) is None


def test_postgis_sql_compilation_uses_st_dwithin_geography_and_gist_index(db_session, test_actors, tmp_path):
    """
    Verifies PostgreSQL dialect compiles native GEOGRAPHY(POINT, 4326), GIST index DDL,
    and ST_DWithin / ST_Distance duplicate query SQL (offline SQL check).
    """
    citizen = test_actors["citizen_a"]["user"]
    probe = Complaint(
        id="cmp-probe-1",
        reference_number="CF-2026-PGSQL01",
        citizen_id=citizen.id,
        title="Broken drainage cover",
        description="Open storm drain grating missing.",
        category=ComplaintCategory.DRAINAGE.value,
        latitude=17.4399,
        longitude=78.4983,
        status=ComplaintStatus.UNDER_REVIEW.value,
    )
    query = build_postgis_duplicate_query(
        db=db_session,
        new_complaint=probe,
        max_distance_meters=150.0,
        cutoff_time=datetime.now(timezone.utc) - timedelta(days=14),
        candidate_limit=25,
    )
    compiled_sql = str(query.statement.compile(dialect=postgresql.dialect()))
    assert "ST_DWithin" in compiled_sql
    assert "ST_Distance" in compiled_sql
    assert "ST_GeogFromText" in compiled_sql
    assert "LIMIT" in compiled_sql

    # Offline PostgreSQL SQL for Phase 2B migration creates extension, column, backfill, and GiST index
    backend_dir = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["ENVIRONMENT"] = "production"
    env["DATABASE_URL"] = "postgresql://u:p@localhost:5432/civicfix"
    env["SECRET_KEY"] = "test_secret_key_for_postgis_sql_compilation_32ch"
    sql_res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "d1a4e8c2f109:d2b5f9d3a218", "--sql"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    assert sql_res.returncode == 0, sql_res.stderr
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in sql_res.stdout
    assert "ADD COLUMN location geography(POINT,4326)" in sql_res.stdout
    assert "ST_MakePoint(longitude, latitude)" in sql_res.stdout
    assert "USING GIST (location)" in sql_res.stdout


def test_spatial_migration_backfill_and_sqlite_bounded_duplicate_detection(db_session, test_actors, tmp_path):
    """Tests Alembic backfill on pre-existing rows plus spatial radius inclusion/exclusion & limit."""
    backend_dir = Path(__file__).resolve().parent.parent
    db_file = tmp_path / "backfill_spatial.db"

    env = os.environ.copy()
    env["ENVIRONMENT"] = "testing"
    env["DATABASE_URL"] = f"sqlite:///{db_file}"
    env["SECRET_KEY"] = "test_secret_key_for_sqlite_backfill_check_min32"

    # Migrate up to 2A (before location column existed), insert row, then migrate 2B
    r1 = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "d1a4e8c2f109"], cwd=str(backend_dir), env=env, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr

    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        INSERT INTO users (id, email, full_name, hashed_password, role, is_active, is_verified, created_at, updated_at)
        VALUES ('u1', 'mig@example.com', 'Mig User', 'hash', 'CITIZEN', 1, 1, '2026-10-01 00:00:00', '2026-10-01 00:00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO complaints (id, reference_number, citizen_id, title, description, category, latitude, longitude, status, priority, is_disputed, ai_processing_status, ai_processing_attempts, created_at, updated_at)
        VALUES ('c1', 'CF-2026-OLDROW1', 'u1', 'Old pothole', 'Legacy road crater before PostGIS', 'ROADS', 17.4400, 78.4980, 'UNDER_REVIEW', 'P3', 0, 'COMPLETED', 1, '2026-10-01 00:00:00', '2026-10-01 00:00:00')
        """
    )
    conn.commit()
    conn.close()

    r2 = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "d2b5f9d3a218"], cwd=str(backend_dir), env=env, capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr

    conn2 = sqlite3.connect(db_file)
    loc_val = conn2.execute("SELECT location FROM complaints WHERE id='c1'").fetchone()[0]
    conn2.close()
    assert parse_wkt_point(loc_val) == pytest.approx((17.4400, 78.4980))

    # Duplicate matching & distant exclusion in DB
    c_a = test_actors["citizen_a"]["user"]
    nearby_same = Complaint(
        reference_number="CF-2026-NEAR01",
        citizen_id=c_a.id,
        title="Deep pothole blocking left lane near bus stand",
        description="Asphalt crater damaging vehicles outside metro station bus stand.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.4402,
        longitude=78.4982,
        status=ComplaintStatus.UNDER_REVIEW.value,
    )
    distant_same = Complaint(
        reference_number="CF-2026-FAR001",
        citizen_id=c_a.id,
        title="Deep pothole blocking left lane near bus stand",
        description="Asphalt crater damaging vehicles 5km away.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.4850,
        longitude=78.5450,
        status=ComplaintStatus.UNDER_REVIEW.value,
    )
    resolved_nearby = Complaint(
        reference_number="CF-2026-RES001",
        citizen_id=c_a.id,
        title="Deep pothole blocking left lane near bus stand",
        description="Already resolved pothole nearby.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.4401,
        longitude=78.4981,
        status=ComplaintStatus.RESOLVED.value,
    )
    incoming = Complaint(
        reference_number="CF-2026-NEW001",
        citizen_id=c_a.id,
        title="Deep pothole blocking left lane outside metro bus stand",
        description="Large asphalt crater outside metro bus stand.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.4403,
        longitude=78.4983,
        status=ComplaintStatus.AI_ANALYSIS_PENDING.value,
    )
    db_session.add_all([nearby_same, distant_same, resolved_nearby, incoming])
    db_session.commit()

    matches = find_potential_duplicates_from_db(db_session, incoming, max_distance_meters=120.0, candidate_limit=10)
    matched_ids = {m.complaint_id for m in matches}
    assert nearby_same.id in matched_ids
    assert distant_same.id not in matched_ids
    assert resolved_nearby.id not in matched_ids

    # Candidate limit obeyed
    limited = find_potential_duplicates_from_db(db_session, incoming, max_distance_meters=120.0, candidate_limit=1)
    assert len(limited) <= 1

    # Invalid coordinates on probe returns empty list safely
    invalid_probe = Complaint(
        id="invalid-probe",
        reference_number="CF-2026-BADGEO",
        citizen_id=c_a.id,
        title="Invalid point",
        description="Corrupt latitude value.",
        category=ComplaintCategory.ROADS.value,
        latitude=999.0,
        longitude=78.4,
    )
    assert find_potential_duplicates_from_db(db_session, invalid_probe) == []


@pytest.mark.skipif(
    not os.getenv("POSTGIS_TEST_DATABASE_URL"),
    reason="BLOCKED: Live PostgreSQL/PostGIS server not configured via POSTGIS_TEST_DATABASE_URL",
)
def test_live_postgis_integration():
    """
    Live PostGIS integration test executed when POSTGIS_TEST_DATABASE_URL is configured
    (e.g. via infrastructure/docker-compose.test.yml).
    """
    url = os.environ["POSTGIS_TEST_DATABASE_URL"]
    eng = create_engine(url)
    try:
        with eng.connect() as conn:
            ver = conn.execute(text("SELECT PostGIS_Version();")).scalar()
            assert ver
            insp = inspect(eng)
            if "complaints" in insp.get_table_names():
                cols = {c["name"] for c in insp.get_columns("complaints")}
                assert "location" in cols
                idx = conn.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename='complaints' AND indexname='ix_complaints_location_gist';")
                ).scalar()
                assert idx == "ix_complaints_location_gist"
    finally:
        eng.dispose()
