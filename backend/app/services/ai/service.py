import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    Complaint, AIAnalysis, PotentialDuplicate, MunicipalDepartment,
    ComplaintStatusHistory, Notification
)
from app.models.enums import ComplaintCategory, PriorityLevel, ComplaintStatus, NotificationType
from app.services.ai.base import BaseAIProvider
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.gemini_provider import GeminiAIProvider, AIServiceUnavailableError
from app.services.ai.duplicate_detector import find_potential_duplicates
from app.services.audit import log_audit

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.mock_provider = MockAIProvider()
        self.gemini_provider = GeminiAIProvider()

    def get_provider(self) -> Tuple[BaseAIProvider, str, str]:
        """
        Dynamically returns (provider_instance, provider_identifier, model_name).
        Enforces honest reporting: if 'gemini' is requested but GOOGLE_API_KEY is missing,
        it uses the deterministic offline provider while recording 'mock_fallback_gemini_unconfigured'.
        """
        if settings.AI_PROVIDER.lower() == "gemini":
            if self.gemini_provider.is_configured():
                return self.gemini_provider, "gemini", self.gemini_provider.model_name
            else:
                logger.warning(
                    "[AI SERVICE] AI_PROVIDER is set to 'gemini' but GOOGLE_API_KEY is not configured. "
                    "Operating with deterministic MockAIProvider fallback without claiming genuine Gemini output."
                )
                return self.mock_provider, "mock_fallback_gemini_unconfigured", "civicfix-deterministic-nlp-v1"

        return self.mock_provider, "mock", "civicfix-deterministic-nlp-v1"

    async def process_new_complaint(self, db: Session, complaint: Complaint) -> AIAnalysis:
        """
        Asynchronously processes a newly submitted complaint:
        1. Categorization & text analysis (Gemini or Mock)
        2. Vision analysis (if attachments exist)
        3. Priority recommendation (P1-P4) & SLA calculation
        4. Department routing suggestion
        5. Spatial & semantic duplicate detection
        """
        provider, provider_name, model_name = self.get_provider()

        try:
            # 1. Text Analysis
            text_result = await provider.analyze_text(
                title=complaint.title,
                description=complaint.description
            )

            # 2. Vision Analysis (if attachments exist)
            image_result = None
            if complaint.attachments:
                first_img = complaint.attachments[0]
                image_result = await provider.analyze_image(first_img.file_path)

            # 3. Priority Recommendation
            prio_rec = provider.recommend_priority(
                category=text_result.suggested_category,
                text_result=text_result,
                image_result=image_result
            )

            # 4. Department Routing: find corresponding municipal department
            category_dept_map = {
                ComplaintCategory.ROADS: "ROADS",
                ComplaintCategory.STREETLIGHTS: "LIGHTING",
                ComplaintCategory.GARBAGE: "SANITATION",
                ComplaintCategory.DRAINAGE: "DRAINAGE",
                ComplaintCategory.WATER_SUPPLY: "WATER",
                ComplaintCategory.FOOTPATHS: "ROADS",
                ComplaintCategory.TREES_HAZARDS: "PARKS",
                ComplaintCategory.SANITATION: "SANITATION",
                ComplaintCategory.OTHER: "ROADS"
            }
            dept_code = category_dept_map.get(text_result.suggested_category, "ROADS")
            dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.code == dept_code).first()

            # 5. SLA Deadline calculation
            sla_hours = {
                PriorityLevel.P1: settings.SLA_HOURS_P1,
                PriorityLevel.P2: settings.SLA_HOURS_P2,
                PriorityLevel.P3: settings.SLA_HOURS_P3,
                PriorityLevel.P4: settings.SLA_HOURS_P4
            }.get(prio_rec.priority, 72)
            
            sla_deadline = datetime.now(timezone.utc) + timedelta(hours=sla_hours)

            # 6. Construct AIAnalysis record
            visual_findings_json = None
            if image_result:
                visual_findings_json = json.dumps({
                    "damage_detected": image_result.damage_detected,
                    "damage_type": image_result.damage_type,
                    "severity": image_result.damage_severity,
                    "observations": image_result.observations,
                    "is_inconclusive": getattr(image_result, "is_inconclusive", False)
                })

            # Check if an analysis already exists (e.g. during re-analysis)
            ai_record = db.query(AIAnalysis).filter(AIAnalysis.complaint_id == complaint.id).first()
            if not ai_record:
                ai_record = AIAnalysis(complaint_id=complaint.id)
                db.add(ai_record)

            ai_record.provider = provider_name
            ai_record.model_name = model_name
            ai_record.suggested_category = text_result.suggested_category.value
            ai_record.suggested_subcategory = text_result.suggested_subcategory
            ai_record.suggested_priority = prio_rec.priority.value
            ai_record.confidence_score = prio_rec.confidence
            ai_record.safety_hazard_detected = text_result.safety_hazard_detected
            ai_record.urgency_level = text_result.urgency_level
            ai_record.summary_explanation = f"{text_result.summary_explanation} Priority Rationale: {prio_rec.rationale}"
            ai_record.visual_findings = visual_findings_json
            ai_record.duplicate_checked = True

            # Update Complaint with AI suggestions (labeled as suggestions; human confirmation required before closure)
            complaint.priority = prio_rec.priority.value
            if dept:
                complaint.department_id = dept.id
            complaint.sla_deadline = sla_deadline
            if complaint.status == ComplaintStatus.SUBMITTED.value:
                complaint.status = ComplaintStatus.UNDER_REVIEW.value

            # Add status history entry
            history_entry = ComplaintStatusHistory(
                complaint_id=complaint.id,
                from_status=complaint.status,
                to_status=ComplaintStatus.UNDER_REVIEW.value,
                change_reason=f"Automated AI triage completed via {provider_name}",
                notes=f"AI assigned priority {prio_rec.priority.value}. Routed to {dept.name if dept else 'General Administration'}."
            )
            db.add(history_entry)

            # 7. Duplicate Check
            existing_complaints = db.query(Complaint).filter(Complaint.id != complaint.id).all()
            duplicates = find_potential_duplicates(complaint, existing_complaints)
            
            for d in duplicates:
                existing_dup = db.query(PotentialDuplicate).filter(
                    PotentialDuplicate.primary_complaint_id == d.complaint_id,
                    PotentialDuplicate.duplicate_complaint_id == complaint.id
                ).first()
                if not existing_dup:
                    dup_record = PotentialDuplicate(
                        primary_complaint_id=d.complaint_id,
                        duplicate_complaint_id=complaint.id,
                        similarity_score=d.similarity_score,
                        distance_meters=d.distance_meters,
                        reason=d.reason,
                        status="FLAGGED"
                    )
                    db.add(dup_record)

            # 8. Notification to Citizen
            notif = Notification(
                user_id=complaint.citizen_id,
                title="Complaint Assessment Complete",
                message=f"Your complaint #{complaint.reference_number} has been assessed as priority {prio_rec.priority.value} and moved to Review.",
                notification_type=NotificationType.AI_UPDATE.value,
                complaint_id=complaint.id
            )
            db.add(notif)

            # 9. Record safe audit log (no PII or raw prompts)
            log_audit(
                db=db,
                action="AI_TRIAGE_EXECUTED",
                entity_type="COMPLAINT",
                entity_id=complaint.id,
                details={
                    "provider": provider_name,
                    "model": model_name,
                    "suggested_category": text_result.suggested_category.value,
                    "suggested_priority": prio_rec.priority.value,
                    "confidence": prio_rec.confidence,
                    "safety_hazard": text_result.safety_hazard_detected
                }
            )

            db.commit()
            db.refresh(ai_record)
            return ai_record

        except Exception as e:
            logger.error(f"Error in AI pipeline for complaint {complaint.id}: {str(e)}", exc_info=True)
            db.rollback()
            # In case of AI failure, mark status as UNDER_REVIEW anyway so it never gets lost!
            complaint.status = ComplaintStatus.UNDER_REVIEW.value
            db.commit()
            raise e

ai_service = AIService()
