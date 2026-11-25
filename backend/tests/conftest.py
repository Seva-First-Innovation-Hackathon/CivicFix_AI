import os
from pathlib import Path
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("EMAIL_ENABLED", "False")
if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)

from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import get_password_hash
import app.db.session as session_module
from app.db.session import Base, get_db
from app.db.init_db import ensure_default_departments
from app.main import app
from app.models.entities import (
    User, CitizenProfile, MunicipalDepartment, DepartmentMembership, CrewProfile
)
from app.models.enums import UserRole
from app.services.storage.service import storage_service


@pytest.fixture(scope="session")
def test_password_material():
    """Dynamically generated per-session test credentials (no static passwords)."""
    return {
        "admin": f"Adm-{uuid.uuid4().hex[:12]}!",
        "staff": f"Stf-{uuid.uuid4().hex[:12]}!",
        "crew": f"Crw-{uuid.uuid4().hex[:12]}!",
        "citizen": f"Cit-{uuid.uuid4().hex[:12]}!",
    }


@pytest.fixture(scope="session")
def hashed_test_passwords(test_password_material):
    """Caches Argon2id hashes once per test session so isolated DB fixtures stay fast."""
    return {role: get_password_hash(pwd) for role, pwd in test_password_material.items()}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch):
    """
    Provides a completely isolated per-test SQLite database and upload directory.
    Ensures zero dependency on civicfix.db, civicfix_test.db, or seed.py, and guarantees
    all tests are order-independent.
    """
    db_file = tmp_path / "isolated_test.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(test_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    # Seed baseline municipal departments without invoking seed.py
    seed_sess = TestingSessionLocal()
    try:
        ensure_default_departments(seed_sess)
    finally:
        seed_sess.close()

    monkeypatch.setattr(session_module, "engine", test_engine)
    monkeypatch.setattr(session_module, "SessionLocal", TestingSessionLocal)

    # Isolate file uploads inside tmp_path so tracked workspace uploads are untouched
    upload_root = tmp_path / "uploads"
    (upload_root / "complaints").mkdir(parents=True, exist_ok=True)
    (upload_root / "resolutions").mkdir(parents=True, exist_ok=True)
    (upload_root / "evidence").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_root))
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "QUEUE_BACKEND", "inline")
    monkeypatch.setattr(storage_service, "_cloud_backend", None)
    monkeypatch.setattr(storage_service, "upload_dir", upload_root)
    monkeypatch.setattr(storage_service, "complaint_dir", upload_root / "complaints")
    monkeypatch.setattr(storage_service, "resolution_dir", upload_root / "resolutions")
    monkeypatch.setattr(storage_service, "evidence_dir", upload_root / "evidence")

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    try:
        limiter._storage.reset()
    except Exception:
        pass

    yield TestingSessionLocal

    try:
        limiter._storage.reset()
    except Exception:
        pass
    app.dependency_overrides.clear()
    test_engine.dispose()


@pytest.fixture
def db_session_factory(isolated_db):
    return isolated_db


@pytest.fixture
def db_session(isolated_db):
    sess = isolated_db()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def client(isolated_db):
    return TestClient(app)


@pytest.fixture
def test_actors(db_session, test_password_material, hashed_test_passwords):
    """
    Creates isolated per-test users across all 4 roles cleanly without seed.py.
    Returns credentials, user records, and pre-authenticated Bearer header helpers.
    """
    depts = {d.code: d for d in db_session.query(MunicipalDepartment).all()}

    admin = User(
        email="admin.test@civicfix.gov",
        full_name="Test Commissioner",
        hashed_password=hashed_test_passwords["admin"],
        role=UserRole.GOVERNMENT_ADMIN.value,
        is_active=True,
        is_verified=True,
    )
    staff_roads = User(
        email="officer.roads@civicfix.gov",
        full_name="Roads Officer",
        hashed_password=hashed_test_passwords["staff"],
        role=UserRole.MUNICIPAL_MEMBER.value,
        is_active=True,
        is_verified=True,
    )
    staff_lighting = User(
        email="officer.lighting@civicfix.gov",
        full_name="Lighting Officer",
        hashed_password=hashed_test_passwords["staff"],
        role=UserRole.MUNICIPAL_MEMBER.value,
        is_active=True,
        is_verified=True,
    )
    crew_a = User(
        email="crew.alpha@civicfix.gov",
        full_name="Crew Alpha",
        hashed_password=hashed_test_passwords["crew"],
        role=UserRole.FIELD_CREW.value,
        is_active=True,
        is_verified=True,
    )
    crew_b = User(
        email="crew.beta@civicfix.gov",
        full_name="Crew Beta",
        hashed_password=hashed_test_passwords["crew"],
        role=UserRole.FIELD_CREW.value,
        is_active=True,
        is_verified=True,
    )
    citizen_a = User(
        email="citizen.alpha@example.com",
        full_name="Citizen Alpha",
        hashed_password=hashed_test_passwords["citizen"],
        role=UserRole.CITIZEN.value,
        is_active=True,
        is_verified=True,
    )
    citizen_b = User(
        email="citizen.beta@example.com",
        full_name="Citizen Beta",
        hashed_password=hashed_test_passwords["citizen"],
        role=UserRole.CITIZEN.value,
        is_active=True,
        is_verified=True,
    )

    db_session.add_all([admin, staff_roads, staff_lighting, crew_a, crew_b, citizen_a, citizen_b])
    db_session.flush()

    db_session.add_all([
        DepartmentMembership(user_id=staff_roads.id, department_id=depts["ROADS"].id, designation="Roads Engineer"),
        DepartmentMembership(user_id=staff_lighting.id, department_id=depts["LIGHTING"].id, designation="Lighting Engineer"),
        CrewProfile(user_id=crew_a.id, department_id=depts["ROADS"].id, vehicle_number="TS-09-AA-0001"),
        CrewProfile(user_id=crew_b.id, department_id=depts["LIGHTING"].id, vehicle_number="TS-09-BB-0002"),
        CitizenProfile(user_id=citizen_a.id, preferred_language="en"),
        CitizenProfile(user_id=citizen_b.id, preferred_language="te"),
    ])
    db_session.commit()

    return {
        "departments": depts,
        "admin": {"user": admin, "email": admin.email, "password": test_password_material["admin"]},
        "staff_roads": {"user": staff_roads, "email": staff_roads.email, "password": test_password_material["staff"]},
        "staff_lighting": {"user": staff_lighting, "email": staff_lighting.email, "password": test_password_material["staff"]},
        "crew_a": {"user": crew_a, "email": crew_a.email, "password": test_password_material["crew"]},
        "crew_b": {"user": crew_b, "email": crew_b.email, "password": test_password_material["crew"]},
        "citizen_a": {"user": citizen_a, "email": citizen_a.email, "password": test_password_material["citizen"]},
        "citizen_b": {"user": citizen_b, "email": citizen_b.email, "password": test_password_material["citizen"]},
    }
