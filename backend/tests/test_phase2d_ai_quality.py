import asyncio
import io
import json

from PIL import Image

from app.core.limiter import limiter
from app.models.entities import (
    AIAnalysis,
    AIFeedback,
    AuditLog,
    Complaint,
    ComplaintAttachment,
    ResolutionComparison,
)
from app.models.enums import ComplaintCategory, ComplaintStatus
from app.services.ai.base import ImageAnalysisResult, TextAnalysisResult
from app.services.ai.service import ai_service
from app.services.storage.backends import compute_sha256_hex
from app.services.storage.service import storage_service


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_png(color=(25, 25, 25), size=(32, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def test_cross_modal_mismatch_preserves_complaint_and_flags_review(
    db_session, db_session_factory, test_actors, monkeypatch
):
    c_a = test_actors["citizen_a"]["user"]
    img_bytes = _make_png(color=(180, 40, 40))
    storage_service.ensure_local_directories()
    img_path = storage_service.complaint_dir / "garbage_pile_mismatch.png"
    img_path.write_bytes(img_bytes)

    comp = Complaint(
        reference_number="CF-2026-XMODAL1",
        citizen_id=c_a.id,
        title="Broken streetlight at park gate",
        description="Lamp pole is dark near south entrance.",
        category=ComplaintCategory.STREETLIGHTS.value,
        latitude=17.44,
        longitude=78.49,
        status=ComplaintStatus.AI_ANALYSIS_PENDING.value,
        ai_processing_status="PENDING",
    )
    db_session.add(comp)
    db_session.flush()
    att = ComplaintAttachment(
        complaint_id=comp.id,
        file_name="garbage_pile_mismatch.png",
        file_path="/uploads/complaints/garbage_pile_mismatch.png",
        file_size=len(img_bytes),
        mime_type="image/png",
        attachment_type="CITIZEN_ORIGINAL",
        uploaded_by_id=c_a.id,
        storage_provider="local",
        storage_object_key="complaints/garbage_pile_mismatch.png",
        sha256_checksum=compute_sha256_hex(img_bytes),
        storage_verification_status="VERIFIED",
    )
    db_session.add(att)
    db_session.commit()
    cid = comp.id

    asyncio.run(ai_service.process_complaint_by_id(cid, session_factory=db_session_factory))

    db_session.expire_all()
    refreshed = db_session.query(Complaint).filter(Complaint.id == cid).first()
    # Must NOT auto-reject on AI disagreement; moves cleanly to human review
    assert refreshed.status == ComplaintStatus.UNDER_REVIEW.value
    assert refreshed.ai_analysis is not None
    assert refreshed.ai_analysis.suggested_category == "STREETLIGHTS"
    assert refreshed.ai_analysis.image_suggested_category == "GARBAGE"
    assert refreshed.ai_analysis.cross_modal_mismatch is True
    assert "human verification" in (refreshed.ai_analysis.cross_modal_explanation or "").lower()
    assert refreshed.ai_analysis.recommended_action == "REQUIRE_VERIFICATION"


def test_confidence_aware_advisory_routing_tiers(
    db_session, db_session_factory, test_actors, monkeypatch
):
    c_a = test_actors["citizen_a"]["user"]
    low_comp = Complaint(
        reference_number="CF-2026-LOWCONF1",
        citizen_id=c_a.id,
        title="Unclear report issue",
        description="Something looks wrong outside my block maybe.",
        category=ComplaintCategory.OTHER.value,
        latitude=17.44,
        longitude=78.49,
        status=ComplaintStatus.AI_ANALYSIS_PENDING.value,
        ai_processing_status="PENDING",
    )
    db_session.add(low_comp)
    db_session.commit()
    cid = low_comp.id

    async def _low_conf_text(*args, **kwargs):
        return TextAnalysisResult(
            suggested_category=ComplaintCategory.OTHER,
            suggested_subcategory="Ambiguous Report",
            safety_hazard_detected=False,
            urgency_level="MEDIUM",
            confidence_score=0.41,
            summary_explanation="Insufficient detail for automated department routing.",
            extracted_keywords=["unclear"],
        )

    with monkeypatch.context() as mp:
        mp.setattr(ai_service.mock_provider, "analyze_text", _low_conf_text)
        asyncio.run(ai_service.process_complaint_by_id(cid, session_factory=db_session_factory))

    db_session.expire_all()
    updated = db_session.query(Complaint).filter(Complaint.id == cid).first()
    assert updated.status == ComplaintStatus.UNDER_REVIEW.value
    assert updated.department_id is None  # Low confidence holds auto-routing
    assert updated.ai_analysis.routing_tier == "LOW_CONFIDENCE"
    assert updated.ai_analysis.recommended_action == "REQUEST_CLARIFICATION_HOLD"


def test_ai_feedback_override_evaluation_endpoint_and_before_after_comparison(
    client, test_actors, db_session, db_session_factory
):
    c_a = test_actors["citizen_a"]
    adm = test_actors["admin"]
    staff_roads = test_actors["staff_roads"]
    lighting_dept = test_actors["departments"]["LIGHTING"]

    t_ca = _login(client, c_a["email"], c_a["password"])["access_token"]
    t_adm = _login(client, adm["email"], adm["password"])["access_token"]
    t_roads = _login(client, staff_roads["email"], staff_roads["password"])["access_token"]

    # Create a ROADS complaint with before & after images
    comp_resp = client.post("/api/v1/complaints", json={
        "title": "Deep asphalt pothole outside bus stop",
        "description": "Large pothole on asphalt carriageway posing hazard.",
        "category": "ROADS",
        "latitude": 17.441,
        "longitude": 78.491,
    }, headers=_headers(t_ca))
    assert comp_resp.status_code == 201
    cid = comp_resp.json()["id"]

    # Upload BEFORE and AFTER photographs (different brightness/colors to ensure deterministic diff)
    before_bytes = _make_png(color=(20, 20, 20))
    after_bytes = _make_png(color=(230, 230, 230))
    b_att = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("before_pothole.png", before_bytes, "image/png")},
        data={"attachment_type": "CITIZEN_ORIGINAL"},
        headers=_headers(t_ca),
    ).json()
    a_att = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("after_resolution.png", after_bytes, "image/png")},
        data={"attachment_type": "RESOLUTION_EVIDENCE"},
        headers=_headers(t_adm),
    ).json()

    # Non-admin staff blocked from /ai/evaluation (admin-only governance)
    assert client.get("/api/v1/admin/ai/evaluation", headers=_headers(t_roads)).status_code == 403

    # Staff applies structured AI override across category, priority, department, and image assessment
    ov_resp = client.post(
        f"/api/v1/admin/complaints/{cid}/review-ai",
        json={
            "category": "STREETLIGHTS",
            "priority": "P1",
            "department_id": lighting_dept.id,
            "image_assessment_override": "Pole wiring also exposed beneath damaged pavement curb.",
            "override_reason": "Field officer confirmed underground electrical conduit damage.",
        },
        headers=_headers(t_adm),
    )
    assert ov_resp.status_code == 200, ov_resp.text
    ov_data = ov_resp.json()
    assert ov_data["category"] == "STREETLIGHTS"
    assert ov_data["priority"] == "P1"
    assert ov_data["department_id"] == lighting_dept.id
    assert ov_data["ai_analysis"]["is_overridden"] is True

    fb_row = db_session.query(AIFeedback).filter(AIFeedback.complaint_id == cid).first()
    assert fb_row is not None
    assert fb_row.original_category == "ROADS"
    assert fb_row.corrected_category == "STREETLIGHTS"
    assert fb_row.corrected_department_id == lighting_dept.id
    assert "electrical conduit" in fb_row.reason

    # Before/After comparison runs advisory assessment without auto-approving repair
    cmp_resp = client.post(
        f"/api/v1/admin/complaints/{cid}/compare-evidence",
        json={"before_attachment_id": b_att["id"], "after_attachment_id": a_att["id"]},
        headers=_headers(t_adm),
    )
    assert cmp_resp.status_code == 200, cmp_resp.text
    cmp_data = cmp_resp.json()
    assert cmp_data["changes_detected"] is True
    assert cmp_data["requires_human_review"] is True
    assert len(json.loads(cmp_data["visual_differences_json"])) >= 2

    db_session.expire_all()
    comp_after_cmp = db_session.query(Complaint).filter(Complaint.id == cid).first()
    assert comp_after_cmp.status != ComplaintStatus.RESOLVED.value

    # Admin AI evaluation summary reflects override metrics & feedback without labelling as accuracy
    eval_resp = client.get("/api/v1/admin/ai/evaluation", headers=_headers(t_adm))
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["total_analyzed"] >= 1
    assert eval_data["staff_override_count"] == 1
    assert eval_data["staff_override_rate_percent"] > 0
    assert "not a labelled" in eval_data["evaluation_note"].lower()
    assert len(eval_data["recent_feedback"]) == 1
