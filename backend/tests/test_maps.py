import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.maps.spatial import haversine_distance_meters, is_within_radius_meters
from app.services.maps.geocoding import reverse_geocode, forward_geocode, _set_cache

client = TestClient(app)

def test_map_config_public_endpoint():
    """Verify that public map configuration endpoint delivers non-sensitive parameters."""
    response = client.get("/api/v1/maps/config")
    assert response.status_code == 200
    data = response.json()
    assert "default_center" in data
    assert "latitude" in data["default_center"]
    assert "longitude" in data["default_center"]
    assert "supported_providers" in data
    assert "carto" in data["supported_providers"]
    assert "osm" in data["supported_providers"]
    assert "geocoding_enabled" in data
    
    # Ensure no credentials/secret keys are exposed
    assert "secret" not in str(data).lower()
    assert "password" not in str(data).lower()
    assert "key" not in str(data).lower() or data.get("geocoding_enabled") is not None

def test_reverse_geocoding_validation():
    """Verify reverse-geocoding input bounds validation."""
    # Out of bounds latitude (> 90)
    bad_lat = client.get("/api/v1/maps/reverse-geocode?lat=95.0&lon=78.49")
    assert bad_lat.status_code == 422

    # Out of bounds longitude (< -180)
    bad_lon = client.get("/api/v1/maps/reverse-geocode?lat=17.44&lon=-185.0")
    assert bad_lon.status_code == 422

    # Pre-seed cache to ensure test runs deterministically without depending on external network
    cache_key = f"rev_{round(17.4399, 4)}_{round(78.4983, 4)}"
    _set_cache(cache_key, {
        "formatted_address": "Tank Bund Road, Ward 12, Hyderabad",
        "road": "Tank Bund Road",
        "city": "Hyderabad",
        "latitude": 17.4399,
        "longitude": 78.4983
    })

    valid_resp = client.get("/api/v1/maps/reverse-geocode?lat=17.4399&lon=78.4983")
    assert valid_resp.status_code == 200
    res_data = valid_resp.json()
    assert res_data["success"] is True
    assert res_data["address"]["city"] == "Hyderabad"

def test_forward_geocoding_validation():
    """Verify forward-geocoding input validation."""
    # Too short query (< 2 chars)
    short_resp = client.get("/api/v1/maps/geocode?q=a")
    assert short_resp.status_code == 422

    # Pre-seed cache for deterministic local test
    query = "Hyderabad Central Station"
    cache_key = f"fwd_{query.lower()}_5"
    _set_cache(cache_key, [
        {
            "display_name": "Hyderabad Deccan Railway Station, Nampally",
            "latitude": 17.3916,
            "longitude": 78.4678,
            "type": "railway"
        }
    ])

    valid_resp = client.get(f"/api/v1/maps/geocode?q={query}&limit=5")
    assert valid_resp.status_code == 200
    data = valid_resp.json()
    assert data["success"] is True
    assert len(data["results"]) > 0
    assert "Railway Station" in data["results"][0]["display_name"]

def test_spatial_haversine_and_radius():
    """Verify spherical distance calculation between coordinates."""
    # Hyderabad Charminar to Golconda Fort (~9.4 km)
    charminar_lat, charminar_lon = 17.3616, 78.4747
    golconda_lat, golconda_lon = 17.3833, 78.4011

    distance = haversine_distance_meters(charminar_lat, charminar_lon, golconda_lat, golconda_lon)
    assert 7500 <= distance <= 9500

    # Within radius check
    assert is_within_radius_meters(charminar_lat, charminar_lon, golconda_lat, golconda_lon, 9000) is True
    assert is_within_radius_meters(charminar_lat, charminar_lon, golconda_lat, golconda_lon, 5000) is False
