"""Load and validate spots.json."""

import json
from pathlib import Path

from .config import DEFAULT_OFFSHORE_KM, SPOTS_FILE
from .geo import destination

BREAK_TYPES = {"beach", "reef", "point"}
TIDE_PREFERENCES = {"low", "low_to_mid", "mid", "mid_to_high", "high", "any"}


def load(path: Path = SPOTS_FILE) -> dict:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    errors = validate(doc)
    if errors:
        raise ValueError("spots.json is invalid:\n  " + "\n  ".join(errors))
    return doc


def forecast_point(spot: dict) -> tuple[float, float]:
    """Where to sample the marine model for this spot (must be over water)."""
    fp = spot.get("forecast_point")
    if fp:
        return fp["lat"], fp["lon"]
    return destination(spot["lat"], spot["lon"], spot["facing_deg"], DEFAULT_OFFSHORE_KM)


def validate(doc: dict) -> list[str]:
    errors = []
    regions = {r["id"] for r in doc.get("regions", [])}
    buoys = doc.get("buoys", {})
    tides = doc.get("tide_stations", {})
    seen = set()
    for s in doc.get("spots", []):
        sid = s.get("id", "?")
        if sid in seen:
            errors.append(f"{sid}: duplicate id")
        seen.add(sid)
        if s.get("region") not in regions:
            errors.append(f"{sid}: unknown region {s.get('region')!r}")
        lat, lon = s.get("lat"), s.get("lon")
        # California coast bounding box.
        if not (isinstance(lat, int | float) and 32.0 <= lat <= 42.1):
            errors.append(f"{sid}: lat {lat!r} outside California")
        if not (isinstance(lon, int | float) and -125.0 <= lon <= -117.0):
            errors.append(f"{sid}: lon {lon!r} outside California")
        facing = s.get("facing_deg")
        if not (isinstance(facing, int | float) and 0 <= facing < 360):
            errors.append(f"{sid}: facing_deg must be 0-359")
        win = s.get("swell_window") or {}
        for key in ("from", "to"):
            v = win.get(key)
            if not (isinstance(v, int | float) and 0 <= v < 360):
                errors.append(f"{sid}: swell_window.{key} must be 0-359")
        if s.get("break_type") not in BREAK_TYPES:
            errors.append(f"{sid}: break_type must be one of {sorted(BREAK_TYPES)}")
        if s.get("tide_preference") not in TIDE_PREFERENCES:
            errors.append(f"{sid}: tide_preference must be one of {sorted(TIDE_PREFERENCES)}")
        b = s.get("buoy") or {}
        for key in ("nearest", "fallback"):
            if b.get(key) not in buoys:
                errors.append(f"{sid}: buoy.{key} {b.get(key)!r} not in buoys registry")
        if b.get("nearest") and b.get("nearest") == b.get("fallback"):
            errors.append(f"{sid}: fallback buoy must differ from nearest")
        if s.get("tide_station") not in tides:
            errors.append(f"{sid}: tide_station {s.get('tide_station')!r} not in registry")
    if not doc.get("spots"):
        errors.append("no spots defined")
    return errors


def used_buoys(doc: dict) -> list[str]:
    ids = {b for s in doc["spots"] for b in (s["buoy"]["nearest"], s["buoy"]["fallback"])}
    # Registry-only buoys (e.g. the offshore early-warning buoy) are fetched too.
    ids.update(doc["buoys"])
    return sorted(ids)


def used_tide_stations(doc: dict) -> list[str]:
    return sorted({s["tide_station"] for s in doc["spots"]})
