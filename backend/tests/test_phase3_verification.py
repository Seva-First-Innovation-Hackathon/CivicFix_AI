import pytest
import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.core.limiter import limiter
from app.models.enums import ComplaintStatus, WorkOrderStatus, PriorityLevel, UserRole

client = TestClient(app)

def get_auth_headers(email: str, password: str) -> dict:
    limiter._storage.reset()
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200, f"Login failed for {email}: {login_resp.text}"
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_phase3_full_lifecycle_and_state_machine():
    """
    Phase 3 End-to-End Complaint Lifecycle:
    Citizen Submission -> AI State -> Staff Verification & Department Routing ->
    Work Order Dispatch -> Field Crew Progress & Evidence Submission ->
    Staff Review & Approval -> Citizen Confirmation -> Resolved.
    """
    limiter._storage.reset()
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")
    staff_headers = get_auth_headers("officer.sharma@civicfix.gov", "StaffSecure2026!")
    crew_headers = get_auth_headers("crew.patel@civicfix.gov", "CrewSecure2026!")
    admin_headers = get_auth_headers("admin@civicfix.gov", "AdminSecure2026!")

    # 1. Citizen submits complaint with precise coordinates
    unique_tag = uuid.uuid4().hex[:6]
    target_lat = 17.4420
    target_lon = 78.4910
    create_payload = {
        "title": f"Dangerous open manhole on 8th Cross #{unique_tag}",
        "description": "Missing manhole cover on pedestrian sidewalk creating severe fall risk.",
        "category": "DRAINAGE",
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

    # 2. Staff verifies complaint and sets priority P2
    verify_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/verify",
        json={"priority": "P2", "verification_notes": "Immediate pedestrian hazard verified on site."},
        headers=staff_headers
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "VERIFIED"
    assert verify_resp.json()["priority"] == "P2"

    # 3. Staff creates work order and dispatches to crew
    depts = client.get("/api/v1/admin/departments", headers=staff_headers).json()
    drainage_dept = next((d for d in depts if d["code"] == "DRAINAGE"), depts[0])
    crews = client.get("/api/v1/admin/users?role=FIELD_CREW", headers=admin_headers).json()
    assert len(crews) > 0
    patel = next((c for c in crews if c["email"] == "crew.patel@civicfix.gov"), crews[0])
    crew_user_id = patel["id"]

    wo_payload = {
        "complaint_id": complaint_id,
        "department_id": drainage_dept["id"],
        "crew_id": crew_user_id,
        "title": "Install reinforced concrete manhole cover",
        "instructions": "Place heavy duty precast cover and seal frame with epoxy mortar."
    }
    wo_resp = client.post("/api/v1/admin/work-orders", json=wo_payload, headers=staff_headers)
    assert wo_resp.status_code == 201
    work_order_id = wo_resp.json()["id"]

    # Complaint transitioned to IN_PROGRESS
    comp_progress = client.get(f"/api/v1/complaints/{complaint_id}", headers=citizen_headers).json()
    assert comp_progress["status"] == "IN_PROGRESS"

    # 4. Crew accepts work order
    accept_resp = client.post(f"/api/v1/admin/work-orders/{work_order_id}/accept", headers=crew_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "ACCEPTED"

    # 5. Crew updates status to IN_PROGRESS with site note
    update_resp = client.patch(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        json={"status": "IN_PROGRESS", "note": "Arrived with crane truck and new cover."},
        headers=crew_headers
    )
    assert update_resp.status_code == 200

    # 6. Crew completes work and submits completion evidence
    evidence_resp = client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/submit-evidence",
        json={
            "completion_notes": "Heavy duty precast concrete manhole cover seated securely and flushed with sidewalk.",
            "materials_used": "1x 600mm precast cover, epoxy polymer mortar"
        },
        headers=crew_headers
    )
    assert evidence_resp.status_code == 200

    # 7. Staff reviews crew evidence and approves
    staff_review = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/review-evidence",
        json={"is_approved": True, "notes": "Cover verified flush and safe for pedestrian traffic."},
        headers=staff_headers
    )
    assert staff_review.status_code == 200
    assert staff_review.json()["status"] == "AWAITING_CITIZEN_CONFIRMATION"

    # 8. Citizen confirms resolution
    confirm_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/confirm-resolution",
        json={"is_satisfied": True, "feedback_rating": 5, "feedback_notes": "Prompt response and perfect repair. Sidewalk is safe."},
        headers=citizen_headers
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "RESOLVED"

def test_phase3_field_crew_access_isolation():
    """
    CRITICAL ACCESS RESTRICTION:
    Field Crew B must NOT be able to view, accept, modify, or submit evidence
    for a work order assigned to Field Crew A.
    """
    limiter._storage.reset()
    admin_headers = get_auth_headers("admin@civicfix.gov", "AdminSecure2026!")
    staff_headers = get_auth_headers("officer.sharma@civicfix.gov", "StaffSecure2026!")
    crew_a_headers = get_auth_headers("crew.patel@civicfix.gov", "CrewSecure2026!")

    # 1. Get or create Crew B
    crew_b_email = "crew.shao@civicfix.gov"
    crew_b_pwd = "CrewBSecure2026!"
    
    # Check if Crew B exists
    crew_b_login = client.post("/api/v1/auth/login", json={"email": crew_b_email, "password": crew_b_pwd})
    if crew_b_login.status_code != 200:
        depts = client.get("/api/v1/admin/departments", headers=admin_headers).json()
        dept_id = depts[0]["id"]
        create_crew_b = client.post("/api/v1/admin/users", json={
            "email": crew_b_email,
            "password": crew_b_pwd,
            "full_name": "Shao Lin (Secondary Road Crew)",
            "phone_number": "+91 98110 99887",
            "role": "FIELD_CREW",
            "department_id": dept_id,
            "vehicle_number": "TS-09-XY-9900",
            "contact_number": "+91 98110 99887"
        }, headers=admin_headers)
        assert create_crew_b.status_code == 201

    crew_b_headers = get_auth_headers(crew_b_email, crew_b_pwd)

    # 2. Get Crew A user id
    crews = client.get("/api/v1/admin/users?role=FIELD_CREW", headers=admin_headers).json()
    crew_a = next((c for c in crews if c["email"] == "crew.patel@civicfix.gov"), crews[0])
    crew_a_id = crew_a["id"]

    # 3. Create a complaint and assign Work Order to Crew A
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")
    comp_resp = client.post("/api/v1/complaints", json={
        "title": f"Streetlight outage near school #{uuid.uuid4().hex[:6]}",
        "description": "Luminaire not functioning, dark street near primary school.",
        "category": "STREETLIGHTS",
        "latitude": 17.4450,
        "longitude": 78.4930
    }, headers=citizen_headers)
    assert comp_resp.status_code == 201
    comp_id = comp_resp.json()["id"]

    depts = client.get("/api/v1/admin/departments", headers=staff_headers).json()
    roads_dept = depts[0]

    wo_resp = client.post("/api/v1/admin/work-orders", json={
        "complaint_id": comp_id,
        "department_id": roads_dept["id"],
        "crew_id": crew_a_id,
        "title": "Replace 70W sodium lamp with LED",
        "instructions": "Inspect capacitor and replace luminaire."
    }, headers=staff_headers)
    assert wo_resp.status_code == 201
    wo_id = wo_resp.json()["id"]

    # 4. Crew B attempts to accept Crew A's work order -> 403 Forbidden!
    b_accept = client.post(f"/api/v1/admin/work-orders/{wo_id}/accept", headers=crew_b_headers)
    assert b_accept.status_code == 403
    assert "not assigned to you" in b_accept.json()["detail"].lower()

    # 5. Crew B attempts to patch status of Crew A's work order -> 403 Forbidden!
    b_patch = client.patch(
        f"/api/v1/admin/work-orders/{wo_id}/status",
        json={"status": "IN_PROGRESS", "note": "Illegal update attempt by Crew B."},
        headers=crew_b_headers
    )
    assert b_patch.status_code == 403
    assert "only update your assigned work orders" in b_patch.json()["detail"].lower()

    # 6. Crew B attempts to submit evidence for Crew A's work order -> 403 Forbidden!
    b_evidence = client.post(
        f"/api/v1/admin/work-orders/{wo_id}/submit-evidence",
        json={"completion_notes": "Fake completion note by wrong crew."},
        headers=crew_b_headers
    )
    assert b_evidence.status_code == 403
    assert "not assigned to you" in b_evidence.json()["detail"].lower()

    # 7. Crew B lists work orders -> Crew A's work order MUST NOT appear!
    b_list = client.get("/api/v1/admin/work-orders", headers=crew_b_headers)
    assert b_list.status_code == 200
    b_wo_ids = [w["id"] for w in b_list.json()]
    assert wo_id not in b_wo_ids

def test_phase3_citizen_idor_isolation():
    """
    CRITICAL IDOR TEST:
    Citizen Priya cannot access, cancel, clarify, or confirm Citizen Arjun's complaints.
    """
    limiter._storage.reset()
    arjun_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")
    priya_headers = get_auth_headers("citizen.priya@example.com", "CitizenPass2026!")

    # Arjun creates a complaint
    arjun_comp = client.post("/api/v1/complaints", json={
        "title": f"Arjun's private water pipe issue #{uuid.uuid4().hex[:6]}",
        "description": "Leakage on residential connection outside gate.",
        "category": "WATER_SUPPLY",
        "latitude": 17.4410,
        "longitude": 78.4900
    }, headers=arjun_headers).json()
    arjun_comp_id = arjun_comp["id"]

    # Priya attempts to view Arjun's complaint -> 403 Forbidden
    priya_view = client.get(f"/api/v1/complaints/{arjun_comp_id}", headers=priya_headers)
    assert priya_view.status_code == 403

    # Priya attempts to cancel Arjun's complaint -> 403 Forbidden
    priya_cancel = client.post(
        f"/api/v1/complaints/{arjun_comp_id}/cancel",
        json={"reason": "Attempting malicious cancellation."},
        headers=priya_headers
    )
    assert priya_cancel.status_code == 403

    # Priya attempts to clarify Arjun's complaint -> 403 Forbidden
    priya_clarify = client.post(
        f"/api/v1/complaints/{arjun_comp_id}/clarify",
        json={"information": "Malicious clarification attempt."},
        headers=priya_headers
    )
    assert priya_clarify.status_code == 403

    # Priya attempts to confirm resolution -> 403 Forbidden
    priya_confirm = client.post(
        f"/api/v1/complaints/{arjun_comp_id}/confirm-resolution",
        json={"is_satisfied": True},
        headers=priya_headers
    )
    assert priya_confirm.status_code == 403

def test_phase3_coordinate_bounds_and_storage():
    """
    Tests geographic coordinate validation and exact storage in PostgreSQL:
    - Real coordinates (17.4420, 78.4910) stored and retrieved accurately.
    - Out-of-bounds latitude (< -90 or > 90) rejected with 422.
    - Out-of-bounds longitude (< -180 or > 180) rejected with 422.
    """
    limiter._storage.reset()
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")

    # 1. Out of bounds latitude (> 90)
    bad_lat_high = client.post("/api/v1/complaints", json={
        "title": "Invalid latitude complaint",
        "description": "Attempting to create complaint with latitude 95.0.",
        "category": "ROADS",
        "latitude": 95.0,
        "longitude": 78.4910
    }, headers=citizen_headers)
    assert bad_lat_high.status_code == 422

    # 2. Out of bounds latitude (< -90)
    bad_lat_low = client.post("/api/v1/complaints", json={
        "title": "Invalid latitude complaint",
        "description": "Attempting to create complaint with latitude -95.0.",
        "category": "ROADS",
        "latitude": -95.0,
        "longitude": 78.4910
    }, headers=citizen_headers)
    assert bad_lat_low.status_code == 422

    # 3. Out of bounds longitude (> 180)
    bad_lon_high = client.post("/api/v1/complaints", json={
        "title": "Invalid longitude complaint",
        "description": "Attempting to create complaint with longitude 185.0.",
        "category": "ROADS",
        "latitude": 17.4420,
        "longitude": 185.0
    }, headers=citizen_headers)
    assert bad_lon_high.status_code == 422

    # 4. Out of bounds longitude (< -180)
    bad_lon_low = client.post("/api/v1/complaints", json={
        "title": "Invalid longitude complaint",
        "description": "Attempting to create complaint with longitude -185.0.",
        "category": "ROADS",
        "latitude": 17.4420,
        "longitude": -185.0
    }, headers=citizen_headers)
    assert bad_lon_low.status_code == 422

    # 5. Valid coordinates persist accurately
    valid_lat = 17.4567
    valid_lon = 78.4321
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

def test_phase3_evidence_access_authorization():
    """
    Evidence endpoint authorization:
    - Anonymous access returns 401 Unauthorized.
    - Invalid bearer token returns 401 Unauthorized.
    """
    # 1. Anonymous access
    anon_resp = client.get("/api/v1/evidence/00000000-0000-0000-0000-000000000000")
    assert anon_resp.status_code == 401

    # 2. Invalid bearer token
    bad_token_resp = client.get(
        "/api/v1/evidence/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": "Bearer totally-invalid-jwt-token"}
    )
    assert bad_token_resp.status_code == 401

def test_phase3_dashboard_real_metrics():
    """
    Dashboard metrics dynamic computation:
    - Staff / Admin can view calculated analytics from PostgreSQL.
    - Citizen access is forbidden (403).
    - Unauthenticated access is unauthorized (401).
    """
    limiter._storage.reset()
    staff_headers = get_auth_headers("officer.sharma@civicfix.gov", "StaffSecure2026!")
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")

    # 1. Staff access returns real computed metrics
    metrics_resp = client.get("/api/v1/admin/dashboard", headers=staff_headers)
    assert metrics_resp.status_code == 200
    data = metrics_resp.json()

    assert "metrics" in data
    assert "total_complaints" in data["metrics"]
    assert "active_complaints" in data["metrics"]
    assert "resolved_complaints" in data["metrics"]
    assert data["metrics"]["total_complaints"] >= 0
    assert "by_category" in data
    assert "by_priority" in data
    assert "by_department" in data

    # 2. Citizen access returns 403 Forbidden
    cit_resp = client.get("/api/v1/admin/dashboard", headers=citizen_headers)
    assert cit_resp.status_code == 403

    # 3. Anonymous access returns 401 Unauthorized
    anon_resp = client.get("/api/v1/admin/dashboard")
    assert anon_resp.status_code == 401
