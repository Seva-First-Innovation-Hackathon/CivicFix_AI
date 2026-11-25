import uuid
from app.core.limiter import limiter


def get_auth_headers(client, actor: dict) -> dict:
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": actor["email"], "password": actor["password"]},
    )
    assert login_resp.status_code == 200, f"Login failed for {actor['email']}: {login_resp.text}"
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_full_complaint_lifecycle_10_steps(client, test_actors):
    """
    Automated 10-step full-lifecycle end-to-end integration test across all 4 roles
    in an isolated per-test database without seeded global credentials.
    """
    limiter._storage.reset()

    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])
    staff_headers = get_auth_headers(client, test_actors["staff_roads"])
    crew_headers = get_auth_headers(client, test_actors["crew_a"])
    admin_headers = get_auth_headers(client, test_actors["admin"])

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

    assert comp_data["status"] in ["SUBMITTED", "AI_ANALYSIS_PENDING", "UNDER_REVIEW"]

    illegal_confirm = client.post(
        f"/api/v1/complaints/{complaint_id}/confirm-resolution",
        json={"is_satisfied": True},
        headers=citizen_headers
    )
    assert illegal_confirm.status_code == 400

    detail_resp = client.get(f"/api/v1/complaints/{complaint_id}", headers=citizen_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] in ["SUBMITTED", "AI_ANALYSIS_PENDING", "UNDER_REVIEW"]

    verify_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/verify",
        json={"priority": "P2", "verification_notes": "Hazard confirmed near pedestrian crossing. Priority upgraded to P2."},
        headers=staff_headers
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "VERIFIED"
    assert verify_resp.json()["priority"] == "P2"

    req_info_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/request-info",
        json={"information": "Is the pothole located in front of shop 14 or shop 16?"},
        headers=staff_headers
    )
    assert req_info_resp.status_code == 200
    assert req_info_resp.json()["status"] == "AWAITING_CITIZEN_INFORMATION"
    assert req_info_resp.json()["clarification_requested"] == "Is the pothole located in front of shop 14 or shop 16?"

    clarify_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/clarify",
        json={"information": "Directly in front of Shop 16, right beside the pedestrian crossing ramp."},
        headers=citizen_headers
    )
    assert clarify_resp.status_code == 200
    assert clarify_resp.json()["status"] in ["UNDER_REVIEW", "VERIFIED"]

    roads_dept = test_actors["departments"]["ROADS"]
    crew_user_id = test_actors["crew_a"]["user"].id

    wo_payload = {
        "complaint_id": complaint_id,
        "department_id": roads_dept.id,
        "crew_id": crew_user_id,
        "title": "Repair asphalt crater at Shop 16",
        "instructions": "Excavate damaged base, lay sub-base aggregate, apply hot-mix asphalt, compact level with grade."
    }
    wo_resp = client.post("/api/v1/admin/work-orders", json=wo_payload, headers=staff_headers)
    assert wo_resp.status_code == 201
    work_order = wo_resp.json()
    wo_id = work_order["id"]
    assert work_order["status"] == "ASSIGNED"

    comp_in_prog = client.get(f"/api/v1/complaints/{complaint_id}", headers=citizen_headers).json()
    assert comp_in_prog["status"] == "IN_PROGRESS"

    accept_resp = client.post(f"/api/v1/admin/work-orders/{wo_id}/accept", headers=crew_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "ACCEPTED"

    progress_resp = client.patch(
        f"/api/v1/admin/work-orders/{wo_id}/status",
        json={"status": "IN_PROGRESS", "note": "Crew on site with roller and asphalt mixer."},
        headers=crew_headers
    )
    assert progress_resp.status_code == 200

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

    comp_pending = client.get(f"/api/v1/complaints/{complaint_id}", headers=citizen_headers).json()
    assert comp_pending["status"] == "WORK_COMPLETED_PENDING_REVIEW"

    review_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/review-evidence",
        json={"is_approved": True, "notes": "Asphalt compaction verified; surface flush with road."},
        headers=staff_headers
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "AWAITING_CITIZEN_CONFIRMATION"

    reopen_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/reopen",
        json={"is_satisfied": False, "reopen_reason": "Loose gravel remains scattered on the bike lane.", "feedback_notes": "Needs sweeping."},
        headers=citizen_headers
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["status"] == "REOPENED"

    res_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/resolution",
        json={"resolution_notes": "Crew re-visited and machine-swept bike lane."},
        headers=staff_headers
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "AWAITING_CITIZEN_CONFIRMATION"

    confirm_resp = client.post(
        f"/api/v1/complaints/{complaint_id}/confirm-resolution",
        json={"is_satisfied": True, "feedback_rating": 5, "feedback_notes": "Cleaned up and completed properly. Thank you!"},
        headers=citizen_headers
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "RESOLVED"

    timeline_resp = client.get(f"/api/v1/complaints/{complaint_id}/timeline", headers=citizen_headers)
    assert timeline_resp.status_code == 200
    timeline = timeline_resp.json()
    assert len(timeline) >= 4

    internal_note_resp = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/internal-note",
        json={"content": "INTERNAL: Contractor invoiced under municipal road maintenance budget code 402."},
        headers=staff_headers
    )
    assert internal_note_resp.status_code == 200

    cit_comments = client.get(f"/api/v1/complaints/{complaint_id}/comments", headers=citizen_headers).json()
    for comm in cit_comments:
        assert comm["is_internal"] is False
        assert "budget code 402" not in comm["content"]

    staff_comments = client.get(f"/api/v1/complaints/{complaint_id}/comments", headers=staff_headers).json()
    has_internal = any(c["is_internal"] is True and "budget code 402" in c["content"] for c in staff_comments)
    assert has_internal is True


def test_citizen_cancellation_workflow(client, test_actors):
    """Test citizen cancellation with mandatory reason and idempotent guard."""
    limiter._storage.reset()
    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])

    create_resp = client.post("/api/v1/complaints", json={
        "title": "Temporary debris left by construction truck",
        "description": "Loose soil deposited on curb.",
        "category": "GARBAGE",
        "latitude": 17.4350,
        "longitude": 78.4820
    }, headers=citizen_headers)
    assert create_resp.status_code == 201
    comp_id = create_resp.json()["id"]

    cancel_resp = client.post(
        f"/api/v1/complaints/{comp_id}/cancel",
        json={"reason": "Construction contractor returned and cleared the debris themselves."},
        headers=citizen_headers
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"
    assert "cleared the debris" in cancel_resp.json()["cancellation_reason"]

    repeat_cancel = client.post(
        f"/api/v1/complaints/{comp_id}/cancel",
        json={"reason": "Already cancelled."},
        headers=citizen_headers
    )
    assert repeat_cancel.status_code == 400


def test_municipal_staff_rejection_workflow(client, test_actors):
    """Test municipal staff rejection with mandatory documented reason."""
    limiter._storage.reset()
    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])
    admin_headers = get_auth_headers(client, test_actors["admin"])

    create_resp = client.post("/api/v1/complaints", json={
        "title": "Private garden hedge overgrown",
        "description": "Neighbor's private garden hedge is untrimmed.",
        "category": "TREES_HAZARDS",
        "latitude": 17.4300,
        "longitude": 78.4800
    }, headers=citizen_headers)
    assert create_resp.status_code == 201
    comp_id = create_resp.json()["id"]

    bad_reject = client.post(
        f"/api/v1/admin/complaints/{comp_id}/reject",
        json={"reason": "   "},
        headers=admin_headers
    )
    assert bad_reject.status_code in [400, 422]

    reject_resp = client.post(
        f"/api/v1/admin/complaints/{comp_id}/reject",
        json={"reason": "Private residential property issue. Outside municipal civil authority mandate."},
        headers=admin_headers
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"
    assert "Outside municipal civil authority" in reject_resp.json()["rejection_reason"]


def test_flag_for_investigation_workflow(client, test_actors):
    """Test municipal staff flagging complaints for investigation."""
    limiter._storage.reset()
    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])
    staff_headers = get_auth_headers(client, test_actors["staff_lighting"])

    create_resp = client.post("/api/v1/complaints", json={
        "title": "Tampered electrical transformer lock",
        "description": "Lock has been broken repeatedly at the municipal substation.",
        "category": "STREETLIGHTS",
        "latitude": 17.4320,
        "longitude": 78.4850
    }, headers=citizen_headers)
    assert create_resp.status_code == 201
    comp_id = create_resp.json()["id"]

    flag_resp = client.post(
        f"/api/v1/admin/complaints/{comp_id}/flag-investigation",
        json={"reason": "Suspected repeated copper wire theft. Referred to electrical safety inspection unit."},
        headers=staff_headers
    )
    assert flag_resp.status_code == 200
    assert flag_resp.json()["status"] == "FLAGGED_FOR_INVESTIGATION"
    assert "Suspected repeated copper wire theft" in flag_resp.json()["investigation_notes"]


def test_role_enforcement_and_crew_restrictions(client, test_actors):
    """Security test: Field crew cannot verify complaints or review evidence, citizens cannot accept WOs."""
    limiter._storage.reset()
    citizen_headers = get_auth_headers(client, test_actors["citizen_a"])
    crew_headers = get_auth_headers(client, test_actors["crew_a"])

    create_resp = client.post("/api/v1/complaints", json={
        "title": "Water pipeline leakage on street 4",
        "description": "Water leaking continuously from main line valve.",
        "category": "WATER_SUPPLY",
        "latitude": 17.4360,
        "longitude": 78.4870
    }, headers=citizen_headers)
    comp_id = create_resp.json()["id"]

    assert client.post(
        f"/api/v1/admin/complaints/{comp_id}/verify",
        json={"priority": "P1"},
        headers=crew_headers
    ).status_code == 403

    assert client.post(
        f"/api/v1/admin/complaints/{comp_id}/review-evidence",
        json={"is_approved": True, "notes": "I approve my own work."},
        headers=crew_headers
    ).status_code == 403

    fake_wo_id = str(uuid.uuid4())
    assert client.post(
        f"/api/v1/admin/work-orders/{fake_wo_id}/accept",
        headers=citizen_headers
    ).status_code == 403
