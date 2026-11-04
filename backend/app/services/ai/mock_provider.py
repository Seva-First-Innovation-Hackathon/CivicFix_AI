import re
from typing import Optional, List, Dict, Any
from app.models.enums import ComplaintCategory, PriorityLevel
from app.services.ai.base import (
    BaseAIProvider,
    TextAnalysisResult,
    ImageAnalysisResult,
    PriorityRecommendation
)

class MockAIProvider(BaseAIProvider):
    provider_name = "mock"
    model_name = "civicfix-deterministic-nlp-v1"

    async def analyze_text(self, title: str, description: str, language: str = "en") -> TextAnalysisResult:
        combined = f"{title.lower()} {description.lower()}"
        
        # Hazard / emergency keywords
        critical_keywords = ["danger", "accident", "emergency", "sparking", "exposed wire", "cave-in", "flooded house", "fallen tree on road", "death trap", "open manhole"]
        high_keywords = ["broken", "overflowing", "deep pothole", "burst", "leakage", "dark street", "waterlogged", "blocked drain", "foul smell", "hazard"]
        
        has_critical = any(kw in combined for kw in critical_keywords)
        has_high = any(kw in combined for kw in high_keywords)

        # Categorization logic
        category = ComplaintCategory.OTHER
        subcategory = "General Civic Issue"
        keywords = []

        if any(w in combined for w in ["pothole", "road", "tar", "asphalt", "crater", "speed breaker", "cracking"]):
            category = ComplaintCategory.ROADS
            subcategory = "Road Surface Damage & Potholes"
            keywords.extend(["pothole", "road maintenance"])
        elif any(w in combined for w in ["light", "lamp", "dark", "pole", "wire", "bulb", "streetlight"]):
            category = ComplaintCategory.STREETLIGHTS
            subcategory = "Non-functional Luminaire / Broken Pole"
            keywords.extend(["streetlight", "public illumination"])
        elif any(w in combined for w in ["garbage", "trash", "waste", "dump", "bin", "debris", "litter"]):
            category = ComplaintCategory.GARBAGE
            subcategory = "Waste Accumulation & Illegal Dumping"
            keywords.extend(["solid waste", "sanitation bin"])
        elif any(w in combined for w in ["drain", "waterlogging", "sewage", "gutter", "clogged drain", "monsoon"]):
            category = ComplaintCategory.DRAINAGE
            subcategory = "Stormwater Drain Blockage / Waterlogging"
            keywords.extend(["drainage network", "waterlogging"])
        elif any(w in combined for w in ["water supply", "pipe", "pipeline", "leak", "drinking water", "tap"]):
            category = ComplaintCategory.WATER_SUPPLY
            subcategory = "Pipeline Leakage / Supply Disruption"
            keywords.extend(["potable water", "pipeline infrastructure"])
        elif any(w in combined for w in ["footpath", "sidewalk", "pedestrian", "pavement", "kerb"]):
            category = ComplaintCategory.FOOTPATHS
            subcategory = "Pedestrian Walkway Structural Damage"
            keywords.extend(["pedestrian safety", "walkway"])
        elif any(w in combined for w in ["tree", "branch", "fallen", "uprooted", "collapse", "hazard"]):
            category = ComplaintCategory.TREES_HAZARDS
            subcategory = "Fallen Tree / Structural Obstruction"
            keywords.extend(["urban forestry", "public hazard"])
        elif any(w in combined for w in ["toilet", "urinal", "hygiene", "sanitary", "stagnant"]):
            category = ComplaintCategory.SANITATION
            subcategory = "Public Sanitation Facility Maintenance"
            keywords.extend(["public health", "hygiene"])

        # Determine urgency and safety
        safety_hazard = has_critical or category in [ComplaintCategory.TREES_HAZARDS, ComplaintCategory.DRAINAGE] and ("open" in combined or "spark" in combined)
        
        if has_critical:
            urgency = "CRITICAL"
            confidence = 0.94
        elif has_high or category != ComplaintCategory.OTHER:
            urgency = "HIGH" if has_high else "MEDIUM"
            confidence = 0.88
        else:
            urgency = "LOW"
            confidence = 0.72

        explanation = (
            f"Automated linguistic scan classified report under {category.value} ({subcategory}). "
            f"Detected indicators: {', '.join(keywords) if keywords else 'general report'}. "
            f"Safety hazard status: {'Immediate risk flagged' if safety_hazard else 'Standard operational review'}."
        )

        return TextAnalysisResult(
            suggested_category=category,
            suggested_subcategory=subcategory,
            safety_hazard_detected=safety_hazard,
            urgency_level=urgency,
            confidence_score=confidence,
            summary_explanation=explanation,
            extracted_keywords=keywords
        )

    async def analyze_image(self, file_path: str) -> ImageAnalysisResult:
        # Deterministic analysis for mock provider
        file_lower = file_path.lower()
        if "resolution" in file_lower or "after" in file_lower:
            return ImageAnalysisResult(
                damage_detected=False,
                damage_type="Remediated Site / Repair Completed",
                damage_severity="NONE",
                confidence_score=0.91,
                observations=[
                    "Surface leveled and restored to municipal standards",
                    "No residual debris or obstruction observed",
                    "Clear vehicular/pedestrian clearance confirmed"
                ],
                is_inconclusive=False
            )
        
        return ImageAnalysisResult(
            damage_detected=True,
            damage_type="Civic Infrastructure Defect",
            damage_severity="HIGH",
            confidence_score=0.87,
            observations=[
                "Visible structural surface deterioration detected",
                "Hazard footprint extends into public thoroughfare",
                "Photographic evidence matches reported complaint parameters"
            ],
            is_inconclusive=False
        )

    async def transcribe_audio(self, file_path: str, language: str = "en") -> str:
        if language == "te":
            return "రహదారిపై పెద్ద గుంత ఉంది, వర్షపు నీరు చేరి ప్రమాదకరంగా మారింది. దయచేసి వెంటనే మరమ్మతు చేయండి."
        elif language == "hi":
            return "मुख्य सड़क पर बड़ा गड्ढा हो गया है और पानी भरा हुआ है। दुर्घटना की संभावना है, कृपया शीघ्र मरम्मत कराएं।"
        return "There is a severe pothole in the middle of the road with stagnant water causing frequent traffic hazards. Immediate repair is required."

    def recommend_priority(
        self,
        category: ComplaintCategory,
        text_result: TextAnalysisResult,
        image_result: Optional[ImageAnalysisResult] = None
    ) -> PriorityRecommendation:
        # P1 Policy: Critical safety hazard, exposed wire, open manhole, fallen tree blocking transit
        if text_result.safety_hazard_detected or text_result.urgency_level == "CRITICAL":
            return PriorityRecommendation(
                priority=PriorityLevel.P1,
                confidence=0.95,
                rationale="Critical safety hazard detected with potential for immediate vehicular or pedestrian harm. SLA: 12 Hours.",
                factors_considered={"safety_hazard": True, "urgency": "CRITICAL", "category": category.value}
            )
        
        # P2 Policy: High urgency, water supply burst, main road issues, overflowing sewer
        if text_result.urgency_level == "HIGH" or category in [ComplaintCategory.WATER_SUPPLY, ComplaintCategory.DRAINAGE]:
            return PriorityRecommendation(
                priority=PriorityLevel.P2,
                confidence=0.89,
                rationale="Substantial disruption to civic infrastructure or essential utility. Prompt intervention recommended. SLA: 24 Hours.",
                factors_considered={"safety_hazard": False, "urgency": "HIGH", "category": category.value}
            )

        # P4 Policy: Minor aesthetic or non-urgent issue
        if text_result.urgency_level == "LOW":
            return PriorityRecommendation(
                priority=PriorityLevel.P4,
                confidence=0.82,
                rationale="Minor maintenance concern without safety compromise. SLA: 168 Hours.",
                factors_considered={"safety_hazard": False, "urgency": "LOW", "category": category.value}
            )

        # P3 Default: Routine maintenance
        return PriorityRecommendation(
            priority=PriorityLevel.P3,
            confidence=0.87,
            rationale="Standard municipal maintenance issue. Scheduled within normal operational roster. SLA: 72 Hours.",
            factors_considered={"safety_hazard": False, "urgency": "MEDIUM", "category": category.value}
        )

