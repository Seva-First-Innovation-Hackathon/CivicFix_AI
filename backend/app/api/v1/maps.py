from fastapi import APIRouter, Query, HTTPException, status
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.services.maps.geocoding import reverse_geocode, forward_geocode

router = APIRouter(prefix="/maps", tags=["Maps & Geospatial Services"])

@router.get("/config")
def get_public_map_configuration():
    """
    Returns safe, non-sensitive public map configuration parameters
    for frontend rendering and spatial alignment.
    """
    return {
        "geocoding_enabled": settings.MAP_GEOCODING_PROVIDER.lower() != "disabled",
        "geocoding_provider": settings.MAP_GEOCODING_PROVIDER,
        "default_center": {
            "latitude": settings.MAP_DEFAULT_CENTER_LAT,
            "longitude": settings.MAP_DEFAULT_CENTER_LON
        },
        "default_zoom": settings.MAP_DEFAULT_ZOOM,
        "supported_providers": ["carto", "osm", "maptiler", "custom"],
        "attribution_required": True
    }

@router.get("/reverse-geocode")
def api_reverse_geocode(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
):
    """
    Reverse-geocodes coordinate pair into structured street and neighborhood details.
    Guarantees privacy: no complaint content or user identity is relayed.
    """
    result = reverse_geocode(lat, lon)
    return result

@router.get("/geocode")
def api_forward_geocode(
    q: str = Query(..., min_length=2, max_length=120, description="Address or landmark query string"),
    limit: int = Query(5, ge=1, le=10, description="Maximum candidate results")
):
    """
    Searches coordinates by address or municipal landmark name.
    """
    result = forward_geocode(query=q, limit=limit)
    return result

