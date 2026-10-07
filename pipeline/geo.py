"""Distance, bearing and direction helpers. Directions are compass degrees (0 = N)."""

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def destination(lat: float, lon: float, bearing_deg: float, distance_km: float):
    """Point reached by travelling distance_km from (lat, lon) along bearing_deg."""
    d = distance_km / EARTH_RADIUS_KM
    b = math.radians(bearing_deg)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2)
    )
    return round(math.degrees(p2), 4), round((math.degrees(l2) + 540) % 360 - 180, 4)


def angle_diff(a: float, b: float) -> float:
    """Smallest angle between two directions, 0..180."""
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def in_window(direction: float | None, start: float, end: float) -> bool | None:
    """True if direction lies clockwise from start to end (inclusive). Handles wrap past north."""
    if direction is None:
        return None
    direction, start, end = direction % 360, start % 360, end % 360
    if start <= end:
        return start <= direction <= end
    return direction >= start or direction <= end


# Wind within this many degrees of straight onshore/offshore gets that label;
# anything between is "cross".
WIND_SECTOR_DEG = 67.5


def wind_relation(wind_from: float | None, facing: float) -> str | None:
    """Label wind as offshore, cross or onshore for a beach facing `facing` degrees.

    Wind direction is where the wind comes FROM (meteorological convention).
    Wind from the sea (same direction the beach faces) is onshore.
    """
    if wind_from is None:
        return None
    diff = angle_diff(wind_from, facing)
    if diff <= WIND_SECTOR_DEG:
        return "onshore"
    if diff >= 180 - WIND_SECTOR_DEG:
        return "offshore"
    return "cross"


COMPASS_POINTS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def compass_to_deg(point: str) -> float | None:
    try:
        return COMPASS_POINTS.index(point.strip().upper()) * 22.5
    except ValueError:
        return None
