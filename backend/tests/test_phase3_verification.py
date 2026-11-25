import uuid
from app.core.limiter import limiter


def get_auth_headers(client, actor: dict) -> dict:
    limiter._storage.reset()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": actor["email"], "password": actor["password"]},
    )
    assert login_resp.status_code == 200, f"Login failed for {actor['email']}: {login_resp.text}"
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_phase3_full_lifecycle_and_state_machine(client, test_actors):
    """Phase 3 End-to-End Complaint Lifecycle using isolated test actors."""
    limiter._storage.reset()
    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])
    staff_headers = get_auth_headers(client, test_actors["staff_roads"])
    crew_headers = get_auth_headers(client, test_actors["crew_a"])

    unique_tag = uuid.uuid4().hex[:6]
    target_lat = 17.4420
    target_lon = 78.4910
    create_payload = {
        "title": f"Dangerous open pothole on 8th Cross #{unique_tag}",
        "description": "Deep road pothole creating severe vehicle hazard on municipal road.",
        "category": "ROADS",
        "latitude": target_lat,
        "longitude": target_lon,
        "address": "8th Cross, Banjara Hills, Ward 10",
        "landmark": "Near Community Hall"
    }
    submit_resp = client.post("/api/v1/complaints", json=create_payload, headers=citizen_headers)
    assert submit_resp.status_code == 201
    comp = submit_resp.json()
    complaint_id = comp["id"]
    assert comp["reference_number"].startswith("CF-")
    assert comp["latitude"] == target_lat
    assert comp["longitude"] == target_lon

    verify_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/verify",
        json={"priority": "P2", "verification_notes": "Immediate road hazard verified on site."},
        headers=staff_headers
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "VERIFIED"
    assert verify_resp.json()["priority"] == "P2"

    roads_dept = test_actors["departments"]["ROADS"]
    crew_a_id = test_actors["crew_a"]["user"].id

    wo_payload = {
        "complaint_id": complaint_id,
        "department_id": roads_dept.id,
        "crew_id": crew_a_id,
        "title": "Install reinforced concrete patch",
        "instructions": "Excavate damaged asphalt and seal cleanly."
    }
    wo_resp = client.post("/api/v1/admin/work-orders", json=wo_payload, headers=staff_headers)
    assert wo_resp.status_code == 201
    work_order_id = wo_resp.json()["id"]

    comp_progress = client.get(f"/api/v1/complaints/{complaint_id}", headers=citizen_headers).json()
    assert comp_progress["status"] == "IN_PROGRESS"

    accept_resp = client.post(f"/api/v1/admin/work-orders/{work_order_id}/accept", headers=crew_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "ACCEPTED"

    update_resp = client.patch(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        json={"status": "IN_PROGRESS", "note": "Arrived with crew and hot mix."},
        headers=crew_headers
    )
    assert update_resp.status_code == 200

    evidence_resp = client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/submit-evidence",
        json={
            "completion_notes": "Road surface patched and flushed with surrounding grade.",
            "materials_used": "Asphalt concrete"
        },
        headers=crew_headers
    )
    assert evidence_resp.status_code == 200

    staff_review = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/review-evidence",
        json={"is_approved": True, "notes": "Surface verified flush and safe for traffic."},
        headers=staff_headers
    )
    assert staff_review.status_code == 200
    assert staff_review.json()["status"] == "AWAITING_CITIZEN_CONFIRMATION"

    confirm_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/confirm-resolution",
        json={"is_satisfied": True, "feedback_rating": 5, "feedback_notes": "Prompt response and perfect repair."},
        headers=citizen_headers
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "RESOLVED"


def test_phase3_field_crew_access_isolation(client, test_actors):
    """Field Crew B must NOT be able to view, accept, modify, or submit evidence for Crew A's work order."""
    limiter._storage.reset()
    staff_headers = get_auth_headers(client, test_actors["staff_roads"])
    crew_b_headers = get_auth_headers(client, test_actors["crew_b"])
    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])

    comp_resp = client.post("/api/v1/complaints", json={
        "title": f"Pothole defect on arterial road #{uuid.uuid4().hex[:6]}",
        "description": "Deep asphalt crater along busy school corridor.",
        "category": "ROADS",
        "latitude": 17.4450,
        "longitude": 78.4930
    }, headers=citizen_headers)
    assert comp_resp.status_code == 201
    comp_id = comp_resp.json()["id"]

    roads_dept = test_actors["departments"]["ROADS"]
    crew_a_id = test_actors["crew_a"]["user"].id

    wo_resp = client.post("/api/v1/admin/work-orders", json={
        "complaint_id": comp_id,
        "department_id": roads_dept.id,
        "crew_id": crew_a_id,
        "title": "Cold-patch crater repair",
        "instructions": "Clean debris and fill with compacted aggregate."
    }, headers=staff_headers)
    assert wo_resp.status_code == 201
    wo_id = wo_resp.json()["id"]

    b_accept = client.post(f"/api/v1/admin/work-orders/{wo_id}/accept", headers=crew_b_headers)
    assert b_accept.status_code == 403
    assert "not assigned to you" in b_accept.json()["detail"].lower()

    b_patch = client.patch(
        f"/api/v1/admin/work-orders/{wo_id}/status",
        json={"status": "IN_PROGRESS", "note": "Illegal update attempt by Crew B."},
        headers=crew_b_headers
    )
    assert b_patch.status_code == 403
    assert "only update your assigned work orders" in b_patch.json()["detail"].lower()

    b_evidence = client.post(
        f"/api/v1/admin/work-orders/{wo_id}/submit-evidence",
        json={"completion_notes": "Fake completion note by wrong crew."},
        headers=crew_b_headers
    )
    assert b_evidence.status_code == 403
    assert "not assigned to you" in b_evidence.json()["detail"].lower()

    b_list = client.get("/api/v1/admin/work-orders", headers=crew_b_headers)
    assert b_list.status_code == 200
    assert wo_id not in [w["id"] for w in b_list.json()]


def test_phase3_citizen_idor_isolation(client, test_actors):
    """Citizen B cannot access, cancel, clarify, or confirm Citizen A's complaints."""
    limiter._storage.reset()
    arjun_headers = get_auth_headers(client, test_actors["citizen_a"])
    priya_headers = get_auth_headers(client, test_actors["citizen_b"])

    arjun_comp = client.post("/api/v1/complaints", json={
        "title": f"Citizen A private water pipe issue #{uuid.uuid4().hex[:6]}",
        "description": "Leakage on residential connection outside gate.",
        "category": "WATER_SUPPLY",
        "latitude": 17.4410,
        "longitude": 78.4900
    }, headers=arjun_headers).json()
    arjun_comp_id = arjun_comp["id"]

    assert client.get(f"/api/v1/complaints/{arjun_comp_id}", headers=priya_headers).status_code == 403
    assert client.post(
        f"/api/v1/complaints/{arjun_comp_id}/cancel",
        json={"reason": "Attempting malicious cancellation."},
        headers=priya_headers
    ).status_code == 403
    assert client.post(
        f"/api/v1/complaints/{arjun_comp_id}/clarify",
        json={"information": "Malicious clarification attempt."},
        headers=priya_headers
    ).status_code == 403
    assert client.post(
        f"/api/v1/complaints/{arjun_comp_id}/confirm-resolution",
        json={"is_satisfied": True},
        headers=priya_headers
    ).status_code == 403


def test_phase3_coordinate_bounds_and_storage(client, test_actors):
    """Tests geographic coordinate validation and exact persistence."""
    limiter._storage.reset()
    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])

    for lat, lon in [(95.0, 78.4910), (-95.0, 78.4910), (17.4420, 185.0), (17.4420, -185.0)]:
        bad = client.post("/api/v1/complaints", json={
            "title": "Invalid coordinate complaint",
            "description": "Attempting out-of-bounds coordinates.",
            "category": "ROADS",
            "latitude": lat,
            "longitude": lon,
        }, headers=citizen_headers)
        assert bad.status_code == 422

    valid_lat, valid_lon = 17.4567, 78.4321
    valid_comp = client.post("/api/v1/complaints", json={
        "title": f"Precise coordinate verification #{uuid.uuid4().hex[:6]}",
        "description": "Pothole at exact surveyed GPS location.",
        "category": "ROADS",
        "latitude": valid_lat,
        "longitude": valid_lon
    }, headers=citizen_headers)
    assert valid_comp.status_code == 201
    created = valid_comp.json()
    assert abs(created["latitude"] - valid_lat) < 1e-4
    assert abs(created["longitude"] - valid_lon) < 1e-4


def test_phase3_evidence_access_authorization(client):
    """Evidence endpoint rejects anonymous requests and invalid bearer tokens."""
    assert client.get("/api/v1/evidence/00000000-0000-0000-0000-000000000000").status_code == 401
    assert client.get(
        "/api/v1/evidence/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": "Bearer totally-invalid-jwt-token"}
    ).status_code == 401


def test_phase3_dashboard_real_metrics(client, test_actors):
    """Dashboard metrics dynamic computation & role enforcement."""
    limiter._storage.reset()
    staff_headers = get_auth_headers(client, test_actors["staff_roads"])
    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])

    metrics_resp = client.get("/api/v1/admin/dashboard", headers=staff_headers)
    assert metrics_resp.status_code == 200
    data = metrics_resp.json()
    assert "metrics" in data
    assert "by_category" in data
    assert "by_priority" in data
    assert "by_department" in data

    assert client.get("/api/v1/admin/dashboard", headers=citizen_headers).status_code == 403
    assert client.get("/api/v1/admin/dashboard").status_code == 401
