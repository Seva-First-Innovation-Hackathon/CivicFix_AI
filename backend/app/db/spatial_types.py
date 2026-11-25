import math
import re
from typing import Optional, Tuple

from geoalchemy2 import Geography
import sqlalchemy as sa
from sqlalchemy import func


def is_valid_coordinates(latitude: Optional[float], longitude: Optional[float]) -> bool:
    """Returns True only if latitude/longitude are finite numbers within WGS84 bounds."""
    if latitude is None or longitude is None:
        return False
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def format_geog_point_wkt(latitude: Optional[float], longitude: Optional[float]) -> Optional[str]:
    """Formats valid WGS84 coordinates into canonical EWKT POINT(lon lat)."""
    if not is_valid_coordinates(latitude, longitude):
        return None
    return f"SRID=4326;POINT({float(longitude):.8f} {float(latitude):.8f})"


def parse_wkt_point(wkt: Optional[str]) -> Optional[Tuple[float, float]]:
    """Parses 'SRID=4326;POINT(lon lat)' or 'POINT(lon lat)' into (latitude, longitude)."""
    if not wkt or not isinstance(wkt, str):
        return None
    match = re.search(r"POINT\s*\(\s*([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s*\)", wkt.strip(), re.IGNORECASE)
    if not match:
        return None
    lon = float(match.group(1))
    lat = float(match.group(2))
    if not is_valid_coordinates(lat, lon):
        return None
    return lat, lon


def wgs84_geography_column_type():
    """
    PostgreSQL/PostGIS native GEOGRAPHY(POINT, 4326) column variant with
    explicitly separated TEXT EWKT storage for SQLite test runs (no mod_spatialite dependency).
    """
    return sa.Text().with_variant(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        "postgresql",
    )


def postgis_point_expr(latitude: float, longitude: float):
    """Builds a PostGIS GEOGRAPHY(POINT, 4326) SQL expression for ST_DWithin / ST_Distance."""
    if not is_valid_coordinates(latitude, longitude):
        raise ValueError(f"Invalid WGS84 coordinates: lat={latitude}, lon={longitude}")
    return func.ST_GeogFromText(format_geog_point_wkt(latitude, longitude))
