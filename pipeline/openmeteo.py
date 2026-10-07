"""Open-Meteo Marine and Weather (forecast) APIs.

Both accept many coordinates in one request, so all spots are fetched in a
single call per API. Responses are normalised to ft / mph / °F using the units
the API reports, so a units change upstream fails loudly instead of silently.
"""

from .config import FORECAST_DAYS, LOCAL_TZ
from .http import FetchError, get_json
from .units import normaliser

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

MARINE_HOURLY = [
    "wave_height", "wave_direction", "wave_period",
    # Peak period: what a buoy reports as dominant period, so the two compare.
    "wave_peak_period",
    "wind_wave_height", "wind_wave_direction", "wind_wave_period",
    "swell_wave_height", "swell_wave_direction", "swell_wave_period",
    "secondary_swell_wave_height", "secondary_swell_wave_direction",
    "secondary_swell_wave_period",
    "tertiary_swell_wave_height", "tertiary_swell_wave_direction",
    "tertiary_swell_wave_period",
    "sea_surface_temperature",
]

WEATHER_HOURLY = [
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    "temperature_2m", "weather_code",
]
WEATHER_DAILY = ["sunrise", "sunset"]


def _coords(points):
    return {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
    }


def marine_params(points, days: int = FORECAST_DAYS) -> dict:
    return {
        **_coords(points),
        "hourly": ",".join(MARINE_HOURLY),
        "length_unit": "imperial",
        "temperature_unit": "fahrenheit",
        "timezone": LOCAL_TZ,
        "timeformat": "unixtime",
        "forecast_days": days,
        "cell_selection": "sea",
    }


def weather_params(points, days: int = FORECAST_DAYS) -> dict:
    return {
        **_coords(points),
        "hourly": ",".join(WEATHER_HOURLY),
        "daily": ",".join(WEATHER_DAILY),
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",
        "timezone": LOCAL_TZ,
        "timeformat": "unixtime",
        "forecast_days": days,
    }


def _as_list(payload, n: int) -> list[dict]:
    if isinstance(payload, dict):
        if payload.get("error"):
            raise FetchError(f"Open-Meteo error: {payload.get('reason')}")
        payload = [payload]
    if not isinstance(payload, list) or len(payload) != n:
        got = len(payload) if isinstance(payload, list) else type(payload).__name__
        raise FetchError(f"Open-Meteo returned {got} locations, expected {n}")
    return payload


def _normalise_block(block: dict, units: dict, variables) -> dict:
    out = {"time": [int(t) for t in block["time"]]}
    for var in variables:
        if var not in block:
            raise FetchError(f"Open-Meteo response missing {var}")
        unit = units.get(var, "")
        if var == "weather_code":
            out[var] = block[var]
            continue
        if unit in ("", "undefined") and all(v is None for v in block[var]):
            # The model doesn't provide this variable (e.g. tertiary swell): all nulls.
            out[var] = list(block[var])
            continue
        try:
            conv = normaliser(unit)
        except ValueError as exc:
            raise FetchError(f"{var}: {exc}") from exc
        out[var] = [conv(v) for v in block[var]]
    return out


def parse_marine(payload, n: int) -> list[dict]:
    locations = _as_list(payload, n)
    return [
        _normalise_block(loc["hourly"], loc.get("hourly_units", {}), MARINE_HOURLY)
        for loc in locations
    ]


def parse_weather(payload, n: int) -> list[dict]:
    out = []
    for loc in _as_list(payload, n):
        hourly = _normalise_block(loc["hourly"], loc.get("hourly_units", {}), WEATHER_HOURLY)
        daily = loc.get("daily", {})
        hourly["sun"] = [
            {"date": int(d), "sunrise": int(r), "sunset": int(s)}
            for d, r, s in zip(
                daily.get("time", []), daily.get("sunrise", []), daily.get("sunset", []),
                strict=True,
            )
        ]
        out.append(hourly)
    return out


def fetch_marine(session, points, days: int = FORECAST_DAYS) -> list[dict]:
    return parse_marine(get_json(session, MARINE_URL, marine_params(points, days)), len(points))


def fetch_weather(session, points, days: int = FORECAST_DAYS) -> list[dict]:
    return parse_weather(
        get_json(session, WEATHER_URL, weather_params(points, days)), len(points)
    )
