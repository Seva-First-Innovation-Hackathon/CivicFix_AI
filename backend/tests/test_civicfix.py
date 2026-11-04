import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import Base, get_db
from app.core.security import get_password_hash
from app.models.entities import User, Complaint, MunicipalDepartment, WorkOrder
from app.models.enums import UserRole, ComplaintStatus, PriorityLevel
from app.services.maps.spatial import haversine_distance_meters
from app.services.ai.duplicate_detector import compute_text_similarity

client = TestClient(app)

def test_health_endpoint():
    """Verify system health check."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

    # API v1 prefix health
    v1_resp = client.get("/api/v1/health")
    assert v1_resp.status_code == 200

def test_database_connectivity_health():
    """Verify database-specific connectivity endpoint without credentials leak."""
    response = client.get("/api/v1/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "dialect" in data
    # Ensure no credentials/connection strings are exposed in output
    assert "password" not in str(data).lower()
    assert "secret" not in str(data).lower()

def test_password_hashing_argon2id():
    """Verify Argon2id password hashing and validation."""
    from app.core.security import get_password_hash, verify_password
    plain_password = "SecretPasswordToHash2026!"
    hashed = get_password_hash(plain_password)
    
    assert hashed != plain_password
    assert "$argon2id$" in hashed  # Enforces Argon2id format
    assert verify_password(plain_password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

def test_citizen_registration_and_login():
    """Verify citizen registration and authentication flow."""
    import uuid
    unique_email = f"test.citizen.{uuid.uuid4().hex[:8]}@test.com"
    reg_payload = {
        "email": unique_email,
        "password": "ValidSecurePassword123!",
        "full_name": "Test Citizen User",
        "phone_number": "+91 99999 88888",
        "preferred_language": "en"
    }
    
    # Register
    reg_resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert reg_data["role"] == "CITIZEN"

    # Duplicate registration must fail
    dup_resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_resp.status_code == 400
    assert "already exists" in dup_resp.json()["detail"].lower()

    # Login with valid credentials
    login_resp = client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": "ValidSecurePassword123!"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    assert "access_token" in login_resp.json()

    # Verify current user endpoint GET /api/v1/auth/me
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == unique_email.lower()
    assert me_data["role"] == "CITIZEN"
    # Never return password hash in user responses
    assert "hashed_password" not in me_data

    # Login with invalid password
    bad_login = client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401

def test_anonymous_access_denial():
    """Verify unauthenticated requests to protected endpoints return 401 Unauthorized."""
    # /auth/me
    resp_me = client.get("/api/v1/auth/me")
    assert resp_me.status_code == 401

    # /complaints/my
    resp_comp = client.get("/api/v1/complaints/my")
    assert resp_comp.status_code == 401

    # /admin/dashboard
    resp_admin = client.get("/api/v1/admin/dashboard")
    assert resp_admin.status_code == 401

def test_role_escalation_denial():
    """Verify citizen cannot access municipal administration endpoints."""
    # Login as citizen
    login_resp = client.post("/api/v1/auth/login", json={
        "email": "citizen.arjun@example.com",
        "password": "CitizenPass2026!"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to access admin dashboard -> Must return 403 Forbidden
    resp = client.get("/api/v1/admin/dashboard", headers=headers)
    assert resp.status_code == 403
    assert "not permitted" in resp.json()["detail"].lower() or "required role" in resp.json()["detail"].lower()

def test_rate_limiting_login_exceeded():
    """Verify that exceeding RATE_LIMIT_LOGIN (5/minute) triggers HTTP 429 with Retry-After."""
    from app.core.limiter import limiter
    limiter._storage.reset()

    # 5 attempts within limit
    for _ in range(5):
        resp = client.post("/api/v1/auth/login", json={
            "email": "rate.limit.test@example.com",
            "password": "WrongPassword!"
        })
        # 401 Unauthorized for bad password, but NOT 429 yet
        assert resp.status_code == 401

    # 6th attempt must be rejected with 429 Too Many Requests
    resp_exceeded = client.post("/api/v1/auth/login", json={
        "email": "rate.limit.test@example.com",
        "password": "WrongPassword!"
    })
    assert resp_exceeded.status_code == 429
    assert resp_exceeded.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert "retry-after" in resp_exceeded.headers or "Retry-After" in resp_exceeded.headers

    # Reset limiter storage and verify legitimate requests immediately succeed again
    limiter._storage.reset()
    resp_reset = client.post("/api/v1/auth/login", json={
        "email": "rate.limit.test@example.com",
        "password": "WrongPassword!"
    })
    assert resp_reset.status_code == 401  # Back to normal 401, not 429

def test_rate_limiting_complaint_create():
    """Verify that complaint submission is bounded by rate limits."""
    from app.core.limiter import limiter
    limiter._storage.reset()

    login = client.post("/api/v1/auth/login", json={
        "email": "citizen.arjun@example.com",
        "password": "CitizenPass2026!"
    })
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Bounded verification: 10 attempts allowed
    comp_payload = {
        "title": "Rate limit pothole report",
        "description": "Road crater needs maintenance promptly.",
        "category": "ROADS",
        "latitude": 17.4410,
        "longitude": 78.4890
    }
    for _ in range(10):
        c_resp = client.post("/api/v1/complaints", json=comp_payload, headers=headers)
        assert c_resp.status_code == 201

    # 11th attempt within minute must return 429
    c_exceeded = client.post("/api/v1/complaints", json=comp_payload, headers=headers)
    assert c_exceeded.status_code == 429
    assert c_exceeded.json()["error_code"] == "RATE_LIMIT_EXCEEDED"




def test_public_admin_registration_is_impossible():
    """
    Ensure the public registration endpoint does not accept role elevation
    and exclusively assigns CITIZEN role.
    """
    payload = {
        "email": "hacker@evil.com",
        "password": "HackerPassword123!",
        "full_name": "Malicious Attacker",
        "role": "GOVERNMENT_ADMIN"  # Attempt mass assignment / privilege escalation
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    if resp.status_code == 201:
        # If it created, ensure role was strictly overridden to CITIZEN
        assert resp.json()["role"] == "CITIZEN"

def test_idor_protection_citizen_complaint_access():
    """
    CRITICAL SECURITY TEST: Citizen A must NEVER be able to view, upload to,
    or modify Citizen B's complaint.
    """
    # Login Citizen Arjun (Citizen A)
    login_a = client.post("/api/v1/auth/login", json={
        "email": "citizen.arjun@example.com",
        "password": "CitizenPass2026!"
    })
    assert login_a.status_code == 200
    token_a = login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Login Citizen Priya (Citizen B)
    login_b = client.post("/api/v1/auth/login", json={
        "email": "citizen.priya@example.com",
        "password": "CitizenPass2026!"
    })
    assert login_b.status_code == 200
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Citizen A submits a private complaint
    comp_resp = client.post("/api/v1/complaints", json={
        "title": "Private drainage issue behind house",
        "description": "Drainage pipeline is overflowing into private alleyway.",
        "category": "DRAINAGE",
        "latitude": 17.4390,
        "longitude": 78.4980
    }, headers=headers_a)
    assert comp_resp.status_code == 201
    complaint_a_id = comp_resp.json()["id"]

    # Citizen A can view their own complaint
    own_resp = client.get(f"/api/v1/complaints/{complaint_a_id}", headers=headers_a)
    assert own_resp.status_code == 200
    assert own_resp.json()["id"] == complaint_a_id

    # Citizen B attempts to view Citizen A's complaint (IDOR attack)
    idor_resp = client.get(f"/api/v1/complaints/{complaint_a_id}", headers=headers_b)
    assert idor_resp.status_code == 403
    assert "forbidden" in idor_resp.json()["detail"].lower()

    # Citizen B attempts to confirm resolution on Citizen A's complaint
    confirm_idor = client.post(
        f"/api/v1/complaints/{complaint_a_id}/confirm-resolution",
        json={"is_satisfied": True},
        headers=headers_b
    )
    assert confirm_idor.status_code == 403

def test_single_admin_invariant_and_staff_creation():
    """
    Test that:
    1. Government Admin can create staff accounts.
    2. Attempting to create a second Government Admin is rejected.
    3. Municipal staff cannot create other staff accounts.
    """
    # Login Government Admin
    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@civicfix.gov",
        "password": "AdminSecure2026!"
    })
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Get department ID
    depts = client.get("/api/v1/admin/departments", headers=admin_headers).json()
    assert len(depts) > 0
    dept_id = depts[0]["id"]

    # Attempt to create a SECOND Government Admin -> Must fail!
    second_admin_payload = {
        "email": "another.admin@civicfix.gov",
        "password": "SecondAdminPass!",
        "full_name": "Second Admin Imposter",
        "role": "GOVERNMENT_ADMIN",
        "department_id": dept_id
    }
    fail_admin = client.post("/api/v1/admin/users", json=second_admin_payload, headers=admin_headers)
    assert fail_admin.status_code == 400
    assert "Single-Admin" in fail_admin.json()["detail"] or "second Government Admin" in fail_admin.json()["detail"]

    # Staff user cannot access admin user creation
    staff_login = client.post("/api/v1/auth/login", json={
        "email": "officer.sharma@civicfix.gov",
        "password": "StaffSecure2026!"
    })
    staff_token = staff_login.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    staff_forbidden = client.post("/api/v1/admin/users", json={
        "email": "crew.new@civicfix.gov",
        "password": "CrewPass2026!",
        "full_name": "New Crew",
        "role": "FIELD_CREW",
        "department_id": dept_id
    }, headers=staff_headers)
    assert staff_forbidden.status_code == 403

def test_two_stage_verification_lifecycle():
    """
    Test complete resolution lifecycle:
    Staff submits resolution -> AWAITING_CITIZEN_CONFIRMATION -> Citizen confirms -> RESOLVED.
    """
    # 1. Citizen A logs in and submits complaint
    login_a = client.post("/api/v1/auth/login", json={
        "email": "citizen.arjun@example.com",
        "password": "CitizenPass2026!"
    })
    token_a = login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    c_resp = client.post("/api/v1/complaints", json={
        "title": "Broken pedestrian railing near park entrance",
        "description": "Metal railing has come loose and poses risk to children.",
        "category": "FOOTPATHS",
        "latitude": 17.4410,
        "longitude": 78.4890
    }, headers=headers_a)
    complaint_id = c_resp.json()["id"]

    # 2. Staff logs in and submits Stage 1 resolution
    login_staff = client.post("/api/v1/auth/login", json={
        "email": "officer.sharma@civicfix.gov",
        "password": "StaffSecure2026!"
    })
    token_staff = login_staff.json()["access_token"]
    headers_staff = {"Authorization": f"Bearer {token_staff}"}

    res_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/resolution",
        json={"resolution_notes": "Railing welded and bolted to concrete base with safety yellow paint applied."},
        headers=headers_staff
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "AWAITING_CITIZEN_CONFIRMATION"

    # 3. Citizen A verifies and approves resolution
    confirm_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/confirm-resolution",
        json={
            "is_satisfied": True,
            "feedback_rating": 5,
            "feedback_notes": "Thank you, repair was completed promptly!"
        },
        headers=headers_a
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "RESOLVED"

def test_haversine_spatial_and_text_similarity():
    """Verify spatial calculation and duplicate algorithm."""
    # Distance between two nearby coordinates in Hyderabad (~110 meters)
    lat1, lon1 = 17.4400, 78.4900
    lat2, lon2 = 17.4408, 78.4905
    dist = haversine_distance_meters(lat1, lon1, lat2, lon2)
    assert 50 < dist < 200

    # Text similarity
    text1 = "Pothole on main road near bus station"
    text2 = "Big pothole on main street near bus stop"
    sim = compute_text_similarity(text1, text2)
    assert sim > 0.3

