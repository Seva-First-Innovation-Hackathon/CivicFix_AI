import pytest
import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.core.limiter import limiter
from app.models.enums import ComplaintStatus, WorkOrderStatus, PriorityLevel

client = TestClient(app)

def get_auth_headers(email: str, password: str) -> dict:
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200, f"Login failed for {email}: {login_resp.text}"
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_full_complaint_lifecycle_10_steps():
    """
    Automated 10-step full-lifecycle end-to-end integration test:
    1. Citizen registers and submits complaint with coordinates.
    2. Initial status verified (SUBMITTED / AI_ANALYSIS_PENDING); invalid transitions rejected.
    3. AI analysis records state.
    4. Municipal staff verifies complaint and assigns priority (P1-P4).
    5. Municipal staff requests clarification -> Citizen clarifies -> Returns to UNDER_REVIEW.
    6. Municipal staff assigns department and dispatches work order -> IN_PROGRESS.
    7. Field crew accepts assignment, logs progress, and submits completion evidence -> WORK_COMPLETED_PENDING_REVIEW.
    8. Municipal staff reviews crew evidence and approves -> AWAITING_CITIZEN_CONFIRMATION.
    9. Citizen reopens with reason, staff resolves, citizen confirms with rating -> RESOLVED.
    10. Audit history, timeline, and privacy separation verified.
    """
    limiter._storage.reset()

    # Step 1: Citizen logs in and submits complaint
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")
    staff_headers = get_auth_headers("officer.sharma@civicfix.gov", "StaffSecure2026!")
    crew_headers = get_auth_headers("crew.patel@civicfix.gov", "CrewSecure2026!")
    admin_headers = get_auth_headers("admin@civicfix.gov", "AdminSecure2026!")

    create_payload = {
        "title": f"Deep dangerous crater on 5th avenue #{uuid.uuid4().hex[:6]}",
        "description": "Deep 4-foot crater obstructing road traffic near the main market. Immediate hazard.",
        "category": "ROADS",
        "latitude": 17.4420,
        "longitude": 78.4910,
        "address": "5th Avenue, Market Road, Ward 12",
        "landmark": "Opposite Central Bank"
    }

    comp_resp = client.post("/api/v1/complaints", json=create_payload, headers=citizen_headers)
    assert comp_resp.status_code == 201
    comp_data = comp_resp.json()
    complaint_id = comp_data["id"]
    ref_number = comp_data["reference_number"]
    assert ref_number.startswith("CF-")

    # Step 2: Validate initial status and prevent illegal arbitrary jumps
    assert comp_data["status"] in ["SUBMITTED", "AI_ANALYSIS_PENDING", "UNDER_REVIEW"]

    # Citizen cannot illegally confirm resolution before resolution is submitted
    illegal_confirm = client.post(
        f"/api/v1/complaints/{complaint_id}/confirm-resolution",
        json={"is_satisfied": True},
        headers=citizen_headers
    )
    assert illegal_confirm.status_code == 400

    # Step 3: AI Analysis is created
    detail_resp = client.get(f"/api/v1/complaints/{complaint_id}", headers=citizen_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] in ["SUBMITTED", "AI_ANALYSIS_PENDING", "UNDER_REVIEW"]

    # Step 4: Municipal Staff reviews and verifies complaint priority (P1-P4)
    verify_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/verify",
        json={"priority": "P2", "verification_notes": "Hazard confirmed near pedestrian crossing. Priority upgraded to P2."},
        headers=staff_headers
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "VERIFIED"
    assert verify_resp.json()["priority"] == "P2"

    # Step 5: Municipal Staff requests information -> Citizen clarifies
    req_info_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/request-info",
        json={"information": "Is the pothole located in front of shop 14 or shop 16?"},
        headers=staff_headers
    )
    assert req_info_resp.status_code == 200
    assert req_info_resp.json()["status"] == "AWAITING_CITIZEN_INFORMATION"
    assert req_info_resp.json()["clarification_requested"] == "Is the pothole located in front of shop 14 or shop 16?"

    # Citizen provides requested clarification
    clarify_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/clarify",
        json={"information": "Directly in front of Shop 16, right beside the pedestrian crossing ramp."},
        headers=citizen_headers
    )
    assert clarify_resp.status_code == 200
    assert clarify_resp.json()["status"] in ["UNDER_REVIEW", "VERIFIED"]

    # Step 6: Municipal Staff assigns department and dispatches Work Order to Field Crew
    depts = client.get("/api/v1/admin/departments", headers=staff_headers).json()
    assert len(depts) > 0
    roads_dept = next((d for d in depts if d["code"] == "ROADS"), depts[0])
    
    # Get crew id
    crews = client.get("/api/v1/admin/users?role=FIELD_CREW", headers=admin_headers).json()
    assert len(crews) > 0
    patel = next((c for c in crews if c["email"] == "crew.patel@civicfix.gov"), crews[0])
    crew_user_id = patel["id"]

    wo_payload = {
        "complaint_id": complaint_id,
        "department_id": roads_dept["id"],
        "crew_id": crew_user_id,
        "title": "Repair asphalt crater at Shop 16",
        "instructions": "Excavate damaged base, lay sub-base aggregate, apply hot-mix asphalt, compact level with grade."
    }
    wo_resp = client.post("/api/v1/admin/work-orders", json=wo_payload, headers=staff_headers)
    assert wo_resp.status_code == 201
    work_order = wo_resp.json()
    wo_id = work_order["id"]
    assert work_order["status"] == "ASSIGNED"

    # Complaint is now IN_PROGRESS
    comp_in_prog = client.get(f"/api/v1/complaints/{complaint_id}", headers=citizen_headers).json()
    assert comp_in_prog["status"] == "IN_PROGRESS"

    # Step 7: Field Crew accepts work order, logs progress, and submits completion evidence
    accept_resp = client.post(f"/api/v1/admin/work-orders/{wo_id}/accept", headers=crew_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "ACCEPTED"

    # Update progress
    progress_resp = client.patch(
        f"/api/v1/admin/work-orders/{wo_id}/status",
        json={"status": "IN_PROGRESS", "note": "Crew on site with roller and asphalt mixer."},
        headers=crew_headers
    )
    assert progress_resp.status_code == 200

    # Field crew submits completion evidence
    submit_evidence_resp = client.post(
        f"/api/v1/admin/work-orders/{wo_id}/submit-evidence",
        json={
            "completion_notes": "Crater repaired with 50mm compacted asphalt. Road swept and barricades removed.",
            "materials_used": "1.2 tonnes asphalt concrete, bitumen emulsion tack coat"
        },
        headers=crew_headers
    )
    assert submit_evidence_resp.status_code == 200
    assert submit_evidence_resp.json()["status"] in ["COMPLETED", "WORK_COMPLETED_PENDING_REVIEW"]

    # Complaint is now in WORK_COMPLETED_PENDING_REVIEW (Crew cannot approve their own work!)
    comp_pending = client.get(f"/api/v1/complaints/{complaint_id}", headers=citizen_headers).json()
    assert comp_pending["status"] == "WORK_COMPLETED_PENDING_REVIEW"

    # Step 8: Municipal Staff reviews evidence and approves
    review_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/review-evidence",
        json={"is_approved": True, "notes": "Asphalt compaction verified; surface flush with road."},
        headers=staff_headers
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "AWAITING_CITIZEN_CONFIRMATION"

    # Step 9: Citizen Reopening and Final Confirmation
    # Citizen tests reopening
    reopen_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/reopen",
        json={"is_satisfied": False, "reopen_reason": "Loose gravel remains scattered on the bike lane.", "feedback_notes": "Needs sweeping."},
        headers=citizen_headers
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["status"] == "REOPENED"

    # Staff re-submits resolution after sweeping
    res_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/resolution",
        json={"resolution_notes": "Crew re-visited and machine-swept bike lane."},
        headers=staff_headers
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "AWAITING_CITIZEN_CONFIRMATION"

    # Citizen confirms resolution with satisfaction rating
    confirm_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/confirm-resolution",
        json={"is_satisfied": True, "feedback_rating": 5, "feedback_notes": "Cleaned up and completed properly. Thank you!"},
        headers=citizen_headers
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "RESOLVED"

    # Step 10: Audit Timeline & Privacy Separation
    # Check timeline contains status transitions
    timeline_resp = client.get(f"/api/v1/complaints/{complaint_id}/timeline", headers=citizen_headers)
    assert timeline_resp.status_code == 200
    timeline = timeline_resp.json()
    assert len(timeline) >= 4

    # Staff adds an internal note
    internal_note_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/internal-note",
        json={"content": "INTERNAL: Contractor invoiced under municipal road maintenance budget code 402."},
        headers=staff_headers
    )
    assert internal_note_resp.status_code == 200

    # Citizen viewing comments must NOT see internal staff note
    cit_comments = client.get(f"/api/v1/complaints/{complaint_id}/comments", headers=citizen_headers).json()
    for comm in cit_comments:
        assert comm["is_internal"] is False
        assert "budget code 402" not in comm["content"]

    # Staff viewing comments CAN see internal staff note
    staff_comments = client.get(f"/api/v1/complaints/{complaint_id}/comments", headers=staff_headers).json()
    has_internal = any(c["is_internal"] is True and "budget code 402" in c["content"] for c in staff_comments)
    assert has_internal is True

def test_citizen_cancellation_workflow():
    """
    Test citizen can cancel their own eligible complaint with a recorded reason,
    and cannot cancel already resolved/cancelled complaints.
    """
    limiter._storage.reset()
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")

    # Create complaint
    create_resp = client.post("/api/v1/complaints", json={
        "title": "Temporary debris left by construction truck",
        "description": "Loose soil deposited on curb.",
        "category": "GARBAGE",
        "latitude": 17.4350,
        "longitude": 78.4820
    }, headers=citizen_headers)
    assert create_resp.status_code == 201
    comp_id = create_resp.json()["id"]

    # Cancel complaint
    cancel_resp = client.post(
        f"/api/v1/complaints/{comp_id}/cancel",
        json={"reason": "Construction contractor returned and cleared the debris themselves."},
        headers=citizen_headers
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"
    assert "cleared the debris" in cancel_resp.json()["cancellation_reason"]

    # Cancelling again must fail with 400
    repeat_cancel = client.post(
        f"/api/v1/complaints/{comp_id}/cancel",
        json={"reason": "Already cancelled."},
        headers=citizen_headers
    )
    assert repeat_cancel.status_code == 400

def test_municipal_staff_rejection_workflow():
    """
    Test municipal staff can reject an invalid or out-of-jurisdiction complaint with documented reason.
    """
    limiter._storage.reset()
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")
    staff_headers = get_auth_headers("officer.sharma@civicfix.gov", "StaffSecure2026!")

    create_resp = client.post("/api/v1/complaints", json={
        "title": "Private garden hedge overgrown",
        "description": "Neighbor's private garden hedge is untrimmed.",
        "category": "TREES_HAZARDS",
        "latitude": 17.4300,
        "longitude": 78.4800
    }, headers=citizen_headers)
    assert create_resp.status_code == 201
    comp_id = create_resp.json()["id"]

    # Reject without reason fails
    bad_reject = client.post(
        f"/api/v1/admin/complaints/{comp_id}/reject",
        json={"reason": "   "},
        headers=staff_headers
    )
    assert bad_reject.status_code in [400, 422]

    # Reject with valid documented reason
    reject_resp = client.post(
        f"/api/v1/admin/complaints/{comp_id}/reject",
        json={"reason": "Private residential property issue. Outside municipal civil authority mandate."},
        headers=staff_headers
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"
    assert "Outside municipal civil authority" in reject_resp.json()["rejection_reason"]

def test_flag_for_investigation_workflow():
    """
    Test municipal staff can flag suspicious or hazardous complaints for investigation.
    """
    limiter._storage.reset()
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")
    staff_headers = get_auth_headers("officer.sharma@civicfix.gov", "StaffSecure2026!")

    create_resp = client.post("/api/v1/complaints", json={
        "title": "Tampered electrical transformer lock",
        "description": "Lock has been broken repeatedly at the municipal substation.",
        "category": "STREETLIGHTS",
        "latitude": 17.4320,
        "longitude": 78.4850
    }, headers=citizen_headers)
    assert create_resp.status_code == 201
    comp_id = create_resp.json()["id"]

    # Flag for investigation
    flag_resp = client.post(
        f"/api/v1/admin/complaints/{comp_id}/flag-investigation",
        json={"reason": "Suspected repeated copper wire theft. Referred to electrical safety inspection unit."},
        headers=staff_headers
    )
    assert flag_resp.status_code == 200
    assert flag_resp.json()["status"] == "FLAGGED_FOR_INVESTIGATION"
    assert "Suspected repeated copper wire theft" in flag_resp.json()["investigation_notes"]

def test_role_enforcement_and_crew_restrictions():
    """
    Security test: Field crew cannot verify complaints or review evidence,
    and citizens cannot accept work orders or access admin routes.
    """
    limiter._storage.reset()
    citizen_headers = get_auth_headers("citizen.arjun@example.com", "CitizenPass2026!")
    crew_headers = get_auth_headers("crew.patel@civicfix.gov", "CrewSecure2026!")

    # Create complaint
    create_resp = client.post("/api/v1/complaints", json={
        "title": "Water pipeline leakage on street 4",
        "description": "Water leaking continuously from main line valve.",
        "category": "WATER_SUPPLY",
        "latitude": 17.4360,
        "longitude": 78.4870
    }, headers=citizen_headers)
    comp_id = create_resp.json()["id"]

    # Crew attempts to call /verify -> Forbidden
    crew_verify = client.post(
        f"/api/v1/admin/complaints/{comp_id}/verify",
        json={"priority": "P1"},
        headers=crew_headers
    )
    assert crew_verify.status_code == 403

    # Crew attempts to review evidence (cannot self-approve) -> Forbidden
    crew_review = client.post(
        f"/api/v1/admin/complaints/{comp_id}/review-evidence",
        json={"is_approved": True, "notes": "I approve my own work."},
        headers=crew_headers
    )
    assert crew_review.status_code == 403

    # Citizen attempts to accept a work order -> Forbidden
    fake_wo_id = str(uuid.uuid4())
    cit_accept = client.post(
        f"/api/v1/admin/work-orders/{fake_wo_id}/accept",
        headers=citizen_headers
    )
    assert cit_accept.status_code == 403
