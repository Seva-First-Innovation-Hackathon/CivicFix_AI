from typing import List, Optional
from datetime import datetime, timezone, timedelta
import re
from app.models.entities import Complaint
from app.services.maps.spatial import haversine_distance_meters
from app.services.ai.base import DuplicateMatch
from app.core.config import settings

def tokenize_text(text: str) -> set:
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    stop_words = {"the", "and", "for", "with", "this", "that", "from", "near", "there", "have", "area", "please"}
    return {w for w in words if w not in stop_words}

def compute_text_similarity(text1: str, text2: str) -> float:
    tokens1 = tokenize_text(text1)
    tokens2 = tokenize_text(text2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)

def find_potential_duplicates(
    new_complaint: Complaint,
    existing_complaints: List[Complaint],
    max_distance_meters: float = settings.DUPLICATE_RADIUS_METERS,
    max_days: int = settings.DUPLICATE_TIME_WINDOW_DAYS
) -> List[DuplicateMatch]:
    matches: List[DuplicateMatch] = []
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=max_days)

    for candidate in existing_complaints:
        # Don't match against self
        if candidate.id == new_complaint.id:
            continue

        # Skip resolved/cancelled from old periods
        if candidate.status in ["RESOLVED", "CANCELLED"]:
            continue

        # Spatial distance check
        distance = haversine_distance_meters(
            new_complaint.latitude, new_complaint.longitude,
            candidate.latitude, candidate.longitude
        )

        if distance > max_distance_meters:
            continue

        # Category factor
        same_category = (new_complaint.category == candidate.category)
        
        # Text similarity factor
        text_sim = compute_text_similarity(
            f"{new_complaint.title} {new_complaint.description}",
            f"{candidate.title} {candidate.description}"
        )

        # Distance score: closer -> higher score
        dist_score = max(0.0, 1.0 - (distance / max_distance_meters))

        # Overall weighted similarity score:
        # Distance (45%) + Category (30%) + Text (25%)
        sim_score = (0.45 * dist_score) + (0.30 * (1.0 if same_category else 0.0)) + (0.25 * text_sim)

        # If similarity threshold met (e.g. >= 0.55)
        if sim_score >= 0.55:
            reason = (
                f"Located {int(distance)}m away. "
                f"{'Same category (' + candidate.category + '). ' if same_category else 'Different category. '}"
                f"Text overlap: {int(text_sim * 100)}%."
            )
            matches.append(DuplicateMatch(
                complaint_id=candidate.id,
                reference_number=candidate.reference_number,
                similarity_score=round(sim_score, 2),
                distance_meters=round(distance, 1),
                reason=reason
            ))

    # Sort by similarity score descending
    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches

