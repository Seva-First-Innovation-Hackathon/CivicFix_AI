from datetime import datetime, timedelta, timezone
import logging
import math
import re
from typing import List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.spatial_types import is_valid_coordinates, postgis_point_expr
from app.models.entities import Complaint
from app.services.ai.base import DuplicateMatch
from app.services.maps.spatial import haversine_distance_meters

logger = logging.getLogger(__name__)

CLOSED_DUPLICATE_EXCLUDED_STATUSES = ("RESOLVED", "CANCELLED")


def tokenize_text(text: str) -> set:
    words = re.findall(r"\b[a-zA-Z]{3,}\b", (text or "").lower())
    stop_words = {
        "the", "and", "for", "with", "this", "that", "from", "near", "there", "have", "area", "please"
    }
    return {w for w in words if w not in stop_words}


def compute_text_similarity(text1: str, text2: str) -> float:
    tokens1 = tokenize_text(text1)
    tokens2 = tokenize_text(text2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def _score_candidate(
    new_complaint: Complaint,
    candidate: Complaint,
    distance_meters: float,
    max_distance_meters: float,
) -> DuplicateMatch | None:
    if distance_meters > max_distance_meters:
        return None

    same_category = new_complaint.category == candidate.category
    text_sim = compute_text_similarity(
        f"{new_complaint.title} {new_complaint.description}",
        f"{candidate.title} {candidate.description}",
    )
    dist_score = max(0.0, 1.0 - (distance_meters / max_distance_meters))

    # Distance (45%) + Category (30%) + Text Jaccard (25%)
    sim_score = (0.45 * dist_score) + (0.30 * (1.0 if same_category else 0.0)) + (0.25 * text_sim)
    if sim_score < 0.55:
        return None

    reason = (
        f"Located {int(distance_meters)}m away. "
        f"{'Same category (' + candidate.category + '). ' if same_category else 'Different category. '}"
        f"Text overlap: {int(text_sim * 100)}%."
    )
    return DuplicateMatch(
        complaint_id=candidate.id,
        reference_number=candidate.reference_number,
        similarity_score=round(sim_score, 2),
        distance_meters=round(distance_meters, 1),
        reason=reason,
    )


def build_postgis_duplicate_query(
    db: Session,
    new_complaint: Complaint,
    max_distance_meters: float,
    cutoff_time: datetime,
    candidate_limit: int = 50,
):
    """
    Constructs a PostGIS-backed ST_DWithin spatial query using Complaint.location GiST index.
    Separated cleanly so both production runtime and SQL compilation tests target one query builder.
    """
    target_geog = postgis_point_expr(new_complaint.latitude, new_complaint.longitude)
    dist_expr = func.ST_Distance(Complaint.location, target_geog).label("distance_meters")
    return (
        db.query(Complaint, dist_expr)
        .filter(
            Complaint.id != new_complaint.id,
            Complaint.status.notin_(CLOSED_DUPLICATE_EXCLUDED_STATUSES),
            Complaint.created_at >= cutoff_time,
            Complaint.location.isnot(None),
            func.ST_DWithin(Complaint.location, target_geog, float(max_distance_meters)),
        )
        .order_by(dist_expr.asc())
        .limit(candidate_limit)
    )


def _fetch_sqlite_spatial_candidates(
    db: Session,
    new_complaint: Complaint,
    max_distance_meters: float,
    cutoff_time: datetime,
    candidate_limit: int = 50,
) -> List[Tuple[Complaint, float]]:
    """
    Explicitly isolated SQLite bounding-box fallback for local dev/unit tests where PostGIS is absent.
    Avoids loading resolved/out-of-area rows by filtering lat/lon bounds in SQL first.
    """
    lat = float(new_complaint.latitude)
    lon = float(new_complaint.longitude)
    lat_delta = min(180.0, (max_distance_meters / 111320.0) * 1.15)
    cos_lat = max(0.01, abs(math.cos(math.radians(lat))))
    lon_delta = min(180.0, (max_distance_meters / (111320.0 * cos_lat)) * 1.15)

    query = db.query(Complaint).filter(
        Complaint.id != new_complaint.id,
        Complaint.status.notin_(CLOSED_DUPLICATE_EXCLUDED_STATUSES),
        Complaint.created_at >= cutoff_time,
        Complaint.latitude.between(max(-90.0, lat - lat_delta), min(90.0, lat + lat_delta)),
    )
    if lon - lon_delta >= -180.0 and lon + lon_delta <= 180.0:
        query = query.filter(Complaint.longitude.between(lon - lon_delta, lon + lon_delta))

    candidates = query.order_by(Complaint.created_at.desc()).limit(candidate_limit * 2).all()
    paired: List[Tuple[Complaint, float]] = []
    for candidate in candidates:
        if not is_valid_coordinates(candidate.latitude, candidate.longitude):
            continue
        dist = haversine_distance_meters(lat, lon, candidate.latitude, candidate.longitude)
        if dist <= max_distance_meters:
            paired.append((candidate, dist))
    paired.sort(key=lambda item: item[1])
    return paired[:candidate_limit]


def find_potential_duplicates_from_db(
    db: Session,
    new_complaint: Complaint,
    max_distance_meters: float = settings.DUPLICATE_RADIUS_METERS,
    max_days: int = settings.DUPLICATE_TIME_WINDOW_DAYS,
    candidate_limit: int = 50,
) -> List[DuplicateMatch]:
    """
    Database-first spatial duplicate detector:
    - On PostgreSQL/PostGIS: filters spatially in database with ST_DWithin + ST_Distance via GiST index.
    - On SQLite (local/unit test fallback): filters via bounded lat/lon bounding box + Haversine.
    Applies weighted category and Jaccard text similarity only to spatially proximate candidates.
    """
    if not is_valid_coordinates(new_complaint.latitude, new_complaint.longitude):
        logger.warning(
            "Skipping spatial duplicate scan for complaint %s due to invalid coordinates.",
            getattr(new_complaint, "id", "unknown"),
        )
        return []

    cutoff_time = datetime.now(timezone.utc) - timedelta(days=max_days)
    dialect_name = db.bind.dialect.name if db.bind is not None else "sqlite"

    candidates_with_dist: List[Tuple[Complaint, float]] = []
    if dialect_name == "postgresql":
        try:
            rows = build_postgis_duplicate_query(
                db=db,
                new_complaint=new_complaint,
                max_distance_meters=max_distance_meters,
                cutoff_time=cutoff_time,
                candidate_limit=candidate_limit,
            ).all()
            candidates_with_dist = [(comp, float(dist)) for comp, dist in rows if dist is not None]
        except Exception as exc:
            logger.error(
                "PostGIS spatial duplicate query failed for complaint %s: %s",
                getattr(new_complaint, "id", "unknown"),
                exc,
                exc_info=True,
            )
            raise
    else:
        candidates_with_dist = _fetch_sqlite_spatial_candidates(
            db=db,
            new_complaint=new_complaint,
            max_distance_meters=max_distance_meters,
            cutoff_time=cutoff_time,
            candidate_limit=candidate_limit,
        )

    matches: List[DuplicateMatch] = []
    for candidate, dist in candidates_with_dist:
        match = _score_candidate(
            new_complaint=new_complaint,
            candidate=candidate,
            distance_meters=dist,
            max_distance_meters=max_distance_meters,
        )
        if match is not None:
            matches.append(match)

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches


def find_potential_duplicates(
    new_complaint: Complaint,
    existing_complaints: List[Complaint],
    max_distance_meters: float = settings.DUPLICATE_RADIUS_METERS,
    max_days: int = settings.DUPLICATE_TIME_WINDOW_DAYS,
) -> List[DuplicateMatch]:
    """In-memory helper retained for deterministic pure-Python unit checks."""
    if not is_valid_coordinates(new_complaint.latitude, new_complaint.longitude):
        return []

    matches: List[DuplicateMatch] = []
    for candidate in existing_complaints:
        if candidate.id == new_complaint.id:
            continue
        if candidate.status in CLOSED_DUPLICATE_EXCLUDED_STATUSES:
            continue
        if not is_valid_coordinates(candidate.latitude, candidate.longitude):
            continue

        distance = haversine_distance_meters(
            new_complaint.latitude,
            new_complaint.longitude,
            candidate.latitude,
            candidate.longitude,
        )
        match = _score_candidate(
            new_complaint=new_complaint,
            candidate=candidate,
            distance_meters=distance,
            max_distance_meters=max_distance_meters,
        )
        if match is not None:
            matches.append(match)

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches
