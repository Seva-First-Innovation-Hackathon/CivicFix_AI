import uuid
from app.services.maps.spatial import haversine_distance_meters
from app.services.ai.duplicate_detector import compute_text_similarity
from app.core.limiter import limiter


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()


def test_health_endpoint(client):
    """Verify system health check."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

    v1_resp = client.get("/api/v1/health")
    assert v1_resp.status_code == 200


def test_database_connectivity_health(client):
    """Verify database-specific connectivity endpoint without credentials leak."""
    response = client.get("/api/v1/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "dialect" in data
    assert "password" not in str(data).lower()
    assert "secret" not in str(data).lower()


def test_password_hashing_argon2id():
    """Verify Argon2id password hashing and validation."""
    from app.core.security import get_password_hash, verify_password
    plain_password = f"Sec-{uuid.uuid4().hex}!"
    hashed = get_password_hash(plain_password)

    assert hashed != plain_password
    assert "$argon2id$" in hashed
    assert verify_password(plain_password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_citizen_registration_and_login(client):
    """Verify citizen registration and authentication flow using isolated fresh credentials."""
    unique_email = f"test.citizen.{uuid.uuid4().hex[:8]}@test.com"
    secret = f"ValidSec-{uuid.uuid4().hex[:10]}!"
    reg_payload = {
        "email": unique_email,
        "password": secret,
        "full_name": "Test Citizen User",
        "phone_number": "+91 99999 88888",
        "preferred_language": "en"
    }

    reg_resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert "refresh_token" in reg_data
    assert reg_data["role"] == "CITIZEN"

    dup_resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_resp.status_code == 400
    assert "already exists" in dup_resp.json()["detail"].lower()

    login_data = _login(client, unique_email, secret)
    token = login_data["access_token"]

    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == unique_email.lower()
    assert me_data["role"] == "CITIZEN"
    assert "hashed_password" not in me_data

    bad_login = client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401


def test_anonymous_access_denial(client):
    """Verify unauthenticated requests to protected endpoints return 401 Unauthorized."""
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/complaints/my").status_code == 401
    assert client.get("/api/v1/admin/dashboard").status_code == 401


def test_role_escalation_denial(client, test_actors):
    """Verify citizen cannot access municipal administration endpoints."""
    c_a = test_actors["citizen_a"]
    token = _login(client, c_a["email"], c_a["password"])["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/admin/dashboard", headers=headers)
    assert resp.status_code == 403
    assert "not permitted" in resp.json()["detail"].lower() or "required role" in resp.json()["detail"].lower()


def test_rate_limiting_login_exceeded(client):
    """Verify that exceeding RATE_LIMIT_LOGIN (5/minute) triggers HTTP 429 with Retry-After."""
    limiter._storage.reset()

    for _ in range(5):
        resp = client.post("/api/v1/auth/login", json={
            "email": "rate.limit.test@example.com",
            "password": "WrongPassword!"
        })
        assert resp.status_code == 401

    resp_exceeded = client.post("/api/v1/auth/login", json={
        "email": "rate.limit.test@example.com",
        "password": "WrongPassword!"
    })
    assert resp_exceeded.status_code == 429
    assert resp_exceeded.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert "retry-after" in resp_exceeded.headers or "Retry-After" in resp_exceeded.headers

    limiter._storage.reset()
    resp_reset = client.post("/api/v1/auth/login", json={
        "email": "rate.limit.test@example.com",
        "password": "WrongPassword!"
    })
    assert resp_reset.status_code == 401


def test_rate_limiting_complaint_create(client, test_actors):
    """Verify that complaint submission is bounded by rate limits."""
    limiter._storage.reset()
    c_a = test_actors["citizen_a"]
    token = _login(client, c_a["email"], c_a["password"])["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

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

    c_exceeded = client.post("/api/v1/complaints", json=comp_payload, headers=headers)
    assert c_exceeded.status_code == 429
    assert c_exceeded.json()["error_code"] == "RATE_LIMIT_EXCEEDED"


def test_public_admin_registration_is_impossible(client):
    """Ensure the public registration endpoint strictly assigns CITIZEN role."""
    payload = {
        "email": f"hacker.{uuid.uuid4().hex[:6]}@evil.com",
        "password": f"Hck-{uuid.uuid4().hex[:10]}!",
        "full_name": "Malicious Attacker",
        "role": "GOVERNMENT_ADMIN"
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    assert resp.json()["role"] == "CITIZEN"


def test_idor_protection_citizen_complaint_access(client, test_actors):
    """Citizen A must NEVER be able to view, upload to, or modify Citizen B's complaint."""
    c_a = test_actors["citizen_a"]
    c_b = test_actors["citizen_b"]
    headers_a = {"Authorization": f"Bearer {_login(client, c_a['email'], c_a['password'])['access_token']}"}
    headers_b = {"Authorization": f"Bearer {_login(client, c_b['email'], c_b['password'])['access_token']}"}

    comp_resp = client.post("/api/v1/complaints", json={
        "title": "Private drainage issue behind house",
        "description": "Drainage pipeline is overflowing into private alleyway.",
        "category": "DRAINAGE",
        "latitude": 17.4390,
        "longitude": 78.4980
    }, headers=headers_a)
    assert comp_resp.status_code == 201
    complaint_a_id = comp_resp.json()["id"]

    own_resp = client.get(f"/api/v1/complaints/{complaint_a_id}", headers=headers_a)
    assert own_resp.status_code == 200
    assert own_resp.json()["id"] == complaint_a_id

    idor_resp = client.get(f"/api/v1/complaints/{complaint_a_id}", headers=headers_b)
    assert idor_resp.status_code == 403
    assert "forbidden" in idor_resp.json()["detail"].lower()

    confirm_idor = client.post(
        f"/api/v1/complaints/{complaint_a_id}/confirm-resolution",
        json={"is_satisfied": True},
        headers=headers_b
    )
    assert confirm_idor.status_code == 403


def test_single_admin_invariant_and_staff_creation(client, test_actors):
    """Test Single-Admin invariant and Government Admin staff creation exclusivity."""
    adm = test_actors["admin"]
    staff = test_actors["staff_roads"]
    admin_headers = {"Authorization": f"Bearer {_login(client, adm['email'], adm['password'])['access_token']}"}
    staff_headers = {"Authorization": f"Bearer {_login(client, staff['email'], staff['password'])['access_token']}"}

    depts = client.get("/api/v1/admin/departments", headers=admin_headers).json()
    assert len(depts) > 0
    dept_id = depts[0]["id"]

    fail_admin = client.post("/api/v1/admin/users", json={
        "email": "another.admin@civicfix.gov",
        "password": f"Adm2-{uuid.uuid4().hex[:10]}!",
        "full_name": "Second Admin Imposter",
        "role": "GOVERNMENT_ADMIN",
        "department_id": dept_id
    }, headers=admin_headers)
    assert fail_admin.status_code == 400
    assert "Single-Admin" in fail_admin.json()["detail"] or "second Government Admin" in fail_admin.json()["detail"]

    staff_forbidden = client.post("/api/v1/admin/users", json={
        "email": "crew.new@civicfix.gov",
        "password": f"Crw-{uuid.uuid4().hex[:10]}!",
        "full_name": "New Crew",
        "role": "FIELD_CREW",
        "department_id": dept_id
    }, headers=staff_headers)
    assert staff_forbidden.status_code == 403


def test_two_stage_verification_lifecycle(client, test_actors):
    """
    Test complete resolution lifecycle:
    Staff submits resolution -> AWAITING_CITIZEN_CONFIRMATION -> Citizen confirms -> RESOLVED.
    """
    c_a = test_actors["citizen_a"]
    staff = test_actors["staff_roads"]
    headers_a = {"Authorization": f"Bearer {_login(client, c_a['email'], c_a['password'])['access_token']}"}
    headers_staff = {"Authorization": f"Bearer {_login(client, staff['email'], staff['password'])['access_token']}"}

    c_resp = client.post("/api/v1/complaints", json={
        "title": "Broken pedestrian railing near park entrance",
        "description": "Metal railing has come loose and poses risk to children.",
        "category": "FOOTPATHS",
        "latitude": 17.4410,
        "longitude": 78.4890
    }, headers=headers_a)
    assert c_resp.status_code == 201
    complaint_id = c_resp.json()["id"]

    res_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/resolution",
        json={"resolution_notes": "Railing welded and bolted to concrete base with safety yellow paint applied."},
        headers=headers_staff
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "AWAITING_CITIZEN_CONFIRMATION"

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
    lat1, lon1 = 17.4400, 78.4900
    lat2, lon2 = 17.4408, 78.4905
    dist = haversine_distance_meters(lat1, lon1, lat2, lon2)
    assert 50 < dist < 200

    text1 = "Pothole on main road near bus station"
    text2 = "Big pothole on main street near bus stop"
    sim = compute_text_similarity(text1, text2)
    assert sim > 0.3
