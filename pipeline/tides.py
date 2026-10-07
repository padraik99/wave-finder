"""NOAA CO-OPS tide predictions.

We request high/low predictions (works for both harmonic and subordinate
stations) and fill hourly heights with cosine interpolation between extremes,
the standard approximation for a smooth tide curve.
"""

import math
import time
from datetime import UTC, date, datetime, timedelta

from .http import FetchError, get_json

COOPS_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
METADATA_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{id}.json"


def params(station: str, begin: date, days: int) -> dict:
    end = begin + timedelta(days=days)
    return {
        "product": "predictions",
        "application": "wave-finder",
        "station": station,
        "begin_date": begin.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "datum": "MLLW",
        "time_zone": "gmt",
        "units": "english",
        "interval": "hilo",
        "format": "json",
    }


def parse_hilo(payload: dict) -> list[dict]:
    if "error" in payload:
        raise FetchError(f"CO-OPS error: {payload['error'].get('message')}")
    preds = payload.get("predictions")
    if not preds:
        raise FetchError("CO-OPS returned no predictions")
    out = []
    for p in preds:
        t = datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        out.append({"t": int(t.timestamp()), "v": round(float(p["v"]), 2), "type": p["type"]})
    out.sort(key=lambda e: e["t"])
    return out


def interpolate_hourly(extremes: list[dict]) -> dict:
    """Hourly heights on the hour between the first and last extreme.

    Between consecutive extremes (t0, v0) and (t1, v1):
        v(t) = (v0 + v1)/2 + (v0 - v1)/2 * cos(pi * (t - t0) / (t1 - t0))
    "rising" is true when the next extreme is a high.
    """
    times, heights, rising = [], [], []
    if len(extremes) < 2:
        return {"time": times, "height": heights, "rising": rising}
    t = math.ceil(extremes[0]["t"] / 3600) * 3600
    i = 0
    while t <= extremes[-1]["t"]:
        while extremes[i + 1]["t"] < t:
            i += 1
        e0, e1 = extremes[i], extremes[i + 1]
        frac = (t - e0["t"]) / (e1["t"] - e0["t"])
        v = (e0["v"] + e1["v"]) / 2 + (e0["v"] - e1["v"]) / 2 * math.cos(math.pi * frac)
        times.append(t)
        heights.append(round(v, 2))
        rising.append(e1["type"] == "H")
        t += 3600
    return {"time": times, "height": heights, "rising": rising}


# CO-OPS sometimes answers a valid request with an error inside an HTTP 200
# ("No Predictions data was found...") and succeeds seconds later, so the HTTP
# layer's retries never see it. Retry those a couple of times before failing.
RETRY_DELAYS_S = (2, 5)


def fetch(session, station: str, begin: date, days: int, sleep=time.sleep) -> dict:
    for delay in (*RETRY_DELAYS_S, None):
        try:
            extremes = parse_hilo(get_json(session, COOPS_URL, params(station, begin, days)))
            break
        except FetchError:
            if delay is None:
                raise
            sleep(delay)
    return {
        "station": station,
        "datum": "MLLW",
        "units": "ft",
        "extremes": extremes,
        "hourly": interpolate_hourly(extremes),
    }


def fetch_metadata(session, station: str) -> dict:
    """Station name and coordinates from the CO-OPS metadata API (used by verify)."""
    payload = get_json(session, METADATA_URL.format(id=station))
    stations = payload.get("stations") or []
    if not stations:
        raise FetchError(f"CO-OPS has no metadata for station {station}")
    s = stations[0]
    return {"name": s.get("name"), "lat": s.get("lat"), "lon": s.get("lng")}
