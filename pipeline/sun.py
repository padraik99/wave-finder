"""Sun times, a line-for-line port of app/js/sun.js (NOAA equations, after Meeus).

The app works out first and last light on the phone; the evening digest needs
the same daylight hours so its windows match the app's When to go card.
tests/cases/scoring.json holds cases both versions must agree on.
"""

import math

RAD = math.pi / 180
DAY = 86400

ALTITUDE = {"sunrise": -0.833, "civil": -6}


def _solar(unix: float) -> tuple[float, float]:
    jd = unix / DAY + 2440587.5
    T = (jd - 2451545) / 36525
    L0 = math.fmod(280.46646 + T * (36000.76983 + T * 0.0003032), 360)
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
    Mr = M * RAD
    C = (math.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T))
         + math.sin(2 * Mr) * (0.019993 - 0.000101 * T)
         + math.sin(3 * Mr) * 0.000289)
    omega = (125.04 - 1934.136 * T) * RAD
    lam = (L0 + C - 0.00569 - 0.00478 * math.sin(omega)) * RAD
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = (eps0 + 0.00256 * math.cos(omega)) * RAD
    decl = math.asin(math.sin(eps) * math.sin(lam))
    y = math.tan(eps / 2) ** 2
    L0r = L0 * RAD
    eq_time = 4 / RAD * (y * math.sin(2 * L0r) - 2 * e * math.sin(Mr)
                         + 4 * e * y * math.sin(Mr) * math.cos(2 * L0r)
                         - 0.5 * y * y * math.sin(4 * L0r) - 1.25 * e * e * math.sin(2 * Mr))
    return decl, eq_time


def js_round(x: float) -> int:
    """Math.round: halves go up (Python's round() sends them to even)."""
    return math.floor(x + 0.5)


def sun_event(local_noon: int, lat: float, lon: float, altitude: float,
              rising: bool) -> int | None:
    utc_day = (local_noon // DAY) * DAY
    t = local_noon
    for _ in range(3):
        decl, eq_time = _solar(t)
        cos_h = ((math.sin(altitude * RAD) - math.sin(lat * RAD) * math.sin(decl))
                 / (math.cos(lat * RAD) * math.cos(decl)))
        if cos_h < -1 or cos_h > 1:
            return None
        H = math.acos(cos_h) / RAD
        minutes = 720 - 4 * (lon + (H if rising else -H)) - eq_time
        t = utc_day + minutes * 60
    return js_round(t)


def sun_times(local_midnight: int, lat: float, lon: float) -> dict:
    noon = local_midnight + 12 * 3600
    return {
        "firstLight": sun_event(noon, lat, lon, ALTITUDE["civil"], True),
        "sunrise": sun_event(noon, lat, lon, ALTITUDE["sunrise"], True),
        "sunset": sun_event(noon, lat, lon, ALTITUDE["sunrise"], False),
        "lastLight": sun_event(noon, lat, lon, ALTITUDE["civil"], False),
    }
