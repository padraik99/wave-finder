"""Live check of every data source and station ID in spots.json.

    python -m pipeline.verify

Checks that each buoy is listed by NDBC and reporting waves, each tide station
exists and returns predictions, the registry coordinates match the operators'
own metadata, and Open-Meteo returns real (non-null) data at every spot.
Exits 1 if anything a spot depends on is broken.
"""

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime

from . import buoys, openmeteo, spots, tides
from .config import BUOY_LIVE_HOURS
from .geo import haversine_km
from .http import get_text, make_session

# Registry coordinates may be off by this much before we flag them.
BUOY_COORD_TOLERANCE_KM = 10
TIDE_COORD_TOLERANCE_KM = 3


def parse_active_stations(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    out = {}
    for st in root.iter("station"):
        out[st.get("id", "").upper()] = {
            "name": st.get("name"),
            "lat": float(st.get("lat")),
            "lon": float(st.get("lon")),
            "type": st.get("type"),
        }
    return out


def _fmt_age(ts, now):
    return "never" if not ts else f"{(now - ts) / 3600:.1f} h ago"


def check(session, doc: dict, now: int) -> tuple[list[str], list[str], list[str]]:
    ok, warn, fail = [], [], []

    # Buoys ---------------------------------------------------------------------
    try:
        active = parse_active_stations(get_text(session, buoys.ACTIVE_STATIONS_URL))
    except Exception as exc:
        active = None
        warn.append(f"NDBC active station list unavailable: {exc}")
    live = {}
    for bid, info in doc["buoys"].items():
        label = f"buoy {bid} {info['name']}"
        if active is not None:
            meta = active.get(bid)
            if not meta:
                warn.append(f"{label}: not in NDBC active station list")
            else:
                d = haversine_km(info["lat"], info["lon"], meta["lat"], meta["lon"])
                if d > BUOY_COORD_TOLERANCE_KM:
                    warn.append(f"{label}: registry coords {d:.0f} km from NDBC's "
                                f"({meta['lat']}, {meta['lon']}, '{meta['name']}')")
        try:
            summary = buoys.fetch(session, bid, now)
        except Exception as exc:
            live[bid] = False
            warn.append(f"{label}: fetch failed: {exc}")
            continue
        live[bid] = buoys.is_live(summary, now, BUOY_LIVE_HOURS)
        latest = summary["latest"] or {}
        spec = "with swell split" if summary["latest_spectral"] else "no spectral file"
        line = (f"{label}: waves {_fmt_age(summary['latest_wave_time'], now)}, "
                f"{latest.get('wave_height_ft')} ft @ {latest.get('dominant_period_s')} s, {spec}")
        (ok if live[bid] else warn).append(line)

    for s in doc["spots"]:
        n, f = s["buoy"]["nearest"], s["buoy"]["fallback"]
        if not live.get(n) and not live.get(f):
            fail.append(f"spot {s['id']}: neither buoy {n} nor {f} is live")
        elif not live.get(n):
            warn.append(f"spot {s['id']}: nearest buoy {n} down, using fallback {f}")

    # Tide stations -------------------------------------------------------------
    today = datetime.fromtimestamp(now, UTC).date()
    for sid in spots.used_tide_stations(doc):
        info = doc["tide_stations"][sid]
        label = f"tide {sid} {info['name']}"
        try:
            meta = tides.fetch_metadata(session, sid)
            d = haversine_km(info["lat"], info["lon"], float(meta["lat"]), float(meta["lon"]))
            if d > TIDE_COORD_TOLERANCE_KM:
                warn.append(f"{label}: registry coords {d:.1f} km from CO-OPS "
                            f"({meta['lat']}, {meta['lon']}, '{meta['name']}')")
        except Exception as exc:
            warn.append(f"{label}: metadata lookup failed: {exc}")
        try:
            data = tides.fetch(session, sid, today, 2)
            ok.append(f"{label}: {len(data['extremes'])} highs/lows in 2 days")
        except Exception as exc:
            fail.append(f"{label}: predictions failed: {exc}")

    # Open-Meteo ----------------------------------------------------------------
    spot_list = doc["spots"]
    checks = [
        ("marine", openmeteo.fetch_marine, [spots.forecast_point(s) for s in spot_list],
         "wave_height"),
        ("weather", openmeteo.fetch_weather, [(s["lat"], s["lon"]) for s in spot_list],
         "wind_speed_10m"),
    ]
    for name, fn, points, var in checks:
        try:
            results = fn(session, points, 2)
        except Exception as exc:
            fail.append(f"Open-Meteo {name}: request failed: {exc}")
            continue
        for s, (lat, lon), r in zip(spot_list, points, results, strict=True):
            vals = [v for v in r[var] if v is not None]
            if not vals:
                fail.append(f"Open-Meteo {name} @ {s['id']} ({lat}, {lon}): all {var} null "
                            "(point probably on land)")
            else:
                ok.append(f"Open-Meteo {name} @ {s['id']}: {len(vals)}/{len(r[var])} hours, "
                          f"{var} now {vals[0]}")
    return ok, warn, fail


def main(argv=None) -> int:
    argparse.ArgumentParser(description="Live-check every data source").parse_args(argv)
    doc = spots.load()
    now = int(time.time())
    ok, warn, fail = check(make_session(), doc, now)
    print(f"Verified at {datetime.fromtimestamp(now, UTC):%Y-%m-%d %H:%M} UTC "
          f"(today {date.today()})\n")
    for title, lines in (("OK", ok), ("WARN", warn), ("FAIL", fail)):
        print(f"== {title} ({len(lines)})")
        for ln in lines:
            print(f"  {ln}")
        print()
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
