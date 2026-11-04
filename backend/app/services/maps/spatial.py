import math
from typing import Tuple

def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes the great-circle distance between two geographic coordinates
    in meters using the spherical Haversine formula.
    """
    R = 6371000.0  # Earth's radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance = R * c
    return distance

def is_within_radius_meters(
    lat1: float, lon1: float, 
    lat2: float, lon2: float, 
    radius_meters: float
) -> bool:
    """Checks whether two points are within the specified radius in meters."""
    return haversine_distance_meters(lat1, lon1, lat2, lon2) <= radius_meters

