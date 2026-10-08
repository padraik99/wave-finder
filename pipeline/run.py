"""Fetch every source and write the JSON the app reads.

    python -m pipeline.run --out data

Output layout (all under --out):
  index.json             spot list with the buoy currently in use for each spot,
                         plus a 72 h outlook so the app's spot list needs no other file
  meta.json              when each source last succeeded, errors, attribution
  forecast/<spot>.json   hourly marine + wind forecast for one spot
  tides/<station>.json   high/low tides plus hourly heights
  buoys/<id>.json        latest observation, the last 48 h, and the marine forecast
                         at the buoy itself, so readings compare like for like

A failing source never wipes good data: the previous file stays in place and
meta.json records the failure. Only a run where every source fails exits non-zero.
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import buoys, openmeteo, spots, tides
from .config import ATTRIBUTION, BUOY_LIVE_HOURS, FORECAST_DAYS, SPOTS_FILE
from .geo import in_window, wind_relation
from .http import make_session

UNITS = {"height": "ft", "period": "s", "direction": "deg_from", "speed": "mph", "temp": "F",
         "time": "unix_utc"}


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"), ensure_ascii=False)
    tmp.replace(path)


def _section_from_previous(prev: dict | None, key: str) -> dict | None:
    if not prev or not prev.get(key):
        return None
    return {"time": prev["time"], **prev[key]}


def _align(section: dict | None, times: list[int], variables) -> dict:
    if not section:
        return {v: [None] * len(times) for v in variables}
    out = {}
    for v in variables:
        lookup = dict(zip(section["time"], section[v], strict=True))
        out[v] = [lookup.get(t) for t in times]
    return out


def build_forecast(spot: dict, marine: dict | None, weather: dict | None,
                   marine_updated: str | None, weather_updated: str | None,
                   sun: list | None) -> dict | None:
    master = marine or weather
    if not master:
        return None
    times = master["time"]
    m = _align(marine, times, openmeteo.MARINE_HOURLY)
    w = _align(weather, times, [v for v in openmeteo.WEATHER_HOURLY])
    win = spot["swell_window"]
    return {
        "spot_id": spot["id"],
        "marine_updated": marine_updated,
        "weather_updated": weather_updated,
        "units": UNITS,
        "time": times,
        "marine": m,
        "weather": w,
        "derived": {
            "wind_relation": [wind_relation(d, spot["facing_deg"])
                              for d in w["wind_direction_10m"]],
            "swell_in_window": [in_window(d, win["from"], win["to"])
                                for d in m["swell_wave_direction"]],
        },
        "sun": sun or [],
    }


# Hours of forecast summarised per spot in index.json, so the app's spot list
# can show every spot from one small file.
OUTLOOK_HOURS = 72
_RELATION_CODE = {"offshore": "o", "cross": "c", "onshore": "n"}


def build_outlook(fc: dict | None, now: int, hours: int = OUTLOOK_HOURS) -> dict | None:
    """Hourly wave height, wind speed and wind label from the current hour on."""
    if not fc:
        return None
    hour = now - now % 3600
    times = fc["time"]
    start = next((i for i, t in enumerate(times) if t >= hour), None)
    if start is None:
        return None
    sl = slice(start, start + hours)
    return {
        "start": times[start],
        "wave_height": fc["marine"]["wave_height"][sl],
        "wind_speed": fc["weather"]["wind_speed_10m"][sl],
        "wind": "".join(_RELATION_CODE.get(r, "-") for r in fc["derived"]["wind_relation"][sl]),
    }


# Forecast variables kept at each buoy's location, and how far ahead.
BUOY_FORECAST_VARS = [
    # No wave_peak_period: Open-Meteo returns it all-null for this coast (checked
    # 2026-10-07), so period compares the buoy's dominant with the mean.
    "wave_height", "wave_period", "wave_direction",
    "swell_wave_height", "swell_wave_period", "swell_wave_direction",
    "sea_surface_temperature",
]
BUOY_FORECAST_AHEAD_HOURS = 48


def build_buoy_forecast(marine: dict | None, now: int, updated: str) -> dict | None:
    """Marine forecast at a buoy, from the start of the forecast to 48 h ahead."""
    if not marine:
        return None
    end = now + BUOY_FORECAST_AHEAD_HOURS * 3600
    keep = [i for i, t in enumerate(marine["time"]) if t <= end]
    return {
        "updated": updated,
        "time": [marine["time"][i] for i in keep],
        **{v: [marine[v][i] for i in keep] for v in BUOY_FORECAST_VARS},
    }


def _status(prev_meta: dict, path: tuple, ok: bool, now: int, error: str | None = None,
            **extra) -> dict:
    node = prev_meta.get("sources", {})
    for key in path:
        node = (node or {}).get(key, {})
    last_success = iso(now) if ok else (node or {}).get("last_success")
    return {"ok": ok, "last_success": last_success, "error": error, **extra}


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


def run(out: Path, session, now: int | None = None, spots_file: Path = SPOTS_FILE,
        forecast_days: int = FORECAST_DAYS) -> int:
    now = int(now if now is not None else time.time())
    doc = spots.load(spots_file)
    prev_meta = read_json(out / "meta.json") or {}
    sources: dict = {"tides": {}, "buoys": {}}
    any_ok = False

    # --- Open-Meteo: one request per API covering every spot (and buoy) --------
    spot_list = doc["spots"]
    buoy_ids = spots.used_buoys(doc)
    marine_points = [spots.forecast_point(s) for s in spot_list]
    marine_points += [(doc["buoys"][b]["lat"], doc["buoys"][b]["lon"]) for b in buoy_ids]
    beach_points = [(s["lat"], s["lon"]) for s in spot_list]
    buoy_marine: dict = {}
    try:
        marine_all = openmeteo.fetch_marine(session, marine_points, forecast_days)
        buoy_marine = dict(zip(buoy_ids, marine_all[len(spot_list):], strict=True))
        marine_all = marine_all[:len(spot_list)]
        sources["marine"] = _status(prev_meta, ("marine",), True, now)
    except Exception as exc:
        marine_all = None
        sources["marine"] = _status(prev_meta, ("marine",), False, now, _err(exc))
    try:
        weather_all = openmeteo.fetch_weather(session, beach_points, forecast_days)
        sources["weather"] = _status(prev_meta, ("weather",), True, now)
    except Exception as exc:
        weather_all = None
        sources["weather"] = _status(prev_meta, ("weather",), False, now, _err(exc))
    any_ok |= sources["marine"]["ok"] or sources["weather"]["ok"]

    forecasts = {}
    for i, spot in enumerate(spot_list):
        path = out / "forecast" / f"{spot['id']}.json"
        prev = read_json(path)
        if marine_all:
            marine, marine_updated = marine_all[i], iso(now)
        else:
            marine = _section_from_previous(prev, "marine")
            marine_updated = prev.get("marine_updated") if prev else None
        if weather_all:
            weather = {k: v for k, v in weather_all[i].items() if k != "sun"}
            sun, weather_updated = weather_all[i]["sun"], iso(now)
        else:
            weather = _section_from_previous(prev, "weather")
            sun = prev.get("sun") if prev else None
            weather_updated = prev.get("weather_updated") if prev else None
        fc = build_forecast(spot, marine, weather, marine_updated, weather_updated, sun)
        if fc:
            write_json(path, fc)
        forecasts[spot["id"]] = fc

    # --- Tides: one request per station ---------------------------------------
    begin = (datetime.fromtimestamp(now, UTC) - timedelta(days=1)).date()
    for station in spots.used_tide_stations(doc):
        try:
            data = tides.fetch(session, station, begin, forecast_days + 1)
            data["name"] = doc["tide_stations"][station]["name"]
            data["updated"] = iso(now)
            write_json(out / "tides" / f"{station}.json", data)
            sources["tides"][station] = _status(prev_meta, ("tides", station), True, now)
            any_ok = True
        except Exception as exc:
            sources["tides"][station] = _status(prev_meta, ("tides", station), False, now,
                                                _err(exc))

    # --- Buoys ----------------------------------------------------------------
    summaries = {}
    for buoy_id in buoy_ids:
        try:
            summary = buoys.fetch(session, buoy_id, now)
            summary["name"] = doc["buoys"][buoy_id]["name"]
            summary["updated"] = iso(now)
            if buoy_id in buoy_marine:
                summary["forecast"] = build_buoy_forecast(buoy_marine[buoy_id], now, iso(now))
            else:  # marine fetch failed: keep the last forecast for this buoy
                prev = read_json(out / "buoys" / f"{buoy_id}.json") or {}
                summary["forecast"] = prev.get("forecast")
            write_json(out / "buoys" / f"{buoy_id}.json", summary)
            summaries[buoy_id] = summary
            live = buoys.is_live(summary, now, BUOY_LIVE_HOURS)
            sources["buoys"][buoy_id] = _status(
                prev_meta, ("buoys", buoy_id), True, now, live=live,
                latest_wave_time=summary["latest_wave_time"] and iso(summary["latest_wave_time"]),
            )
            any_ok = True
        except Exception as exc:
            sources["buoys"][buoy_id] = _status(prev_meta, ("buoys", buoy_id), False, now,
                                                _err(exc), live=False)

    # --- Index: which buoy each spot should show right now --------------------
    index_spots = []
    for spot in spot_list:
        active, role = None, None
        for r in ("nearest", "fallback"):
            bid = spot["buoy"][r]
            if buoys.is_live(summaries.get(bid), now, BUOY_LIVE_HOURS):
                active, role = bid, r
                break
        index_spots.append({
            "id": spot["id"],
            "name": spot["name"],
            "region": spot["region"],
            "active_buoy": active,
            "active_buoy_role": role,
            "tide_station": spot["tide_station"],
            "forecast": f"forecast/{spot['id']}.json",
            "outlook": build_outlook(forecasts.get(spot["id"]), now),
        })

    write_json(out / "index.json", {"generated_at": iso(now), "spots": index_spots})
    write_json(out / "meta.json", {
        "generated_at": iso(now),
        "sources": sources,
        "attribution": ATTRIBUTION,
    })

    failed = [k for k in ("marine", "weather") if not sources[k]["ok"]]
    failed += [f"tide {k}" for k, v in sources["tides"].items() if not v["ok"]]
    failed += [f"buoy {k}" for k, v in sources["buoys"].items() if not v["ok"]]
    print(f"Wrote {out}. Failed sources: {', '.join(failed) if failed else 'none'}")
    for name in ("marine", "weather"):
        if sources[name]["error"]:
            print(f"  {name}: {sources[name]['error']}")
    return 0 if any_ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--days", type=int, default=FORECAST_DAYS)
    args = ap.parse_args(argv)
    return run(args.out, make_session(), forecast_days=args.days)


if __name__ == "__main__":
    sys.exit(main())
