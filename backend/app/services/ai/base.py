from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from app.models.enums import ComplaintCategory, PriorityLevel

@dataclass
class TextAnalysisResult:
    suggested_category: ComplaintCategory
    suggested_subcategory: Optional[str]
    safety_hazard_detected: bool
    urgency_level: str  # CRITICAL, HIGH, MEDIUM, LOW
    confidence_score: float
    summary_explanation: str
    extracted_keywords: List[str]

@dataclass
class ImageAnalysisResult:
    damage_detected: bool
    damage_type: str
    damage_severity: str
    confidence_score: float
    observations: List[str]
    is_inconclusive: bool

@dataclass
class PriorityRecommendation:
    priority: PriorityLevel
    confidence: float
    rationale: str
    factors_considered: Dict[str, Any]

@dataclass
class DuplicateMatch:
    complaint_id: str
    reference_number: str
    similarity_score: float
    distance_meters: float
    reason: str

class BaseAIProvider(ABC):
    @abstractmethod
    async def analyze_text(self, title: str, description: str, language: str = "en") -> TextAnalysisResult:
        pass

    @abstractmethod
    async def analyze_image(self, file_path: str) -> ImageAnalysisResult:
        pass

    @abstractmethod
    async def transcribe_audio(self, file_path: str, language: str = "en") -> str:
        pass

    @abstractmethod
    def recommend_priority(
        self,
        category: ComplaintCategory,
        text_result: TextAnalysisResult,
        image_result: Optional[ImageAnalysisResult] = None
    ) -> PriorityRecommendation:
        pass

