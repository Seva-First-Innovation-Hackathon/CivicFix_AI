from collections import Counter, defaultdict
from datetime import datetime, timezone
import logging
import math
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status as http_status
from geoalchemy2 import Geometry
from sqlalchemy import and_, case, cast, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.spatial_types import is_valid_coordinates
from app.models.entities import Complaint, User
from app.models.enums import ComplaintStatus, UserRole

logger = logging.getLogger(__name__)

OPEN_EXCLUDE_STATUSES = {
    ComplaintStatus.RESOLVED.value,
    ComplaintStatus.CANCELLED.value,
    ComplaintStatus.REJECTED.value,
}


def _apply_hotspot_filters(
    query,
    current_user: User,
    category: Optional[str],
    priority: Optional[str],
    status: Optional[str],
    department_id: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    overdue_only: bool,
):
    if current_user.role == UserRole.FIELD_CREW.value:
        query = query.filter(Complaint.assigned_crew_id == current_user.id)
    elif current_user.role == UserRole.MUNICIPAL_MEMBER.value:
        if current_user.department_membership:
            user_dept_id = current_user.department_membership.department_id
            if department_id and department_id != user_dept_id:
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You cannot access hotspot analytics for another department.",
                )
            query = query.filter(
                or_(Complaint.department_id == user_dept_id, Complaint.department_id.is_(None))
            )
        else:
            query = query.filter(Complaint.department_id.is_(None))
    elif department_id:
        query = query.filter(Complaint.department_id == department_id)

    if category:
        query = query.filter(Complaint.category == category)
    if priority:
        query = query.filter(Complaint.priority == priority)
    if status:
        query = query.filter(Complaint.status == status)
    if overdue_only:
        query = query.filter(
            Complaint.sla_deadline.isnot(None),
            Complaint.sla_deadline < datetime.now(timezone.utc),
            Complaint.status.notin_(list(OPEN_EXCLUDE_STATUSES)),
        )
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(Complaint.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(Complaint.created_at <= dt_to)
        except ValueError:
            pass

    return query


def build_postgis_hotspot_query(
    db: Session,
    current_user: User,
    grid_size_meters: int = 500,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    department_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    overdue_only: bool = False,
):
    """
    Constructs a PostGIS ST_SnapToGrid aggregation query grouped strictly in-DB without
    selecting citizen PII columns.
    """
    grid_deg = max(100, min(5000, grid_size_meters)) / 111320.0
    now = datetime.now(timezone.utc)
    snapped_geom = func.ST_SnapToGrid(cast(Complaint.location, Geometry(srid=4326)), grid_deg)
    bucket_lat_expr = func.ST_Y(snapped_geom).label("bucket_lat")
    bucket_lon_expr = func.ST_X(snapped_geom).label("bucket_lon")
    is_open_cond = Complaint.status.notin_(list(OPEN_EXCLUDE_STATUSES))

    query = db.query(
        bucket_lat_expr,
        bucket_lon_expr,
        Complaint.category.label("category"),
        func.count(Complaint.id).label("complaint_count"),
        func.sum(case((is_open_cond, 1), else_=0)).label("open_count"),
        func.sum(case((and_(Complaint.priority == "P1", is_open_cond), 1), else_=0)).label("p1_count"),
        func.sum(
            case(
                (and_(Complaint.sla_deadline.isnot(None), Complaint.sla_deadline < now, is_open_cond), 1),
                else_=0,
            )
        ).label("overdue_count"),
    ).filter(Complaint.location.isnot(None))

    query = _apply_hotspot_filters(
        query, current_user, category, priority, status, department_id, date_from, date_to, overdue_only
    )
    return query.group_by(bucket_lat_expr, bucket_lon_expr, Complaint.category)


def compute_spatial_hotspots(
    db: Session,
    current_user: User,
    grid_size_meters: int = 500,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    department_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    overdue_only: bool = False,
) -> Dict[str, Any]:
    """
    Aggregates civic complaints into non-PII geographic hotspot clusters filtered by
    category, priority, status, department, overdue state, and date range.
    Uses PostgreSQL PostGIS ST_SnapToGrid DB grouping when running on PostgreSQL,
    or isolated coordinate bucketing on SQLite dev/test databases.
    """
    clean_grid_m = max(100, min(5000, int(grid_size_meters or 500)))
    grid_deg = clean_grid_m / 111320.0
    now = datetime.now(timezone.utc)
    dialect_name = db.bind.dialect.name if db.bind is not None else "sqlite"

    buckets: Dict[tuple, Dict[str, Any]] = defaultdict(
        lambda: {
            "lats": [],
            "lons": [],
            "complaint_count": 0,
            "open_count": 0,
            "p1_count": 0,
            "overdue_count": 0,
            "categories": Counter(),
        }
    )

    matched_total = 0
    if dialect_name == "postgresql":
        pg_rows = build_postgis_hotspot_query(
            db=db,
            current_user=current_user,
            grid_size_meters=clean_grid_m,
            category=category,
            priority=priority,
            status=status,
            department_id=department_id,
            date_from=date_from,
            date_to=date_to,
            overdue_only=overdue_only,
        ).all()
        for row in pg_rows:
            if row.bucket_lat is None or row.bucket_lon is None:
                continue
            cell_key = (round(float(row.bucket_lat), 6), round(float(row.bucket_lon), 6))
            bucket = buckets[cell_key]
            cnt = int(row.complaint_count or 0)
            matched_total += cnt
            bucket["lats"].append(float(row.bucket_lat))
            bucket["lons"].append(float(row.bucket_lon))
            bucket["complaint_count"] += cnt
            bucket["open_count"] += int(row.open_count or 0)
            bucket["p1_count"] += int(row.p1_count or 0)
            bucket["overdue_count"] += int(row.overdue_count or 0)
            bucket["categories"][row.category] += cnt
    else:
        # Isolated SQLite non-PII spatial column query
        query = db.query(
            Complaint.latitude,
            Complaint.longitude,
            Complaint.category,
            Complaint.status,
            Complaint.priority,
            Complaint.sla_deadline,
        )
        query = _apply_hotspot_filters(
            query, current_user, category, priority, status, department_id, date_from, date_to, overdue_only
        )
        for lat, lon, cat, st, prio, sla_dl in query.all():
            if not is_valid_coordinates(lat, lon):
                continue
            matched_total += 1
            b_lat_idx = math.floor(float(lat) / grid_deg)
            b_lon_idx = math.floor(float(lon) / grid_deg)
            bucket = buckets[(b_lat_idx, b_lon_idx)]
            bucket["lats"].append(float(lat))
            bucket["lons"].append(float(lon))
            bucket["complaint_count"] += 1
            if st not in OPEN_EXCLUDE_STATUSES:
                bucket["open_count"] += 1
                if sla_dl is not None:
                    dl_utc = sla_dl.replace(tzinfo=timezone.utc) if sla_dl.tzinfo is None else sla_dl.astimezone(timezone.utc)
                    if dl_utc < now:
                        bucket["overdue_count"] += 1
            if prio == "P1" and st not in OPEN_EXCLUDE_STATUSES:
                bucket["p1_count"] += 1
            bucket["categories"][cat] += 1

    max_count = max((b["complaint_count"] for b in buckets.values()), default=1)
    hotspot_clusters: List[Dict[str, Any]] = []
    for bucket in buckets.values():
        cnt = bucket["complaint_count"]
        dominant_cat = bucket["categories"].most_common(1)[0][0]
        centroid_lat = round(sum(bucket["lats"]) / len(bucket["lats"]), 5)
        centroid_lon = round(sum(bucket["lons"]) / len(bucket["lons"]), 5)
        hotspot_clusters.append({
            "bucket_lat": centroid_lat,
            "bucket_lon": centroid_lon,
            "complaint_count": cnt,
            "open_count": bucket["open_count"],
            "p1_count": bucket["p1_count"],
            "overdue_count": bucket["overdue_count"],
            "dominant_category": dominant_cat,
            "intensity": round(cnt / max_count, 3),
            "radius_meters": max(150, min(2500, int(clean_grid_m * (0.6 + 0.6 * (cnt / max_count))))),
        })

    hotspot_clusters.sort(key=lambda h: (h["complaint_count"], h["p1_count"]), reverse=True)

    has_demo_citizens = (
        db.query(User.id)
        .filter(User.email.like("citizen%@example.com"))
        .first()
        is not None
    )

    return {
        "hotspots": hotspot_clusters,
        "total_complaints_matched": matched_total,
        "grid_size_meters": clean_grid_m,
        "aggregation_method": "postgis_st_snaptogrid" if dialect_name == "postgresql" else "bounded_coordinate_grid",
        "is_demonstration_mode": bool(
            os.getenv("ALLOW_DEMO_SEEDING", "").strip().lower() == "true" or has_demo_citizens
        ),
    }
