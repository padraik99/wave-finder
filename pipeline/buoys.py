"""NDBC realtime buoy observations.

NDBC also redistributes CDIP buoys under 462xx station IDs, so one parser
covers both networks. Two files per station:
  {id}.txt   standard meteorological data (wave height, period, wind, water temp)
  {id}.spec  spectral summary: swell vs wind-sea split
"""

from datetime import UTC, datetime

from .config import BUOY_HISTORY_HOURS
from .geo import compass_to_deg
from .http import get_text
from .units import c_to_f, m_to_ft, ms_to_mph

REALTIME_URL = "https://www.ndbc.noaa.gov/data/realtime2/{id}.{ext}"
ACTIVE_STATIONS_URL = "https://www.ndbc.noaa.gov/activestations.xml"


def _num(token: str):
    if token in ("MM", "N/A"):
        return None
    try:
        return float(token)
    except ValueError:
        return None


def parse_table(text: str) -> list[dict]:
    """Parse an NDBC realtime2 table into dicts keyed by column name, newest first."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("#"):
        raise ValueError("not an NDBC realtime table")
    header = lines[0].lstrip("#").split()
    rows = []
    for ln in lines[1:]:
        if ln.startswith("#"):
            continue  # units line
        parts = ln.split()
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts, strict=True))
        t = datetime(
            int(row["YY"]), int(row["MM"]), int(row["DD"]), int(row["hh"]), int(row["mm"]),
            tzinfo=UTC,
        )
        row["time"] = int(t.timestamp())
        rows.append(row)
    rows.sort(key=lambda r: r["time"], reverse=True)
    return rows


def parse_met(text: str) -> list[dict]:
    out = []
    for r in parse_table(text):
        out.append({
            "time": r["time"],
            "wave_height_ft": m_to_ft(_num(r.get("WVHT", "MM"))),
            "dominant_period_s": _num(r.get("DPD", "MM")),
            "average_period_s": _num(r.get("APD", "MM")),
            "mean_wave_dir_deg": _num(r.get("MWD", "MM")),
            "wind_dir_deg": _num(r.get("WDIR", "MM")),
            "wind_speed_mph": ms_to_mph(_num(r.get("WSPD", "MM"))),
            "wind_gust_mph": ms_to_mph(_num(r.get("GST", "MM"))),
            "water_temp_f": c_to_f(_num(r.get("WTMP", "MM"))),
            "air_temp_f": c_to_f(_num(r.get("ATMP", "MM"))),
        })
    return out


def parse_spec(text: str) -> list[dict]:
    out = []
    for r in parse_table(text):
        out.append({
            "time": r["time"],
            "swell_height_ft": m_to_ft(_num(r.get("SwH", "MM"))),
            "swell_period_s": _num(r.get("SwP", "MM")),
            "swell_dir_deg": compass_to_deg(r.get("SwD", "MM")),
            "wind_wave_height_ft": m_to_ft(_num(r.get("WWH", "MM"))),
            "wind_wave_period_s": _num(r.get("WWP", "MM")),
            "wind_wave_dir_deg": compass_to_deg(r.get("WWD", "MM")),
            "steepness": None if r.get("STEEPNESS") in (None, "MM", "N/A") else r["STEEPNESS"],
        })
    return out


def _recent(rows: list[dict], now: int) -> list[dict]:
    cutoff = now - BUOY_HISTORY_HOURS * 3600
    return [r for r in rows if r["time"] >= cutoff]


def _latest_with(rows: list[dict], key: str):
    return next((r for r in rows if r.get(key) is not None), None)


def summarise(station: str, met: list[dict], spec: list[dict] | None, now: int) -> dict:
    latest_wave = _latest_with(met, "wave_height_ft")
    latest_any = met[0] if met else None
    return {
        "id": station,
        "latest_obs_time": latest_any["time"] if latest_any else None,
        "latest_wave_time": latest_wave["time"] if latest_wave else None,
        "latest": latest_wave,
        "latest_spectral": _latest_with(spec or [], "swell_height_ft"),
        "met": _recent(met, now),
        "spectral": _recent(spec or [], now),
        "units": {"height": "ft", "period": "s", "direction": "deg_from",
                  "speed": "mph", "temp": "F"},
    }


def fetch(session, station: str, now: int) -> dict:
    met = parse_met(get_text(session, REALTIME_URL.format(id=station, ext="txt")))
    try:
        spec = parse_spec(get_text(session, REALTIME_URL.format(id=station, ext="spec")))
    except Exception:  # spectral file is optional; some stations lack it
        spec = None
    return summarise(station, met, spec, now)


def is_live(summary: dict | None, now: int, max_age_hours: float) -> bool:
    """Live = has a wave-height reading newer than max_age_hours."""
    if not summary or not summary.get("latest_wave_time"):
        return False
    return now - summary["latest_wave_time"] <= max_age_hours * 3600
