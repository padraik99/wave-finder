"""How good is an hour, and when to go: a port of the scoring in app/js/model.js.

The evening digest has to name the same Good windows the app shows, so this
follows model.js step for step (same arithmetic, same tie-breaks, same
Math.round). tests/cases/scoring.json holds cases both versions must pass;
change one side and that file tells you the other needs the same change.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .config import LOCAL_TZ
from .sun import js_round, sun_times

HOUR = 3600
TZ = ZoneInfo(LOCAL_TZ)


def local_day_key(u: int) -> str:
    return datetime.fromtimestamp(u, UTC).astimezone(TZ).strftime("%Y-%m-%d")


def hour_index(times: list[int], t: float) -> int:
    if not times:
        return -1
    if t < times[0]:
        return 0
    lo, hi = 0, len(times) - 1
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if times[mid] <= t:
            lo = mid
        else:
            hi = mid - 1
    return lo


def tide_height_at(tide: dict | None, t: int) -> float | None:
    """Interpolated tide height at t, rounded to 0.1 ft like tideAt. None if outside."""
    hourly = (tide or {}).get("hourly") or {}
    time, height = hourly.get("time") or [], hourly.get("height") or []
    if not time:
        return None
    i = hour_index(time, t)
    if t < time[0] or t > time[-1] + HOUR:
        return None
    h = height[i]
    if i + 1 < len(time) and height[i] is not None and height[i + 1] is not None:
        f = (t - time[i]) / (time[i + 1] - time[i])
        h = height[i] + (height[i + 1] - height[i]) * min(max(f, 0), 1)
    return None if h is None else js_round(h * 10) / 10


def tide_classes(tide: dict | None, times: list[int]) -> list[str | None]:
    hourly = (tide or {}).get("hourly") or {}
    if not hourly.get("time"):
        return [None] * len(times)
    rng: dict[str, tuple[float, float]] = {}
    for u, v in zip(hourly["time"], hourly["height"], strict=True):
        if v is None:
            continue
        key = local_day_key(u)
        lo, hi = rng.get(key, (float("inf"), float("-inf")))
        rng[key] = (min(lo, v), max(hi, v))
    out = []
    for t in times:
        h = tide_height_at(tide, t)
        r = rng.get(local_day_key(t))
        if h is None or r is None:
            out.append(None)
            continue
        lo, hi = r
        if not hi > lo:
            out.append("mid")
            continue
        f = (h - lo) / (hi - lo)
        out.append("low" if f < 1 / 3 else "high" if f > 2 / 3 else "mid")
    return out


TIDE_OK = {
    "low": ["low"], "low_to_mid": ["low", "mid"], "mid": ["mid"],
    "mid_to_high": ["mid", "high"], "high": ["high"], "any": ["low", "mid", "high"],
}


def tide_suits(pref: str | None, cls: str | None) -> bool | None:
    if cls is None or pref not in TIDE_OK:
        return None
    return cls in TIDE_OK[pref]


def size_score(h: float | None, mode: str = "surf", expert: bool = False) -> float:
    if h is None:
        return 0
    if expert:
        return min(max(h / 18, 0), 1)
    if mode == "bb":
        if h < 1:
            return 0.1
        if h < 2.5:
            return 0.3 + ((h - 1) / 1.5) * 0.7
        if h <= 5:
            return 1
        if h <= 8:
            return 1 - ((h - 5) / 3) * 0.6
        return 0.2
    if h < 1:
        return 0.05
    if h <= 6:
        return h / 6
    if h <= 10:
        return 1
    return max(0.3, 1 - (h - 10) / 8)


WIND_FACTOR = {"offshore": 1, "cross": 0.75, "onshore": 0.45}


def wind_score(rel: str | None, mph: float | None) -> float:
    f = WIND_FACTOR.get(rel, 0.5)
    if mph is not None and mph < 5:
        f = max(f, 0.95)
    if rel == "onshore" and mph is not None and mph > 15:
        f = 0.25
    return f


def hour_score(h, rel, mph, tide_ok=None, mode="surf", expert=False) -> float:
    return size_score(h, mode, expert) * wind_score(rel, mph) * (0.8 if tide_ok is False else 1)


def score_label(s: float) -> str:
    return "Good" if s >= 0.75 else "Fair" if s >= 0.55 else "Poor"


def when_to_go(fc: dict, tide: dict | None, spot: dict, start: int,
               is_daylight: Callable[[int], bool], mode: str = "surf", hours: int = 72,
               max_n: int = 3) -> list[dict]:
    """Best daylight windows from `start` for `hours`, as whenToGo returns them."""
    expert = spot.get("skill") == "expert_only"
    times = fc["time"]
    first = max(hour_index(times, start), 0)
    classes = tide_classes(tide, times)
    scored: list[dict | None] = []
    i = first
    while i < len(times) and times[i] < start + hours * HOUR:
        t = times[i]
        if not is_daylight(t):
            scored.append(None)
            i += 1
            continue
        h = fc["marine"]["wave_height"][i]
        rel = fc["derived"]["wind_relation"][i]
        mph = fc["weather"]["wind_speed_10m"][i]
        cls = classes[i]
        scored.append({
            "i": i, "t": t, "cls": cls, "h": h, "rel": rel, "mph": mph,
            "score": hour_score(h, rel, mph, tide_suits(spot.get("tide_preference"), cls),
                                mode, expert),
        })
        i += 1

    runs: list[list[dict]] = []
    run: list[dict] = []
    for x in scored:
        if not x or x["score"] < 0.4:
            if run:
                runs.append(run)
            run = []
            continue
        if run and x["score"] < 0.85 * max(r["score"] for r in run):
            runs.append(run)
            run = []
        run.append(x)
    if run:
        runs.append(run)

    wins = []
    for r in runs:
        peak = r[0]
        for b in r[1:]:
            if b["score"] > peak["score"]:
                peak = b
        wins.append({"start": r[0]["t"], "end": r[-1]["t"] + HOUR, "peak": peak,
                     "score": peak["score"], "label": score_label(peak["score"])})
    wins.sort(key=lambda w: -w["score"])
    return sorted(wins[:max_n], key=lambda w: w["start"])


def daylight_for(fc: dict, lat: float, lon: float) -> Callable[[int], bool]:
    """isDaylight as the spot page builds it: from 30 min before first light to
    last light, on the local days the forecast's sun list covers."""
    days = {}
    for d in fc.get("sun") or []:
        days.setdefault(local_day_key(d["date"] + 12 * 3600), sun_times(d["date"], lat, lon))

    def is_daylight(t: int) -> bool:
        d = days.get(local_day_key(t))
        if not d or d["firstLight"] is None or d["lastLight"] is None:
            return False
        return d["firstLight"] - 1800 <= t < d["lastLight"]

    return is_daylight
