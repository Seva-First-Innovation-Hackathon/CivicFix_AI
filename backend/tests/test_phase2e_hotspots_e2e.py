import asyncio
import io
from datetime import datetime, timedelta, timezone

from PIL import Image

from app.models.entities import AuditLog, BackgroundJob, Complaint, SLABreachEvent
from app.models.enums import ComplaintStatus
from app.services.ai.service import ai_service
from app.services.jobs.queue import execute_job_by_id
from app.services.sla.monitor import monitor_sla_deadlines
from app.services.storage.backends import S3CompatibleStorageBackend
from app.services.storage.service import storage_service
from tests.test_phase2a_storage import FakeS3Client


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_png(color=(15, 25, 35)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), color=color).save(buf, format="PNG")
    return buf.getvalue()


def test_hotspots_aggregation_filters_rbac_and_zero_pii(client, test_actors, db_session):
    adm = test_actors["admin"]
    roads = test_actors["staff_roads"]
    lighting = test_actors["staff_lighting"]
    crew_a = test_actors["crew_a"]
    c_a = test_actors["citizen_a"]["user"]

    roads_dept = test_actors["departments"]["ROADS"]
    lighting_dept = test_actors["departments"]["LIGHTING"]
    now = datetime.now(timezone.utc)

    c1 = Complaint(
        reference_number="CF-2026-HS01",
        citizen_id=c_a.id,
        title="Private Citizen Address 42 Secret St",
        description="Should NEVER leak in aggregate hotspots response.",
        category="ROADS",
        latitude=17.4400,
        longitude=78.4900,
        status=ComplaintStatus.IN_PROGRESS.value,
        priority="P1",
        department_id=roads_dept.id,
        assigned_crew_id=crew_a["user"].id,
        sla_deadline=now - timedelta(hours=3),
    )
    c2 = Complaint(
        reference_number="CF-2026-HS02",
        citizen_id=c_a.id,
        title="Second nearby road defect",
        description="Nearby cluster point.",
        category="ROADS",
        latitude=17.4404,
        longitude=78.4904,
        status=ComplaintStatus.UNDER_REVIEW.value,
        priority="P2",
        department_id=roads_dept.id,
    )
    c3 = Complaint(
        reference_number="CF-2026-HS03",
        citizen_id=c_a.id,
        title="Separate ward streetlight out",
        description="Distant cluster for lighting.",
        category="STREETLIGHTS",
        latitude=17.5000,
        longitude=78.5500,
        status=ComplaintStatus.UNDER_REVIEW.value,
        priority="P3",
        department_id=lighting_dept.id,
    )
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    t_adm = _login(client, adm["email"], adm["password"])["access_token"]
    t_roads = _login(client, roads["email"], roads["password"])["access_token"]
    t_light = _login(client, lighting["email"], lighting["password"])["access_token"]
    t_crew_a = _login(client, crew_a["email"], crew_a["password"])["access_token"]

    # Admin global hotspots + correlation header
    res_adm = client.get("/api/v1/admin/analytics/hotspots?grid_size_meters=500", headers=_headers(t_adm))
    assert res_adm.status_code == 200
    assert "X-Request-ID" in res_adm.headers
    payload = res_adm.json()
    assert payload["total_complaints_matched"] == 3
    assert len(payload["hotspots"]) == 2
    top_bucket = payload["hotspots"][0]
    assert top_bucket["complaint_count"] == 2
    assert top_bucket["p1_count"] == 1
    assert top_bucket["overdue_count"] == 1
    assert top_bucket["dominant_category"] == "ROADS"

    # Zero PII leaked anywhere in serialized hotspots
    serialized = str(payload)
    assert "Secret St" not in serialized
    assert c_a.id not in serialized
    assert "CF-2026-HS01" not in serialized

    # Filters: category + priority + overdue_only
    res_p1 = client.get("/api/v1/admin/analytics/hotspots?priority=P1&overdue_only=true", headers=_headers(t_adm))
    assert res_p1.status_code == 200
    assert res_p1.json()["total_complaints_matched"] == 1

    # Department RBAC: lighting member cannot query ROADS department_id
    assert (
        client.get(
            f"/api/v1/admin/analytics/hotspots?department_id={roads_dept.id}",
            headers=_headers(t_light),
        ).status_code
        == 403
    )

    # Scoped roads officer sees only roads complaints (2)
    res_roads = client.get("/api/v1/admin/analytics/hotspots", headers=_headers(t_roads))
    assert res_roads.status_code == 200
    assert res_roads.json()["total_complaints_matched"] == 2

    # Field crew sees only assigned complaint (1)
    res_crew = client.get("/api/v1/admin/analytics/hotspots", headers=_headers(t_crew_a))
    assert res_crew.status_code == 200
    assert res_crew.json()["total_complaints_matched"] == 1


def test_phase2_full_end_to_end_lifecycle_r2_outbox_comparison_sla_and_audit(
    client, test_actors, db_session, db_session_factory, monkeypatch
):
    """
    Executes the full 12-step Section 11 End-to-End Phase 2 verification flow:
    1. Citizen creates complaint
    2. Complaint persisted with WKT/PostGIS location + outbox AI job
    3. Citizen uploads before photo into durable private R2 backend
    4. Durable outbox AI triage job runs cleanly via worker executor
    5. Municipal staff inspects & verifies ticket
    6. Staff dispatches work order to Field Crew
    7. Crew accepts & submits after-repair evidence (stored on R2)
    8. Before/After evidence AI comparison runs cleanly without auto-approving
    9. Municipal staff approves resolution evidence
    10. Citizen confirms repair (RESOLVED)
    11. SLA monitoring records overdue cases without duplicating
    12. Complete audit history preserved
    """
    fake_s3 = FakeS3Client()
    r2_backend = S3CompatibleStorageBackend(
        bucket_name="civicfix-e2e-bucket",
        access_key_id="k",
        secret_access_key="s",
        endpoint_url="https://acct.r2.cloudflarestorage.com",
        provider_name="r2",
        client=fake_s3,
    )
    monkeypatch.setattr("app.services.storage.service.settings.STORAGE_BACKEND", "r2")
    monkeypatch.setattr(storage_service, "_cloud_backend", r2_backend)
    monkeypatch.setattr("app.services.jobs.queue.settings.QUEUE_BACKEND", "redis")

    fake_pool_jobs = []

    class _Pool:
        async def enqueue_job(self, func_name, *args, _job_id=None, _defer_until=None):
            fake_pool_jobs.append((func_name, args, _job_id))
            return type("J", (), {"job_id": _job_id})()

    async def _pool():
        return _Pool()

    monkeypatch.setattr("app.services.jobs.queue._get_arq_pool", _pool)

    c_a = test_actors["citizen_a"]
    roads = test_actors["staff_roads"]
    crew_a = test_actors["crew_a"]
    adm = test_actors["admin"]

    t_cit = _login(client, c_a["email"], c_a["password"])["access_token"]
    t_roads = _login(client, roads["email"], roads["password"])["access_token"]
    t_crew = _login(client, crew_a["email"], crew_a["password"])["access_token"]
    t_adm = _login(client, adm["email"], adm["password"])["access_token"]

    # 1-2. Citizen creates complaint
    create_resp = client.post("/api/v1/complaints", json={
        "title": "Deep pothole outside East Transit Plaza",
        "description": "Large asphalt crater causing traffic swerving at bus bay.",
        "category": "ROADS",
        "latitude": 17.4415,
        "longitude": 78.4915,
    }, headers=_headers(t_cit))
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]
    assert create_resp.json()["ai_processing_status"] == "PENDING"
    assert len(fake_pool_jobs) == 2

    # 3. Upload citizen photo to private R2
    before_att = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("before_pothole.png", _make_png((15, 15, 15)), "image/png")},
        data={"attachment_type": "CITIZEN_ORIGINAL"},
        headers=_headers(t_cit),
    )
    assert before_att.status_code == 200
    assert before_att.json()["storage_provider"] == "r2"

    # 4. Run queued AI triage job via outbox executor
    ai_job = db_session.query(BackgroundJob).filter(
        BackgroundJob.complaint_id == cid,
        BackgroundJob.job_type == "ai_triage",
    ).first()
    assert ai_job is not None and ai_job.status == "QUEUED"
    res = asyncio.run(execute_job_by_id(ai_job.id, session_factory=db_session_factory))
    assert res["outcome"] == "succeeded"

    comp_detail = client.get(f"/api/v1/complaints/{cid}", headers=_headers(t_roads)).json()
    assert comp_detail["status"] == "UNDER_REVIEW"
    assert comp_detail["ai_processing_status"] == "COMPLETED"
    assert comp_detail["ai_analysis"] is not None

    # 5-6. Verify & dispatch work order to Field Crew A
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/verify",
        json={"priority": "P2", "verification_notes": "Confirmed deep road defect."},
        headers=_headers(t_roads),
    ).status_code == 200

    wo_resp = client.post("/api/v1/admin/work-orders", json={
        "complaint_id": cid,
        "department_id": test_actors["departments"]["ROADS"].id,
        "crew_id": crew_a["user"].id,
        "title": "Resurface transit bay pothole",
        "instructions": "Compact base and seal asphalt.",
    }, headers=_headers(t_roads))
    assert wo_resp.status_code == 201
    wo_id = wo_resp.json()["id"]

    # 7. Crew accepts work order & uploads AFTER photo to R2 & submits evidence
    assert client.post(f"/api/v1/admin/work-orders/{wo_id}/accept", headers=_headers(t_crew)).status_code == 200
    after_att = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("after_resolution.png", _make_png((240, 240, 240)), "image/png")},
        data={"attachment_type": "AFTER_REPAIR"},
        headers=_headers(t_crew),
    )
    assert after_att.status_code == 200 and after_att.json()["storage_provider"] == "r2"

    assert client.post(
        f"/api/v1/admin/work-orders/{wo_id}/submit-evidence",
        json={"completion_notes": "Pavement resurfaced and compacted to flush grade."},
        headers=_headers(t_crew),
    ).status_code == 200

    # 8. AI Before/After comparison succeeds cleanly across R2 bytes & preserves human approval gate
    cmp_resp = client.post(
        f"/api/v1/admin/complaints/{cid}/compare-evidence",
        json={"before_attachment_id": before_att.json()["id"], "after_attachment_id": after_att.json()["id"]},
        headers=_headers(t_roads),
    )
    assert cmp_resp.status_code == 200
    assert cmp_resp.json()["changes_detected"] is True
    assert cmp_resp.json()["requires_human_review"] is True

    # 9-10. Staff approves evidence -> Citizen confirms repair -> RESOLVED
    assert client.post(
        f"/api/v1/admin/complaints/{cid}/review-evidence",
        json={"is_approved": True, "notes": "Visual repair verified cleanly."},
        headers=_headers(t_roads),
    ).status_code == 200

    confirm_resp = client.post(
        f"/api/v1/complaints/{cid}/confirm-resolution",
        json={"is_satisfied": True, "feedback_rating": 5, "feedback_notes": "Clean asphalt patch."},
        headers=_headers(t_cit),
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "RESOLVED"

    # 11. SLA breach monitoring records separate open overdue ticket cleanly
    overdue_open = Complaint(
        reference_number="CF-2026-E2ESLA",
        citizen_id=c_a["user"].id,
        title="Overdue drainage grating missing",
        description="Past SLA open issue.",
        category="DRAINAGE",
        latitude=17.445,
        longitude=78.495,
        status=ComplaintStatus.UNDER_REVIEW.value,
        priority="P1",
        department_id=test_actors["departments"]["ROADS"].id,
        sla_deadline=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(overdue_open)
    db_session.commit()
    sla_sum = monitor_sla_deadlines(db=db_session)
    assert sla_sum["new_breaches_recorded"] == 1

    # 12. Audit trail preserves complete chain
    audit_logs = client.get("/api/v1/admin/audit-logs", headers=_headers(t_adm)).json()
    actions = {a["action"] for a in audit_logs}
    assert {
        "COMPLAINT_CREATED",
        "ATTACHMENT_UPLOADED",
        "WORK_ORDER_CREATED",
        "EVIDENCE_BEFORE_AFTER_COMPARED",
        "RESOLUTION_CONFIRMED_BY_CITIZEN",
        "SLA_BREACH_DETECTED",
    }.issubset(actions)
