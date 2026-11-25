import asyncio
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Callable
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

import app.db.session as db_session
from app.core.config import settings
from app.models.entities import (
    Complaint, AIAnalysis, PotentialDuplicate, MunicipalDepartment,
    ComplaintStatusHistory, Notification
)
from app.models.enums import ComplaintCategory, PriorityLevel, ComplaintStatus, NotificationType
from app.services.ai.base import BaseAIProvider
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.gemini_provider import GeminiAIProvider, AIServiceUnavailableError
from app.services.ai.duplicate_detector import find_potential_duplicates_from_db
from app.services.audit import log_audit
from app.services.notifications.service import send_notification

logger = logging.getLogger(__name__)

_SECRET_PATTERN = re.compile(r"(AIza[0-9A-Za-z\-_]{10,}|key=[^\s&]+|Bearer\s+[A-Za-z0-9\.\-_]+)", re.IGNORECASE)

INITIAL_TRIAGE_STATUSES = {
    ComplaintStatus.SUBMITTED.value,
    ComplaintStatus.AI_ANALYSIS_PENDING.value,
}


def sanitize_ai_error(exc: Exception) -> str:
    """Produces a bounded, credential-free error summary suitable for DB persistence and logs."""
    msg = f"{type(exc).__name__}: {str(exc)}"
    msg = _SECRET_PATTERN.sub("[REDACTED]", msg)
    msg = " ".join(msg.split())
    return msg[:220]


class AIService:
    def __init__(self):
        self.mock_provider = MockAIProvider()
        self.gemini_provider = GeminiAIProvider()

    def get_provider(self) -> Tuple[BaseAIProvider, str, str]:
        """
        Dynamically returns (provider_instance, provider_identifier, model_name).
        Honest reporting: if 'gemini' is requested without GOOGLE_API_KEY, uses deterministic
        MockAIProvider fallback while recording 'mock_fallback_gemini_unconfigured'.
        """
        if settings.AI_PROVIDER.lower() == "gemini":
            if self.gemini_provider.is_configured():
                return self.gemini_provider, "gemini", self.gemini_provider.model_name
            logger.warning(
                "[AI SERVICE] AI_PROVIDER is 'gemini' but GOOGLE_API_KEY is not configured. "
                "Operating with deterministic MockAIProvider fallback."
            )
            return self.mock_provider, "mock_fallback_gemini_unconfigured", "civicfix-deterministic-nlp-v1"

        return self.mock_provider, "mock", "civicfix-deterministic-nlp-v1"

    @staticmethod
    def _stale_cutoff() -> datetime:
        stale_seconds = max(300, (settings.AI_REQUEST_TIMEOUT_SECONDS or 30) * 3)
        return datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)

    def try_claim_processing(self, db: Session, complaint_id: str, force: bool = False) -> bool:
        """
        Atomically claims exclusive AI processing ownership in the database to prevent
        duplicate concurrent execution for the same complaint.
        """
        now = datetime.now(timezone.utc)
        stale_cutoff = self._stale_cutoff()

        eligible_statuses = ["PENDING", "FAILED"]
        if force:
            eligible_statuses.append("COMPLETED")

        updated_rows = (
            db.query(Complaint)
            .filter(
                Complaint.id == complaint_id,
                or_(
                    Complaint.ai_processing_status.in_(eligible_statuses),
                    and_(
                        Complaint.ai_processing_status == "PROCESSING",
                        Complaint.ai_processing_started_at < stale_cutoff,
                    ),
                ),
            )
            .update(
                {
                    Complaint.ai_processing_status: "PROCESSING",
                    Complaint.ai_processing_started_at: now,
                    Complaint.ai_processing_attempts: Complaint.ai_processing_attempts + 1,
                    Complaint.ai_processing_error: None,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return updated_rows == 1

    async def _run_inference_and_persist(self, db: Session, complaint: Complaint) -> AIAnalysis:
        provider, provider_name, model_name = self.get_provider()
        timeout_sec = max(1, settings.AI_REQUEST_TIMEOUT_SECONDS or 30)

        # Capture previous status BEFORE any modification (prevents UNDER_REVIEW -> UNDER_REVIEW bug)
        previous_status = complaint.status

        # 1. Text Analysis with bounded timeout
        text_result = await asyncio.wait_for(
            provider.analyze_text(title=complaint.title, description=complaint.description),
            timeout=timeout_sec,
        )

        # 2. Vision Analysis if attachments exist (reads bytes transparently across local / R2 / S3)
        image_result = None
        if complaint.attachments:
            first_img = complaint.attachments[0]
            try:
                from app.services.storage.service import storage_service
                img_bytes = storage_service.read_bytes(
                    file_path=first_img.file_path,
                    storage_provider=getattr(first_img, "storage_provider", "local"),
                    storage_object_key=getattr(first_img, "storage_object_key", None),
                )
            except Exception as img_read_exc:
                logger.warning(
                    "Unable to load attachment %s for complaint %s vision analysis: %s",
                    first_img.id,
                    complaint.id,
                    sanitize_ai_error(img_read_exc),
                )
                img_bytes = None

            image_result = await asyncio.wait_for(
                provider.analyze_image(first_img.file_path, image_bytes=img_bytes),
                timeout=timeout_sec,
            )

        # 3. Priority Recommendation & Cross-Modal Consistency Check
        prio_rec = provider.recommend_priority(
            category=text_result.suggested_category,
            text_result=text_result,
            image_result=image_result,
        )

        image_suggested_cat = (
            image_result.suggested_category.value
            if image_result and getattr(image_result, "suggested_category", None) is not None
            else None
        )
        cross_modal_mismatch = bool(
            image_result
            and not image_result.is_inconclusive
            and getattr(image_result, "suggested_category", None) is not None
            and image_result.suggested_category != ComplaintCategory.OTHER
            and image_result.suggested_category != text_result.suggested_category
        )
        cross_modal_explanation = None
        if cross_modal_mismatch and image_result and image_result.suggested_category:
            cross_modal_explanation = (
                f"Text triage indicates {text_result.suggested_category.value} while uploaded image suggests "
                f"{image_result.suggested_category.value}. Flagged for municipal human verification."
            )

        # Confidence-aware advisory routing (never bypasses human approval workflow)
        effective_confidence = float(text_result.confidence_score)
        if cross_modal_mismatch:
            routing_tier = "MEDIUM_CONFIDENCE"
            recommended_action = "REQUIRE_VERIFICATION"
        elif effective_confidence >= settings.AI_HIGH_CONFIDENCE_THRESHOLD:
            routing_tier = "HIGH_CONFIDENCE"
            recommended_action = "SUGGEST_DEPARTMENT"
        elif effective_confidence >= settings.AI_MEDIUM_CONFIDENCE_THRESHOLD:
            routing_tier = "MEDIUM_CONFIDENCE"
            recommended_action = "REQUIRE_VERIFICATION"
        else:
            routing_tier = "LOW_CONFIDENCE"
            recommended_action = "REQUEST_CLARIFICATION_HOLD"

        # 4. Department Routing (advisory)
        category_dept_map = {
            ComplaintCategory.ROADS: "ROADS",
            ComplaintCategory.STREETLIGHTS: "LIGHTING",
            ComplaintCategory.GARBAGE: "SANITATION",
            ComplaintCategory.DRAINAGE: "DRAINAGE",
            ComplaintCategory.WATER_SUPPLY: "WATER",
            ComplaintCategory.FOOTPATHS: "ROADS",
            ComplaintCategory.TREES_HAZARDS: "PARKS",
            ComplaintCategory.SANITATION: "SANITATION",
            ComplaintCategory.OTHER: "ROADS",
        }
        dept_code = category_dept_map.get(text_result.suggested_category, "ROADS")
        dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.code == dept_code).first()

        # 5. SLA Deadline
        sla_hours = {
            PriorityLevel.P1: settings.SLA_HOURS_P1,
            PriorityLevel.P2: settings.SLA_HOURS_P2,
            PriorityLevel.P3: settings.SLA_HOURS_P3,
            PriorityLevel.P4: settings.SLA_HOURS_P4,
        }.get(prio_rec.priority, 72)
        sla_deadline = datetime.now(timezone.utc) + timedelta(hours=sla_hours)

        visual_findings_json = None
        if image_result:
            visual_findings_json = json.dumps({
                "damage_detected": image_result.damage_detected,
                "damage_type": image_result.damage_type,
                "severity": image_result.damage_severity,
                "observations": image_result.observations,
                "is_inconclusive": getattr(image_result, "is_inconclusive", False),
                "suggested_category": image_suggested_cat,
            })

        ai_record = db.query(AIAnalysis).filter(AIAnalysis.complaint_id == complaint.id).first()
        if not ai_record:
            ai_record = AIAnalysis(complaint_id=complaint.id)
            db.add(ai_record)

        ai_record.provider = provider_name
        ai_record.model_name = model_name
        ai_record.suggested_category = text_result.suggested_category.value
        ai_record.suggested_subcategory = text_result.suggested_subcategory
        ai_record.suggested_priority = prio_rec.priority.value
        ai_record.confidence_score = effective_confidence
        ai_record.safety_hazard_detected = text_result.safety_hazard_detected
        ai_record.urgency_level = text_result.urgency_level
        ai_record.summary_explanation = (
            f"{text_result.summary_explanation} Priority Rationale: {prio_rec.rationale}"
            + (f" [{cross_modal_explanation}]" if cross_modal_explanation else "")
        )
        ai_record.visual_findings = visual_findings_json
        ai_record.image_suggested_category = image_suggested_cat
        ai_record.cross_modal_mismatch = cross_modal_mismatch
        ai_record.cross_modal_explanation = cross_modal_explanation
        ai_record.routing_tier = routing_tier
        ai_record.recommended_action = recommended_action
        ai_record.suggested_department_id = dept.id if dept else None
        ai_record.duplicate_checked = True

        # Apply advisory priority/department suggestion only when not manually overridden and confident without mismatch
        if not ai_record.is_overridden:
            complaint.priority = prio_rec.priority.value
            if dept and not complaint.department_id and recommended_action != "REQUEST_CLARIFICATION_HOLD":
                complaint.department_id = dept.id
            if not complaint.sla_deadline:
                complaint.sla_deadline = sla_deadline

        complaint.ai_processing_status = "COMPLETED"
        complaint.ai_processing_error = None
        complaint.ai_processing_completed_at = datetime.now(timezone.utc)

        # Transition from SUBMITTED / AI_ANALYSIS_PENDING -> UNDER_REVIEW accurately & idempotently
        if previous_status in INITIAL_TRIAGE_STATUSES:
            complaint.status = ComplaintStatus.UNDER_REVIEW.value
            existing_history = (
                db.query(ComplaintStatusHistory)
                .filter(
                    ComplaintStatusHistory.complaint_id == complaint.id,
                    ComplaintStatusHistory.from_status == previous_status,
                    ComplaintStatusHistory.to_status == ComplaintStatus.UNDER_REVIEW.value,
                    ComplaintStatusHistory.changed_by_id.is_(None),
                )
                .first()
            )
            if not existing_history:
                db.add(ComplaintStatusHistory(
                    complaint_id=complaint.id,
                    from_status=previous_status,
                    to_status=ComplaintStatus.UNDER_REVIEW.value,
                    changed_by_id=None,
                    change_reason=f"Automated AI triage completed via {provider_name}",
                    notes=(
                        f"AI assigned priority {prio_rec.priority.value}. "
                        f"Routed to {dept.name if dept else 'General Administration'}."
                    ),
                ))

        # 7. Spatial Duplicate Check (PostGIS ST_DWithin on PostgreSQL; bounded fallback on SQLite)
        duplicates = find_potential_duplicates_from_db(db=db, new_complaint=complaint)
        for d in duplicates:
            existing_dup = db.query(PotentialDuplicate).filter(
                PotentialDuplicate.primary_complaint_id == d.complaint_id,
                PotentialDuplicate.duplicate_complaint_id == complaint.id,
            ).first()
            if not existing_dup:
                db.add(PotentialDuplicate(
                    primary_complaint_id=d.complaint_id,
                    duplicate_complaint_id=complaint.id,
                    similarity_score=d.similarity_score,
                    distance_meters=d.distance_meters,
                    reason=d.reason,
                    status="FLAGGED",
                ))

        # 8. Notify Citizen once for AI triage completion
        existing_ai_notif = (
            db.query(Notification)
            .filter(
                Notification.complaint_id == complaint.id,
                Notification.notification_type == NotificationType.AI_UPDATE.value,
            )
            .first()
        )
        if not existing_ai_notif and complaint.citizen_id:
            send_notification(
                db=db,
                user_id=complaint.citizen_id,
                title="Complaint Assessment Complete",
                message=(
                    f"Your complaint #{complaint.reference_number} has been assessed as "
                    f"priority {prio_rec.priority.value} and moved to Review."
                ),
                notification_type=NotificationType.AI_UPDATE.value,
                complaint_id=complaint.id,
                commit=False,
            )

        # 9. Audit Log (atomically staged, no PII/raw prompts)
        log_audit(
            db=db,
            action="AI_TRIAGE_EXECUTED",
            entity_type="COMPLAINT",
            entity_id=complaint.id,
            details={
                "provider": provider_name,
                "model": model_name,
                "previous_status": previous_status,
                "resulting_status": complaint.status,
                "suggested_category": text_result.suggested_category.value,
                "suggested_priority": prio_rec.priority.value,
                "confidence": prio_rec.confidence,
                "safety_hazard": text_result.safety_hazard_detected,
            },
            commit=False,
        )

        db.commit()
        db.refresh(ai_record)
        return ai_record

    async def process_complaint_by_id(
        self,
        complaint_id: str,
        session_factory: Optional[Callable[[], Session]] = None,
        force: bool = False,
        raise_on_failure: bool = False,
    ) -> Optional[AIAnalysis]:
        """
        Safely processes AI triage using an isolated database session.
        Idempotent across retries and resilient against provider failures/timeouts.
        """
        factory = session_factory or db_session.SessionLocal
        db = factory()
        try:
            if not self.try_claim_processing(db, complaint_id, force=force):
                logger.info("Skipping AI triage for %s (already processed or actively processing).", complaint_id)
                return None

            complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
            if not complaint:
                logger.warning("Complaint %s not found when starting AI background triage.", complaint_id)
                return None

            try:
                return await self._run_inference_and_persist(db, complaint)
            except Exception as exc:
                safe_error = sanitize_ai_error(exc)
                logger.error("AI triage pipeline failed for complaint %s: %s", complaint_id, safe_error)
                db.rollback()

                failed_complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
                if failed_complaint:
                    prev_fail_status = failed_complaint.status
                    failed_complaint.ai_processing_status = "FAILED"
                    failed_complaint.ai_processing_error = safe_error
                    failed_complaint.ai_processing_completed_at = datetime.now(timezone.utc)

                    # Preserve the complaint cleanly in manual review if still awaiting AI triage
                    if prev_fail_status in INITIAL_TRIAGE_STATUSES:
                        failed_complaint.status = ComplaintStatus.UNDER_REVIEW.value
                        existing_hist = (
                            db.query(ComplaintStatusHistory)
                            .filter(
                                ComplaintStatusHistory.complaint_id == failed_complaint.id,
                                ComplaintStatusHistory.from_status == prev_fail_status,
                                ComplaintStatusHistory.to_status == ComplaintStatus.UNDER_REVIEW.value,
                                ComplaintStatusHistory.changed_by_id.is_(None),
                            )
                            .first()
                        )
                        if not existing_hist:
                            db.add(ComplaintStatusHistory(
                                complaint_id=failed_complaint.id,
                                from_status=prev_fail_status,
                                to_status=ComplaintStatus.UNDER_REVIEW.value,
                                changed_by_id=None,
                                change_reason="Automated AI triage failed; queued for manual municipal review",
                                notes=safe_error,
                            ))

                    log_audit(
                        db=db,
                        action="AI_TRIAGE_FAILED",
                        entity_type="COMPLAINT",
                        entity_id=failed_complaint.id,
                        details={
                            "error": safe_error,
                            "attempt": failed_complaint.ai_processing_attempts,
                            "previous_status": prev_fail_status,
                            "resulting_status": failed_complaint.status,
                        },
                        commit=False,
                    )
                    db.commit()
                if raise_on_failure:
                    raise
                return None
        finally:
            db.close()

    async def process_new_complaint(self, db: Session, complaint: Complaint) -> Optional[AIAnalysis]:
        """Backward-compatible wrapper preserving atomic history recording and safe error isolation."""
        try:
            complaint.ai_processing_status = "PROCESSING"
            complaint.ai_processing_started_at = datetime.now(timezone.utc)
            complaint.ai_processing_attempts = (complaint.ai_processing_attempts or 0) + 1
            return await self._run_inference_and_persist(db, complaint)
        except Exception as exc:
            safe_error = sanitize_ai_error(exc)
            logger.error("Error in AI pipeline for complaint %s: %s", complaint.id, safe_error)
            db.rollback()
            prev_status = complaint.status
            complaint.ai_processing_status = "FAILED"
            complaint.ai_processing_error = safe_error
            complaint.ai_processing_completed_at = datetime.now(timezone.utc)
            if prev_status in INITIAL_TRIAGE_STATUSES:
                complaint.status = ComplaintStatus.UNDER_REVIEW.value
                db.add(ComplaintStatusHistory(
                    complaint_id=complaint.id,
                    from_status=prev_status,
                    to_status=ComplaintStatus.UNDER_REVIEW.value,
                    changed_by_id=None,
                    change_reason="Automated AI triage failed; queued for manual municipal review",
                    notes=safe_error,
                ))
            db.commit()
            raise exc


async def run_ai_triage_background(complaint_id: str, force: bool = False) -> None:
    """FastAPI BackgroundTasks entrypoint creating a dedicated fresh DB session and reconciling outbox state."""
    from app.models.entities import BackgroundJob

    await ai_service.process_complaint_by_id(complaint_id=complaint_id, force=force)
    db = db_session.SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.complaint_id == complaint_id,
                BackgroundJob.job_type == "ai_triage",
                BackgroundJob.status == "PENDING_DISPATCH",
            )
            .update(
                {
                    BackgroundJob.status: "SUCCEEDED",
                    BackgroundJob.completed_at: now,
                },
                synchronize_session=False,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def recover_interrupted_ai_jobs(session_factory: Optional[Callable[[], Session]] = None) -> int:
    """
    Startup recovery for in-process BackgroundTasks interrupted by process restarts/crashes.
    Identifies interrupted PENDING/PROCESSING complaints and moves them cleanly to FAILED +
    UNDER_REVIEW so no citizen ticket remains stuck indefinitely in AI_ANALYSIS_PENDING.
    """
    factory = session_factory or db_session.SessionLocal
    db = factory()
    try:
        stale_cutoff = AIService._stale_cutoff()
        interrupted = (
            db.query(Complaint)
            .filter(
                Complaint.status == ComplaintStatus.AI_ANALYSIS_PENDING.value,
                or_(
                    Complaint.ai_processing_status == "PENDING",
                    and_(
                        Complaint.ai_processing_status == "PROCESSING",
                        or_(
                            Complaint.ai_processing_started_at.is_(None),
                            Complaint.ai_processing_started_at < stale_cutoff,
                        ),
                    ),
                ),
            )
            .all()
        )
        recovered = 0
        now = datetime.now(timezone.utc)
        for comp in interrupted:
            prev = comp.status
            comp.ai_processing_status = "FAILED"
            comp.ai_processing_error = "Interrupted during process restart; eligible for AI retry."
            comp.ai_processing_completed_at = now
            comp.status = ComplaintStatus.UNDER_REVIEW.value
            db.add(ComplaintStatusHistory(
                complaint_id=comp.id,
                from_status=prev,
                to_status=ComplaintStatus.UNDER_REVIEW.value,
                changed_by_id=None,
                change_reason="Recovered interrupted background AI job into manual review",
            ))
            recovered += 1
        if recovered:
            db.commit()
        return recovered
    except Exception as exc:
        logger.warning("Skipping interrupted AI job recovery check: %s", sanitize_ai_error(exc))
        db.rollback()
        return 0
    finally:
        db.close()


ai_service = AIService()
