"""Mavericks Watch: switches on for a big forecast, then watches the buoys.

    python -m pipeline.mavericks --data data --state state/mavericks.json

Runs every 30 minutes (cron-job.org, GitHub's schedule as backup). Each run:

1. Idle: reads the published Mavericks forecast. Any hour at or above the
   spot's big_wave.min_ft (15 ft) within 5 days switches the watch on, with
   one ntfy message saying when the peak is due.
2. On: fetches only the three buoys between the storm and Pillar Point
   (46059 far offshore, 46214 Point Reyes, 46012 Half Moon Bay; NDBC, no
   Open-Meteo call). The first time 46059 shows forerunners (18 s or longer
   period) it pings once, comparing the period it measured with the forecast
   for 46059's own position at that hour.
3. Stands down, with a message, once no hour in the next 5 days reaches the
   threshold and either 12 hours have passed since the last big forecast hour
   (the swell has gone through) or the forecast has dropped below 14 ft before
   arriving (a downgrade). Then a new swell can switch it on again.

State is a small JSON file kept on the `watch` branch; this is its only writer.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from . import buoys, ntfy
from .config import SPOTS_FILE
from .http import make_session
from .run import read_json, write_json
from .score import TZ

SPOT_ID = "mavericks"
DEFAULT_MIN_FT = 15
LOOKAHEAD_H = 120
FORERUNNER_S = 18
OFFSHORE = "46059"
WATCH_BUOYS = ("46059", "46214", "46012")
PASSED_AFTER_H = 12
DOWNGRADE_FT = 14
READING_MAX_AGE_H = 3
FORECAST_MATCH_S = 90 * 60
HOUR = 3600


def local_str(u: int) -> str:
    t = datetime.fromtimestamp(u, UTC).astimezone(TZ)
    h = t.hour % 12 or 12
    return f"{t:%a} {h}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"


def ahead(fc: dict | None, now: int, hours: int = LOOKAHEAD_H) -> list[tuple[int, float]]:
    """(time, wave height ft) for forecast hours from the current hour to `hours` ahead."""
    if not fc or not fc.get("time"):
        return []
    hour = now - now % HOUR
    return [(t, h) for t, h in zip(fc["time"], fc["marine"]["wave_height"], strict=True)
            if hour <= t <= now + hours * HOUR and h is not None]


def forecast_at(buoy_fc: dict | None, t: int) -> dict | None:
    """The forecast for the buoy's own position nearest to t (within 90 min)."""
    if not buoy_fc or not buoy_fc.get("time"):
        return None
    k = min(range(len(buoy_fc["time"])), key=lambda i: abs(buoy_fc["time"][i] - t))
    if abs(buoy_fc["time"][k] - t) > FORECAST_MATCH_S:
        return None
    return {key: buoy_fc.get(key, [None] * (k + 1))[k] for key in
            ("time", "swell_wave_period", "wave_period", "swell_wave_height", "wave_height")}


def reading(summary: dict | None, now: int) -> dict | None:
    """Latest wave reading if it is recent enough to trust."""
    obs = (summary or {}).get("latest")
    if not obs or now - obs["time"] > READING_MAX_AGE_H * HOUR:
        return None
    return obs


def long_period(summary: dict | None, now: int) -> tuple[float | None, dict | None]:
    """Longest period 46059 is showing right now: the dominant period, or the
    swell part of the spectrum if that is longer."""
    obs = reading(summary, now)
    if not obs:
        return None, None
    best = obs.get("dominant_period_s")
    spec = (summary or {}).get("latest_spectral")
    if spec and now - spec["time"] <= READING_MAX_AGE_H * HOUR:
        sp = spec.get("swell_period_s")
        if sp is not None and (best is None or sp > best):
            best = sp
    return best, obs


def buoy_line(bid: str, name: str, summary: dict | None, now: int) -> str:
    obs = reading(summary, now)
    if not obs:
        return f"{bid} {name}: no recent reading"
    h = obs.get("wave_height_ft")
    p = obs.get("dominant_period_s")
    return (f"{bid} {name}: {'–' if h is None else f'{h:.1f}'} ft @ "
            f"{'–' if p is None else round(p)} s ({local_str(obs['time'])})")


def compare_line(period: float, buoy_fc: dict | None, t: int) -> str:
    f = forecast_at(buoy_fc, t)
    fp = f and (f["swell_wave_period"] or f["wave_period"])
    if not fp:
        return "No forecast for 46059's position at that hour to compare with."
    gap = period - fp
    verdict = ("about as forecast" if abs(gap) < 2
               else "longer than forecast: the swell may be ahead of schedule or bigger"
               if gap > 0 else "shorter than forecast")
    return (f"Forecast at 46059 for that hour: {fp:.0f} s swell period. "
            f"Measured {period:.0f} s, {verdict}.")


def step(state: dict | None, fc: dict | None, buoy_fc: dict | None, now: int,
         fetch: Callable[[str], dict | None], names: dict[str, str],
         min_ft: float = DEFAULT_MIN_FT) -> tuple[dict, list[dict]]:
    """One check. Returns the new state and the messages to send
    ({title, message, priority, tags})."""
    state = dict(state or {"status": "idle"})
    msgs: list[dict] = []
    hours = ahead(fc, now)
    big = [(t, h) for t, h in hours if h >= min_ft]
    peak = max(hours, key=lambda x: x[1]) if hours else None

    if state.get("status") != "armed":
        if not big:
            return state, []
        bt, bh = max(big, key=lambda x: x[1])
        state = {"status": "armed", "armed_at": now, "peak_ft": bh, "peak_t": bt,
                 "last_big_t": big[-1][0], "forerunners_at": None}
        msgs.append({
            "title": "Mavericks Watch on",
            "message": (f"Forecast at Mavericks reaches {bh:.0f} ft around {local_str(bt)}. "
                        f"Watching buoys {', '.join(WATCH_BUOYS)} every 30 min for "
                        f"forerunners ({FORERUNNER_S} s+ at {OFFSHORE})."),
            "priority": "high", "tags": "ocean,eyes",
        })
    else:
        if big:
            state["last_big_t"] = big[-1][0]
            bt, bh = max(big, key=lambda x: x[1])
            state["peak_ft"], state["peak_t"] = bh, bt
        else:
            top = peak[1] if peak else 0
            passed = now >= state.get("last_big_t", 0) + PASSED_AFTER_H * HOUR
            downgraded = state.get("last_big_t", 0) > now and top < DOWNGRADE_FT
            if passed or downgraded:
                why = ("the swell has passed" if passed else
                       f"the forecast dropped to {top:.0f} ft before it arrived")
                msgs.append({
                    "title": "Mavericks Watch off",
                    "message": (f"Standing down: {why}. Peak forecast was "
                                f"{state.get('peak_ft', 0):.0f} ft "
                                f"({local_str(state.get('peak_t', now))})."),
                    "priority": "default", "tags": "ocean",
                })
                return {"status": "idle", "last_watch": {
                    k: state.get(k) for k in ("armed_at", "peak_ft", "peak_t", "forerunners_at")
                } | {"ended_at": now}}, msgs

    # Armed: buoy-only check.
    readings = {bid: fetch(bid) for bid in WATCH_BUOYS}
    for bid in WATCH_BUOYS:
        print("  " + buoy_line(bid, names.get(bid, ""), readings[bid], now))
    if not state.get("forerunners_at"):
        period, obs = long_period(readings[OFFSHORE], now)
        if period is not None and period >= FORERUNNER_S:
            state["forerunners_at"] = now
            state["forerunner"] = {"t": obs["time"], "period_s": period,
                                   "height_ft": obs.get("wave_height_ft")}
            lines = [
                f"46059 (about 400 mi west of Pillar Point) shows {period:.0f} s at "
                f"{local_str(obs['time'])}: the long-period front of the swell is on its way.",
                compare_line(period, buoy_fc, obs["time"]),
                *(buoy_line(b, names.get(b, ""), readings[b], now) for b in WATCH_BUOYS[1:]),
                f"Peak forecast at Mavericks: {state['peak_ft']:.0f} ft around "
                f"{local_str(state['peak_t'])}.",
            ]
            msgs.append({"title": "Mavericks forerunners at 46059", "message": "\n".join(lines),
                         "priority": "high", "tags": "ocean,rotating_light"})
    return state, msgs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--state", type=Path, default=Path("state/mavericks.json"))
    args = ap.parse_args(argv)
    now = int(time.time())
    doc = json.loads(SPOTS_FILE.read_text("utf-8"))
    spot = next(s for s in doc["spots"] if s["id"] == SPOT_ID)
    min_ft = (spot.get("big_wave") or {}).get("min_ft", DEFAULT_MIN_FT)
    names = {b: doc["buoys"].get(b, {}).get("name", "") for b in WATCH_BUOYS}
    fc = read_json(args.data / "forecast" / f"{SPOT_ID}.json")
    buoy_fc = (read_json(args.data / "buoys" / f"{OFFSHORE}.json") or {}).get("forecast")
    if not fc:
        print("No Mavericks forecast in the data; keeping state as it is.")
        return 0
    session = make_session()

    def fetch(bid: str) -> dict | None:
        try:
            return buoys.fetch(session, bid, now)
        except Exception as exc:
            print(f"  {bid}: fetch failed: {type(exc).__name__}: {exc}"[:300])
            return None

    prev = read_json(args.state)
    state, msgs = step(prev, fc, buoy_fc, now, fetch, names, min_ft)
    print(f"Mavericks Watch: {state['status']}"
          + (f", peak {state['peak_ft']:.0f} ft {local_str(state['peak_t'])}"
             if state["status"] == "armed" else ""))
    for m in msgs:
        print(f"Sending: {m['title']}\n{m['message']}")
        ntfy.send(session, m["title"], m["message"], priority=m["priority"], tags=m["tags"])
    if state != prev:
        write_json(args.state, state)
        print("State changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
