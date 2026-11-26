"""
Phase 2.8 & 2.8.1 Security, Lifecycle, Refresh CAS & Bootstrap Regression Tests.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import io
import os
import subprocess
import sys
import threading

from PIL import Image
import pytest
from sqlalchemy.orm import Query

from app.core.limiter import limiter
from app.core.security import hash_token
from app.models.entities import (
    AuditLog,
    Complaint,
    ComplaintAttachment,
    MunicipalDepartment,
    PotentialDuplicate,
    RefreshToken,
    User,
    WorkOrder,
)
from app.models.enums import ComplaintStatus, UserRole, WorkOrderStatus
from app.services.storage.service import storage_service


def _login(client, email: str, password: str) -> dict:
    limiter._storage.reset()
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (12, 12), color=(40, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# HIGH-02: Evidence Authentication (Bearer Header Only, No ?token=, Map Safety)
# ---------------------------------------------------------------------------

def test_evidence_rejects_query_token_and_secures_map_metadata(client, test_actors, db_session):
    """
    1. Query-string ?token= must never authenticate evidence or /uploads/ endpoints (401).
    2. Authorization: Bearer succeeds only for authorized owner / dept staff / assigned crew.
    3. Map complaint endpoint exposes safe first_attachment_id and omits raw /uploads/ first_image URLs.
    """
    t_cit_a = _login(client, test_actors["citizen_a"]["email"], test_actors["citizen_a"]["password"])["access_token"]
    t_cit_b = _login(client, test_actors["citizen_b"]["email"], test_actors["citizen_b"]["password"])["access_token"]
    t_roads = _login(client, test_actors["staff_roads"]["email"], test_actors["staff_roads"]["password"])["access_token"]
    t_light = _login(client, test_actors["staff_lighting"]["email"], test_actors["staff_lighting"]["password"])["access_token"]
    t_crew_a = _login(client, test_actors["crew_a"]["email"], test_actors["crew_a"]["password"])["access_token"]
    t_crew_b = _login(client, test_actors["crew_b"]["email"], test_actors["crew_b"]["password"])["access_token"]

    comp = client.post(
        "/api/v1/complaints",
        json={
            "title": "Exposed manhole along ward avenue",
            "description": "Missing cast-iron cover beside bus bay.",
            "category": "ROADS",
            "latitude": 17.4415,
            "longitude": 78.4915,
        },
        headers=_auth(t_cit_a),
    ).json()
    cid = comp["id"]

    # Assign work order to crew_a in ROADS
    client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": cid,
            "department_id": test_actors["departments"]["ROADS"].id,
            "crew_id": test_actors["crew_a"]["user"].id,
            "title": "Install new cover",
            "instructions": "Fit frame securely.",
        },
        headers=_auth(t_roads),
    )

    att = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("manhole.png", _tiny_png(), "image/png")},
        data={"attachment_type": "CITIZEN_ORIGINAL"},
        headers=_auth(t_cit_a),
    ).json()

    # Query-string ?token=... is strictly rejected (401)
    assert client.get(f"/api/v1/evidence/{att['id']}?token={t_cit_a}").status_code == 401
    assert client.get(f"{att['file_path']}?token={t_cit_a}").status_code == 401
    assert client.get(f"/api/v1/evidence/{att['id']}").status_code == 401

    # Bearer header succeeds only for authorized owner / dept staff / assigned crew
    assert client.get(f"/api/v1/evidence/{att['id']}", headers=_auth(t_cit_a)).status_code == 200
    assert client.get(f"/api/v1/evidence/{att['id']}", headers=_auth(t_roads)).status_code == 200
    assert client.get(f"/api/v1/evidence/{att['id']}", headers=_auth(t_crew_a)).status_code == 200

    assert client.get(f"/api/v1/evidence/{att['id']}", headers=_auth(t_cit_b)).status_code == 403
    assert client.get(f"/api/v1/evidence/{att['id']}", headers=_auth(t_light)).status_code == 403
    assert client.get(f"/api/v1/evidence/{att['id']}", headers=_auth(t_crew_b)).status_code == 403

    # Map complaints response carries first_attachment_id and NEVER exposes raw /uploads/ first_image
    map_resp = client.get("/api/v1/admin/map/complaints", headers=_auth(t_roads))
    assert map_resp.status_code == 200
    entry = next(item for item in map_resp.json()["complaints"] if item["id"] == cid)
    assert entry["first_attachment_id"] == att["id"]
    assert "first_image" not in entry


# ---------------------------------------------------------------------------
# HIGH-01 & HIGH-04: Scoped Crews, Work Orders, Duplicate Scoping
# ---------------------------------------------------------------------------

def test_scoped_admin_crews_endpoint_and_rbac(client, test_actors):
    roads_headers = _auth(_login(client, test_actors["staff_roads"]["email"], test_actors["staff_roads"]["password"])["access_token"])
    admin_headers = _auth(_login(client, test_actors["admin"]["email"], test_actors["admin"]["password"])["access_token"])
    crew_headers = _auth(_login(client, test_actors["crew_a"]["email"], test_actors["crew_a"]["password"])["access_token"])
    citizen_headers = _auth(_login(client, test_actors["citizen_a"]["email"], test_actors["citizen_a"]["password"])["access_token"])

    assert client.get("/api/v1/admin/users?role=FIELD_CREW", headers=roads_headers).status_code == 403
    assert client.get("/api/v1/admin/crews", headers=crew_headers).status_code == 403
    assert client.get("/api/v1/admin/crews", headers=citizen_headers).status_code == 403

    roads_crews = client.get("/api/v1/admin/crews", headers=roads_headers)
    assert roads_crews.status_code == 200
    roads_emails = {u["email"] for u in roads_crews.json()}
    assert test_actors["crew_a"]["email"] in roads_emails
    assert test_actors["crew_b"]["email"] not in roads_emails

    admin_crews = client.get("/api/v1/admin/crews", headers=admin_headers)
    assert admin_crews.status_code == 200
    admin_emails = {u["email"] for u in admin_crews.json()}
    assert test_actors["crew_a"]["email"] in admin_emails
    assert test_actors["crew_b"]["email"] in admin_emails


def test_department_scoping_on_work_orders_and_duplicates(client, db_session, test_actors):
    depts = test_actors["departments"]
    citizen_headers = _auth(_login(client, test_actors["citizen_a"]["email"], test_actors["citizen_a"]["password"])["access_token"])
    roads_headers = _auth(_login(client, test_actors["staff_roads"]["email"], test_actors["staff_roads"]["password"])["access_token"])
    light_headers = _auth(_login(client, test_actors["staff_lighting"]["email"], test_actors["staff_lighting"]["password"])["access_token"])

    c_roads = client.post(
        "/api/v1/complaints",
        json={
            "title": "Deep pothole near bus stop",
            "description": "Asphalt collapsed near curb creating a hazard for two-wheelers.",
            "category": "ROADS",
            "latitude": 17.4410,
            "longitude": 78.4910,
        },
        headers=citizen_headers,
    ).json()

    c_light_1 = client.post(
        "/api/v1/complaints",
        json={
            "title": "Unlit streetlight pole 14",
            "description": "LED luminaire on junction pole 14 completely dark all night.",
            "category": "STREETLIGHTS",
            "latitude": 17.4450,
            "longitude": 78.4950,
        },
        headers=citizen_headers,
    ).json()
    c_light_2 = client.post(
        "/api/v1/complaints",
        json={
            "title": "Dark junction lamp pole 14",
            "description": "Duplicate report for dark street lamp on pole 14 at junction.",
            "category": "STREETLIGHTS",
            "latitude": 17.4451,
            "longitude": 78.4951,
        },
        headers=citizen_headers,
    ).json()

    for cid, did in [
        (c_roads["id"], depts["ROADS"].id),
        (c_light_1["id"], depts["LIGHTING"].id),
        (c_light_2["id"], depts["LIGHTING"].id),
    ]:
        comp = db_session.query(Complaint).filter(Complaint.id == cid).first()
        comp.department_id = did
    db_session.commit()

    wo_roads = client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": c_roads["id"],
            "department_id": depts["ROADS"].id,
            "crew_id": test_actors["crew_a"]["user"].id,
            "title": "Patch asphalt crater",
            "instructions": "Fill with hot mix.",
        },
        headers=roads_headers,
    )
    assert wo_roads.status_code == 201

    wo_light = client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": c_light_1["id"],
            "department_id": depts["LIGHTING"].id,
            "crew_id": test_actors["crew_b"]["user"].id,
            "title": "Replace LED driver",
            "instructions": "Inspect pole wiring.",
        },
        headers=light_headers,
    )
    assert wo_light.status_code == 201

    roads_wo_ids = {wo["id"] for wo in client.get("/api/v1/admin/work-orders", headers=roads_headers).json()}
    assert wo_roads.json()["id"] in roads_wo_ids
    assert wo_light.json()["id"] not in roads_wo_ids

    dup = PotentialDuplicate(
        primary_complaint_id=c_light_1["id"],
        duplicate_complaint_id=c_light_2["id"],
        similarity_score=0.92,
        distance_meters=14.0,
        reason="Same streetlight pole",
        status="FLAGGED",
    )
    db_session.add(dup)
    db_session.commit()
    db_session.refresh(dup)

    roads_dup_ids = {d["id"] for d in client.get("/api/v1/admin/duplicates", headers=roads_headers).json()}
    assert dup.id not in roads_dup_ids

    dismiss_resp = client.post(
        f"/api/v1/admin/duplicates/{dup.id}/review",
        json={"status": "DISMISSED", "review_notes": "Cross-dept dismiss attempt"},
        headers=roads_headers,
    )
    assert dismiss_resp.status_code == 403
    db_session.refresh(dup)
    assert dup.status == "FLAGGED"

    assert client.post(
        f"/api/v1/admin/duplicates/{dup.id}/review",
        json={"status": "DISMISSED", "review_notes": "Valid distinct lamp issue"},
        headers=light_headers,
    ).status_code == 200


# ---------------------------------------------------------------------------
# HIGH-05: Strict Lifecycle, Counter Idempotency, Cross-Dept & Citizen Guards
# ---------------------------------------------------------------------------

def test_work_order_lifecycle_blocks_direct_completion_and_repeated_counter_decrements(client, db_session, test_actors):
    depts = test_actors["departments"]
    cit_headers = _auth(_login(client, test_actors["citizen_a"]["email"], test_actors["citizen_a"]["password"])["access_token"])
    roads_headers = _auth(_login(client, test_actors["staff_roads"]["email"], test_actors["staff_roads"]["password"])["access_token"])
    crew_headers = _auth(_login(client, test_actors["crew_a"]["email"], test_actors["crew_a"]["password"])["access_token"])

    comp = client.post(
        "/api/v1/complaints",
        json={
            "title": "Sunken storm manhole cover on avenue",
            "description": "Manhole frame is sunken by 4 inches in active vehicle lane.",
            "category": "ROADS",
            "latitude": 17.4420,
            "longitude": 78.4920,
        },
        headers=cit_headers,
    ).json()
    cid = comp["id"]

    # Create work order -> active_task_count increments 0 -> 1
    wo = client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": cid,
            "department_id": depts["ROADS"].id,
            "crew_id": test_actors["crew_a"]["user"].id,
            "title": "Raise manhole ring",
            "instructions": "Reset frame flush with pavement.",
        },
        headers=roads_headers,
    ).json()
    wo_id = wo["id"]

    crew_user = db_session.query(User).filter(User.id == test_actors["crew_a"]["user"].id).first()
    db_session.refresh(crew_user.crew_profile)
    assert crew_user.crew_profile.active_task_count == 1

    # Field crew CANNOT skip /submit-evidence by PATCHing COMPLETED or WORK_COMPLETED_PENDING_REVIEW (403)
    for forbidden_status in ("COMPLETED", "WORK_COMPLETED_PENDING_REVIEW"):
        r_patch = client.patch(
            f"/api/v1/admin/work-orders/{wo_id}/status",
            json={"status": forbidden_status, "note": "Bypassing evidence gate"},
            headers=crew_headers,
        )
        assert r_patch.status_code == 403
    assert client.patch(
        f"/api/v1/admin/work-orders/{wo_id}/status",
        json={"status": "COMPLETED", "note": "Staff bypass attempt"},
        headers=roads_headers,
    ).status_code == 400

    # Direct /resolution by FIELD_CREW is also blocked (403)
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/resolution",
        json={"resolution_notes": "Attempting to skip verification"},
        headers=crew_headers,
    ).status_code == 403

    # Counter remains 1 through legitimate status updates
    assert client.post(f"/api/v1/admin/work-orders/{wo_id}/accept", headers=crew_headers).status_code == 200
    assert client.patch(
        f"/api/v1/admin/work-orders/{wo_id}/status",
        json={"status": "BLOCKED", "note": "Waiting on concrete truck", "blocker_reason": "Delivery delay"},
        headers=crew_headers,
    ).status_code == 200
    assert client.patch(
        f"/api/v1/admin/work-orders/{wo_id}/status",
        json={"status": "IN_PROGRESS", "note": "Truck arrived, resuming work"},
        headers=crew_headers,
    ).status_code == 200
    db_session.refresh(crew_user.crew_profile)
    assert crew_user.crew_profile.active_task_count == 1

    # Submit evidence decrements active_task_count from 1 -> 0 once
    assert client.post(
        f"/api/v1/admin/work-orders/{wo_id}/submit-evidence",
        json={"completion_notes": "Ring reset with rapid-set concrete."},
        headers=crew_headers,
    ).status_code == 200
    db_session.refresh(crew_user.crew_profile)
    assert crew_user.crew_profile.active_task_count == 0

    # Duplicate submit-evidence or backward PATCH/assign/create_work_order are rejected (400) & counter stays 0
    assert client.post(
        f"/api/v1/admin/work-orders/{wo_id}/submit-evidence",
        json={"completion_notes": "Second submission should fail."},
        headers=crew_headers,
    ).status_code == 400
    assert client.patch(
        f"/api/v1/admin/work-orders/{wo_id}/status",
        json={"status": "IN_PROGRESS", "note": "Cannot reopen completed work order"},
        headers=crew_headers,
    ).status_code == 400
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/assign",
        json={"department_id": depts["ROADS"].id},
        headers=roads_headers,
    ).status_code == 400
    assert client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": cid,
            "department_id": depts["ROADS"].id,
            "crew_id": test_actors["crew_a"]["user"].id,
            "title": "Blocked pending review dispatch",
            "instructions": "Must reject while pending review.",
        },
        headers=roads_headers,
    ).status_code == 400
    db_session.refresh(crew_user.crew_profile)
    assert crew_user.crew_profile.active_task_count == 0

    # Staff approves -> WO becomes COMPLETED and citizen confirms -> RESOLVED
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/review-evidence",
        json={"is_approved": True, "notes": "Flush alignment verified."},
        headers=roads_headers,
    ).status_code == 200
    wo_row = db_session.query(WorkOrder).filter(WorkOrder.id == wo_id).first()
    assert wo_row.status == WorkOrderStatus.COMPLETED.value

    assert client.post(
        f"/api/v1/complaints/{cid}/confirm-resolution",
        json={"is_satisfied": True, "feedback_rating": 5, "feedback_notes": "Fixed well."},
        headers=cit_headers,
    ).status_code == 200

    # Closed RESOLVED complaint blocks assign, work-order creation, resolution, and work-order patches
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/assign",
        json={"department_id": depts["ROADS"].id},
        headers=roads_headers,
    ).status_code == 400
    assert client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": cid,
            "department_id": depts["ROADS"].id,
            "crew_id": test_actors["crew_a"]["user"].id,
            "title": "Late dispatch",
            "instructions": "Should fail.",
        },
        headers=roads_headers,
    ).status_code == 400
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/resolution",
        json={"resolution_notes": "Late resolution should fail"},
        headers=roads_headers,
    ).status_code == 400


def test_cross_department_dispatch_and_reopen_state_restrictions(client, db_session, test_actors):
    """
    1. MUNICIPAL_MEMBER cannot dispatch into or assign another department, even when complaint.department_id is None.
    2. Crew from another department is rejected for ROADS dispatch (even by GOVERNMENT_ADMIN -> 400).
    3. create_work_order rejects REOPENED complaints until triaged/verified/assigned.
    """
    depts = test_actors["departments"]
    cit_headers = _auth(_login(client, test_actors["citizen_a"]["email"], test_actors["citizen_a"]["password"])["access_token"])
    roads_headers = _auth(_login(client, test_actors["staff_roads"]["email"], test_actors["staff_roads"]["password"])["access_token"])
    admin_headers = _auth(_login(client, test_actors["admin"]["email"], test_actors["admin"]["password"])["access_token"])

    comp = client.post(
        "/api/v1/complaints",
        json={
            "title": "Unassigned triage issue needing strict dispatch validation",
            "description": "Sinkhole next to curb requiring strict dispatch checks.",
            "category": "ROADS",
            "latitude": 17.4410,
            "longitude": 78.4910,
        },
        headers=cit_headers,
    ).json()
    cid = comp["id"]

    # Force complaint.department_id = None cleanly to prove empty department_id cannot be abused
    c_row = db_session.query(Complaint).filter(Complaint.id == cid).first()
    c_row.department_id = None
    c_row.status = ComplaintStatus.VERIFIED.value
    db_session.commit()

    # Roads officer CANNOT assign to LIGHTING or dispatch LIGHTING work order or crew_b (LIGHTING crew)
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/assign",
        json={"department_id": depts["LIGHTING"].id},
        headers=roads_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": cid,
            "department_id": depts["LIGHTING"].id,
            "crew_id": test_actors["crew_b"]["user"].id,
            "title": "Cross-dept dispatch attempt",
            "instructions": "Must fail 403.",
        },
        headers=roads_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": cid,
            "department_id": depts["ROADS"].id,
            "crew_id": test_actors["crew_b"]["user"].id,
            "title": "Cross-dept crew dispatch attempt",
            "instructions": "Crew B belongs to LIGHTING, must fail 403.",
        },
        headers=roads_headers,
    ).status_code == 403

    # Even GOVERNMENT_ADMIN cannot dispatch a LIGHTING crew inside a ROADS work order (400)
    assert client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": cid,
            "department_id": depts["ROADS"].id,
            "crew_id": test_actors["crew_b"]["user"].id,
            "title": "Mismatched crew dept by admin",
            "instructions": "Must reject 400.",
        },
        headers=admin_headers,
    ).status_code == 400

    # Cross-municipality / conflicting jurisdiction check on assignment -> 403
    south_dept = MunicipalDepartment(
        name="South Zone Roads",
        code="ROADS_SOUTH",
        description="South municipality division",
        jurisdiction="South Municipality",
        is_active=True,
    )
    north_dept = MunicipalDepartment(
        name="North Zone Roads",
        code="ROADS_NORTH",
        description="North municipality division",
        jurisdiction="North Municipality",
        is_active=True,
    )
    db_session.add_all([south_dept, north_dept])
    db_session.flush()
    c_row.department_id = north_dept.id
    c_row.status = ComplaintStatus.VERIFIED.value
    db_session.commit()
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/assign",
        json={"department_id": south_dept.id},
        headers=admin_headers,
    ).status_code == 403

    # Reject work-order creation when complaint is REOPENED
    c_row.department_id = depts["ROADS"].id
    c_row.status = ComplaintStatus.REOPENED.value
    db_session.commit()
    assert client.post(
        "/api/v1/admin/work-orders",
        json={
            "complaint_id": cid,
            "department_id": depts["ROADS"].id,
            "crew_id": test_actors["crew_a"]["user"].id,
            "title": "Reopened complaint direct WO",
            "instructions": "Must require triage/verification before dispatch.",
        },
        headers=roads_headers,
    ).status_code == 400


def test_citizen_only_confirm_and_reopen_rejects_non_citizens_and_illegal_states(client, test_actors):
    cit_headers = _auth(_login(client, test_actors["citizen_a"]["email"], test_actors["citizen_a"]["password"])["access_token"])
    roads_headers = _auth(_login(client, test_actors["staff_roads"]["email"], test_actors["staff_roads"]["password"])["access_token"])
    crew_headers = _auth(_login(client, test_actors["crew_a"]["email"], test_actors["crew_a"]["password"])["access_token"])
    admin_headers = _auth(_login(client, test_actors["admin"]["email"], test_actors["admin"]["password"])["access_token"])

    comp = client.post(
        "/api/v1/complaints",
        json={
            "title": "Broken asphalt edge near intersection",
            "description": "Road pavement curb has crumbled leaving a sharp drop along bike lane.",
            "category": "ROADS",
            "latitude": 17.4401,
            "longitude": 78.4902,
        },
        headers=cit_headers,
    ).json()
    cid = comp["id"]

    # Active ticket cannot be reopened by citizen (400)
    assert client.post(
        f"/api/v1/complaints/{cid}/reopen",
        json={"is_satisfied": False, "reopen_reason": "Attempting invalid reopen on active ticket"},
        headers=cit_headers,
    ).status_code == 400

    # Staff moves to AWAITING_CITIZEN_CONFIRMATION
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/resolution",
        json={"resolution_notes": "Cleared debris from stormwater grate and flushed inlet."},
        headers=roads_headers,
    ).status_code == 200

    # Non-citizens (staff, crew, admin) are strictly blocked from confirm-resolution & reopen (403)
    for non_cit_hdr in (roads_headers, crew_headers, admin_headers):
        assert client.post(
            f"/api/v1/complaints/{cid}/confirm-resolution",
            json={"is_satisfied": True, "feedback_rating": 5},
            headers=non_cit_hdr,
        ).status_code == 403
        assert client.post(
            f"/api/v1/complaints/{cid}/reopen",
            json={"is_satisfied": False, "reopen_reason": "Non-citizen attempt to reopen"},
            headers=non_cit_hdr,
        ).status_code == 403

    # Legitimate citizen reopen from AWAITING_CITIZEN_CONFIRMATION -> REOPENED -> RESOLVED still works
    assert client.post(
        f"/api/v1/complaints/{cid}/reopen",
        json={"is_satisfied": False, "reopen_reason": "Water still pooling after rain."},
        headers=cit_headers,
    ).json()["status"] == "REOPENED"
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/resolution",
        json={"resolution_notes": "Cleared secondary obstruction downstream."},
        headers=roads_headers,
    ).status_code == 200
    assert client.post(
        f"/api/v1/complaints/{cid}/confirm-resolution",
        json={"is_satisfied": True, "feedback_rating": 5, "feedback_notes": "Flow restored."},
        headers=cit_headers,
    ).json()["status"] == "RESOLVED"


# ---------------------------------------------------------------------------
# HIGH-06: Deterministic Refresh CAS Loser, Family Revocation & Audit Persistence
# ---------------------------------------------------------------------------

def test_deterministic_cas_loser_revokes_family_and_persists_audit(client, db_session_factory, test_actors, monkeypatch):
    """
    Deterministically simulates a winning concurrent rotation committing right AFTER the
    losing request read `rt.is_revoked == False` and right BEFORE its atomic CAS `UPDATE`.
    Verifies:
    - Losing request enters the zero-row CAS branch (`updated != 1`).
    - Returns HTTP 401 without minting a new valid token.
    - Revokes the whole token family (including the winner's new refresh token).
    - Persists `REFRESH_TOKEN_REUSE_DETECTED` in AuditLog even when raising HTTP 401.
    """
    citizen = test_actors["citizen_a"]
    login_data = _login(client, citizen["email"], citizen["password"])
    initial_refresh = login_data["refresh_token"]

    orig_update = Query.update
    winner_tokens = {}
    simulated = {"done": False}

    def cas_losing_update(self, values, synchronize_session="evaluate", update_args=None):
        entity = self.column_descriptions[0].get("entity") if self.column_descriptions else None
        if entity is RefreshToken and not simulated["done"] and RefreshToken.replaced_by_jti in values:
            simulated["done"] = True
            # Simulate concurrent winner rotating & committing initial_refresh BEFORE losing CAS UPDATE executes
            other_db = db_session_factory()
            try:
                winner = other_db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(initial_refresh)).first()
                assert winner is not None and winner.is_revoked is False
                winner.is_revoked = True
                winner.revoked_reason = "rotated"
                winner.replaced_by_jti = "winner_jti_1"
                winner_child = RefreshToken(
                    jti="winner_jti_1",
                    token_hash=hash_token("winner_raw_secret_token"),
                    family_id=winner.family_id,
                    parent_jti=winner.jti,
                    user_id=winner.user_id,
                    is_revoked=False,
                    expires_at=winner.expires_at,
                )
                other_db.add(winner_child)
                other_db.commit()
                winner_tokens["family_id"] = winner.family_id
                winner_tokens["child_id"] = winner_child.id
            finally:
                other_db.close()

        return orig_update(self, values, synchronize_session=synchronize_session, update_args=update_args)

    monkeypatch.setattr(Query, "update", cas_losing_update)

    loser_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh})
    assert loser_resp.status_code == 401
    assert simulated["done"] is True

    # Verify in fresh session: token family (including winner child) revoked, NO extra active tokens, audit persisted
    check_db = db_session_factory()
    try:
        family_rows = check_db.query(RefreshToken).filter(RefreshToken.family_id == winner_tokens["family_id"]).all()
        assert len(family_rows) == 2
        assert all(row.is_revoked is True for row in family_rows)

        audit_row = (
            check_db.query(AuditLog)
            .filter(
                AuditLog.user_id == citizen["user"].id,
                AuditLog.action == "REFRESH_TOKEN_REUSE_DETECTED",
            )
            .first()
        )
        assert audit_row is not None
        assert "concurrent_cas_race" in (audit_row.details or "")
    finally:
        check_db.close()


@pytest.mark.skipif(
    not os.getenv("POSTGIS_TEST_DATABASE_URL"),
    reason="BLOCKED: Live PostgreSQL server not configured via POSTGIS_TEST_DATABASE_URL for concurrency test",
)
def test_live_postgres_concurrent_refresh_cas_race():
    """
    Genuine PostgreSQL concurrency test using threading.Barrier to force two concurrent
    /auth/refresh calls across the read->CAS boundary simultaneously.
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from fastapi.testclient import TestClient
    from alembic import command
    from alembic.config import Config
    from app.core.security import get_password_hash
    from app.db.session import get_db
    from app.main import app
    from app.models.entities import CitizenProfile, NotificationPreference

    url = os.environ["POSTGIS_TEST_DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    pg_engine = create_engine(url, pool_pre_ping=True)
    PgSession = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    db = PgSession()
    try:
        cit = User(
            email="pg.concurrent.test@example.com",
            full_name="PG Concurrency User",
            hashed_password=get_password_hash("StrongPgTestPass123!"),
            role=UserRole.CITIZEN.value,
            is_active=True,
            is_verified=True,
        )
        db.add(cit)
        db.flush()
        db.add(CitizenProfile(user_id=cit.id))
        db.add(NotificationPreference(user_id=cit.id))
        db.commit()
    finally:
        db.close()

    def _pg_db():
        s = PgSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _pg_db
    barrier = threading.Barrier(2, timeout=10)
    orig_update = Query.update

    def synced_update(self, values, synchronize_session="evaluate", update_args=None):
        entity = self.column_descriptions[0].get("entity") if self.column_descriptions else None
        if entity is RefreshToken and RefreshToken.replaced_by_jti in values:
            barrier.wait()
        return orig_update(self, values, synchronize_session=synchronize_session, update_args=update_args)

    Query.update = synced_update
    try:
        pg_client = TestClient(app)
        login_res = pg_client.post(
            "/api/v1/auth/login",
            json={"email": "pg.concurrent.test@example.com", "password": "StrongPgTestPass123!"},
        ).json()
        rt = login_res["refresh_token"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            r1 = pool.submit(pg_client.post, "/api/v1/auth/refresh", json={"refresh_token": rt}).result()
            r2 = pool.submit(pg_client.post, "/api/v1/auth/refresh", json={"refresh_token": rt}).result()

        assert sorted([r1.status_code, r2.status_code]) == [200, 401]
        winner = r1 if r1.status_code == 200 else r2
        assert pg_client.post("/api/v1/auth/refresh", json={"refresh_token": winner.json()["refresh_token"]}).status_code == 401
    finally:
        Query.update = orig_update
        app.dependency_overrides.clear()
        pg_engine.dispose()


# ---------------------------------------------------------------------------
# Render & CLI Bootstrap Fail-Closed & Idempotency Tests
# ---------------------------------------------------------------------------

def test_bootstrap_admin_fail_closed_and_render_startup(db_session_factory, monkeypatch, capsys, tmp_path):
    """
    1. Missing / invalid email or weak password fails on fresh DB (ValueError).
    2. Email collision with non-admin raises ValueError (no silent exit 0).
    3. Valid creation creates single active GOVERNMENT_ADMIN (no secrets logged).
    4. Repeat call with existing active admin succeeds idempotently even WITHOUT password/email.
    5. Database failure raises cleanly (exit non-zero via CLI).
    6. render.yaml startCommand runs `python bootstrap.py` without `|| true`.
    """
    import bootstrap

    # Missing config -> fail
    with pytest.raises(ValueError):
        bootstrap.bootstrap_admin(email="", password="StrongPassword123!", full_name="Admin")
    with pytest.raises(ValueError):
        bootstrap.bootstrap_admin(email="not-an-email", password="StrongPassword123!", full_name="Admin")
    with pytest.raises(ValueError):
        bootstrap.bootstrap_admin(email="admin@civicfix.gov", password="password123", full_name="Admin")

    # Existing non-admin collision -> fail closed
    s = db_session_factory()
    try:
        from app.core.security import get_password_hash
        citizen = User(
            email="existing.citizen@civicfix.gov",
            full_name="Existing Citizen",
            hashed_password=get_password_hash("CitizenPass123!"),
            role=UserRole.CITIZEN.value,
            is_active=True,
            is_verified=True,
        )
        s.add(citizen)
        s.commit()
    finally:
        s.close()

    with pytest.raises(ValueError, match="already exists with role 'CITIZEN'"):
        bootstrap.bootstrap_admin(
            email="existing.citizen@civicfix.gov",
            password="UniqueStrongPassword99!",
            full_name="Commissioner",
        )

    # Valid creation -> single active admin, secret never printed
    admin_secret = "ValidAdminBootstrap99!"
    created = bootstrap.bootstrap_admin(
        email="commissioner@civicfix.gov",
        password=admin_secret,
        full_name="Municipal Commissioner",
    )
    assert created.role == UserRole.GOVERNMENT_ADMIN.value
    assert created.is_active is True
    out = capsys.readouterr().out
    assert admin_secret not in out

    # Repeat startup WITHOUT credentials succeeds idempotently because active admin exists
    preserved = bootstrap.bootstrap_admin(email="", password="", full_name="")
    assert preserved.id == created.id

    # CLI exit codes: missing credentials on fresh temp DB -> exit 1; repeated on populated DB -> exit 0
    fresh_db = tmp_path / "cli_bootstrap_test.db"
    backend_dir = Path(__file__).resolve().parent.parent
    env_base = os.environ.copy()
    env_base["DATABASE_URL"] = f"sqlite:///{fresh_db.as_posix()}"
    env_base["ENVIRONMENT"] = "testing"
    env_base["SECRET_KEY"] = "cli-bootstrap-test-secret-key-min-32-chars"

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend_dir, env=env_base, check=True)

    env_missing = dict(env_base)
    env_missing.pop("INITIAL_ADMIN_EMAIL", None)
    env_missing.pop("INITIAL_ADMIN_PASSWORD", None)
    res_fail = subprocess.run([sys.executable, "bootstrap.py"], cwd=backend_dir, env=env_missing, capture_output=True, text=True)
    assert res_fail.returncode != 0

    env_valid = dict(env_base)
    env_valid["INITIAL_ADMIN_EMAIL"] = "boot.admin@civicfix.gov"
    env_valid["INITIAL_ADMIN_PASSWORD"] = "BootAdminSecret99!"
    res_ok = subprocess.run([sys.executable, "bootstrap.py"], cwd=backend_dir, env=env_valid, capture_output=True, text=True)
    assert res_ok.returncode == 0
    assert "BootAdminSecret99!" not in res_ok.stdout
    assert "BootAdminSecret99!" not in res_ok.stderr

    # Repeat CLI run WITHOUT credentials succeeds cleanly because admin exists
    res_repeat = subprocess.run([sys.executable, "bootstrap.py"], cwd=backend_dir, env=env_missing, capture_output=True, text=True)
    assert res_repeat.returncode == 0

    # Database failure -> nonzero exit
    env_bad_db = dict(env_base)
    env_bad_db["DATABASE_URL"] = "sqlite:///Z:/nonexistent_dir_12345/missing.db"
    env_bad_db["INITIAL_ADMIN_EMAIL"] = "boot.admin@civicfix.gov"
    env_bad_db["INITIAL_ADMIN_PASSWORD"] = "BootAdminSecret99!"
    res_db_fail = subprocess.run([sys.executable, "bootstrap.py"], cwd=backend_dir, env=env_bad_db, capture_output=True, text=True)
    assert res_db_fail.returncode != 0

    # Render startup contract verification: no `|| true`, bootstrap required after migrate
    render_yaml = (backend_dir.parent / "render.yaml").read_text(encoding="utf-8")
    assert "python migrate.py && python bootstrap.py && uvicorn app.main:app" in render_yaml
    assert "bootstrap.py || true" not in render_yaml
    assert "|| true" not in render_yaml
