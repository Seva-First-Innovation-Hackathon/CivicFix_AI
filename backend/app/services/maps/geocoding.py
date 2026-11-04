"""
CivicFix AI — Provider-Independent Spatial Geocoding Service

Provides privacy-preserving forward and reverse geocoding with:
1. Upstream rate-limiting and in-memory TTL caching (Nominatim 1 req/sec policy).
2. Privacy isolation: NEVER forwards complaint titles, descriptions, citizen names, or private notes.
3. Fail-safe fallback: Network/quota failures return structured degraded responses without crashing callers.
"""
import time
import logging
from typing import Optional, Dict, Any, List
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory LRU / TTL cache: key -> (timestamp, data)
_CACHE: Dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 3600 * 24  # 24 hours for geographical coordinates
_LAST_REQUEST_TIME = 0.0
_MIN_REQUEST_INTERVAL = 1.05  # Nominatim terms: maximum 1 request per second

def _get_cache(key: str) -> Optional[Any]:
    now = time.time()
    if key in _CACHE:
        ts, data = _CACHE[key]
        if now - ts < _CACHE_TTL_SECONDS:
            return data
        else:
            del _CACHE[key]
    return None

def _set_cache(key: str, data: Any):
    _CACHE[key] = (time.time(), data)
    # Prevent unbound memory growth
    if len(_CACHE) > 2000:
        oldest = sorted(_CACHE.items(), key=lambda x: x[1][0])[:500]
        for k, _ in oldest:
            _CACHE.pop(k, None)

def _throttle():
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _LAST_REQUEST_TIME = time.time()

def reverse_geocode(lat: float, lon: float) -> Dict[str, Any]:
    """
    Reverse geocodes latitude and longitude to a human-readable street address.
    Strictly isolated: only coordinates are transmitted to external providers.
    """
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return {
            "success": False,
            "address": None,
            "error": "Invalid coordinates range"
        }

    # Cache key rounded to ~11 meters precision to coalesce nearby lookups
    cache_key = f"rev_{round(lat, 4)}_{round(lon, 4)}"
    cached = _get_cache(cache_key)
    if cached:
        return {"success": True, "address": cached, "cached": True}

    provider = settings.MAP_GEOCODING_PROVIDER.lower()
    if provider == "disabled":
        return {
            "success": False,
            "address": None,
            "message": "Geocoding service is administratively disabled"
        }

    if provider == "nominatim":
        try:
            _throttle()
            headers = {
                "User-Agent": settings.MAP_GEOCODING_USER_AGENT,
                "Accept": "application/json"
            }
            params = {
                "lat": lat,
                "lon": lon,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 18
            }
            url = f"{settings.NOMINATIM_BASE_URL.rstrip('/')}/reverse"
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    display_name = data.get("display_name", "")
                    addr_details = data.get("address", {})
                    
                    # Synthesize clean localized street address
                    road = addr_details.get("road") or addr_details.get("pedestrian") or addr_details.get("path") or ""
                    suburb = addr_details.get("suburb") or addr_details.get("neighbourhood") or addr_details.get("residential") or ""
                    city = addr_details.get("city") or addr_details.get("town") or addr_details.get("county") or ""
                    postcode = addr_details.get("postcode", "")

                    parts = [p for p in [road, suburb, city, postcode] if p]
                    formatted_address = ", ".join(parts) if parts else display_name

                    result = {
                        "formatted_address": formatted_address or f"{lat:.4f}, {lon:.4f}",
                        "raw_display_name": display_name,
                        "road": road,
                        "suburb": suburb,
                        "city": city,
                        "postcode": postcode,
                        "latitude": lat,
                        "longitude": lon
                    }
                    _set_cache(cache_key, result)
                    return {"success": True, "address": result, "cached": False}
                elif resp.status_code == 429:
                    logger.warning("Upstream geocoding provider rate-limit (429) hit.")
                    return {"success": False, "address": None, "error": "Geocoding rate limit exceeded"}
        except Exception as exc:
            logger.warning(f"Reverse geocode lookup failed gracefully: {exc}")
            return {"success": False, "address": None, "error": str(exc)}

    return {"success": False, "address": None, "error": f"Unsupported geocoding provider '{provider}'"}

def forward_geocode(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Forward geocodes an address or landmark search query to coordinate candidates.
    """
    clean_query = query.strip()
    if len(clean_query) < 2 or len(clean_query) > 120:
        return {"success": False, "results": [], "error": "Query must be between 2 and 120 characters"}

    cache_key = f"fwd_{clean_query.lower()}_{limit}"
    cached = _get_cache(cache_key)
    if cached:
        return {"success": True, "results": cached, "cached": True}

    provider = settings.MAP_GEOCODING_PROVIDER.lower()
    if provider == "disabled":
        return {"success": False, "results": [], "message": "Geocoding disabled"}

    if provider == "nominatim":
        try:
            _throttle()
            headers = {
                "User-Agent": settings.MAP_GEOCODING_USER_AGENT,
                "Accept": "application/json"
            }
            params = {
                "q": clean_query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": min(limit, 10)
            }
            url = f"{settings.NOMINATIM_BASE_URL.rstrip('/')}/search"
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    items = resp.json()
                    results = []
                    for item in items:
                        try:
                            results.append({
                                "display_name": item.get("display_name"),
                                "latitude": float(item.get("lat")),
                                "longitude": float(item.get("lon")),
                                "type": item.get("type"),
                                "importance": item.get("importance", 0.0)
                            })
                        except (ValueError, TypeError):
                            continue
                    _set_cache(cache_key, results)
                    return {"success": True, "results": results, "cached": False}
        except Exception as exc:
            logger.warning(f"Forward geocode failed gracefully: {exc}")
            return {"success": False, "results": [], "error": str(exc)}

    return {"success": False, "results": [], "error": f"Unsupported provider '{provider}'"}

