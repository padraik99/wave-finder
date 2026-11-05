"""Evening digest: one ntfy message listing starred spots with a Good window.

    python -m pipeline.digest --data data [--alerts alerts.json] [--force]

Reads the stars from alerts.json (made by the app's "Alert on these" button)
and the published forecast and tide files, and runs the same When to go
scoring as the app (pipeline/score.py) over the next 48 hours. A window is
Good at a peak score of 0.75 or more. Nothing Good: nothing is sent.

Runs are triggered around 6 PM Pacific (cron-job.org, with GitHub's own
schedule as a backup). It only sends between 5:50 and 9 PM Pacific, and not if
a digest already went out in the last 6 hours, so a backup run can't double up.
--force skips both checks and, if nothing is Good, says so (for testing).
"""

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import ntfy, spots
from .config import SPOTS_FILE
from .http import make_session
from .run import read_json
from .score import TZ, daylight_for, when_to_go

TITLE_PREFIX = "Wave Finder evening"
GOOD = 0.75
AHEAD_HOURS = 48
SEND_FROM = (17, 50)   # local time, inclusive
SEND_UNTIL = (21, 0)   # local time, exclusive
DEDUPE_SINCE = "6h"
STALE_AFTER_H = 3
MAX_BYTES = 3000
MODES = {"surf": "surf", "bb": "bodyboard"}


def load_alerts(path: Path, known: set[str]) -> tuple[list[str], str, list[str]]:
    """(star ids, mode, warnings). Unknown ids are dropped with a warning."""
    doc = read_json(path)
    if not isinstance(doc, dict):
        return [], "surf", [f"{path} missing or not valid JSON"]
    mode = doc.get("mode") if doc.get("mode") in MODES else "surf"
    stars, warnings = [], []
    for sid in doc.get("stars") or []:
        if sid in known:
            if sid not in stars:
                stars.append(sid)
        else:
            warnings.append(f"unknown spot id in alerts.json: {sid!r}")
    return stars, mode, warnings


def local(u: int) -> datetime:
    return datetime.fromtimestamp(u, UTC).astimezone(TZ)


def fmt_hour(u: int) -> str:
    h = local(u).hour
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


def fmt_window(w: dict) -> str:
    return f"{local(w['start']).strftime('%a')} {fmt_hour(w['start'])}–{fmt_hour(w['end'])}"


def good_windows(spot: dict, fc: dict, tide: dict | None, now: int, mode: str) -> list[dict]:
    is_day = daylight_for(fc, spot["lat"], spot["lon"])
    wins = when_to_go(fc, tide, spot, now, is_day, mode, AHEAD_HOURS, 3)
    return [w for w in wins if w["score"] >= GOOD]


def describe(w: dict) -> str:
    p = w["peak"]
    h = "–" if p["h"] is None else f"{p['h']:.1f}"
    wind = f"{p['rel'] or 'wind ?'} {'' if p['mph'] is None else round(p['mph'])} mph".strip()
    tide = f", {p['cls']} tide" if p["cls"] else ""
    return f"{fmt_window(w)}: {h} ft, {wind}{tide}"


def collect(data: Path, doc: dict, stars: list[str], now: int, mode: str) -> list[tuple]:
    """[(spot, [good windows])] for starred spots that have any."""
    by_id = {s["id"]: s for s in doc["spots"]}
    out = []
    for sid in stars:
        spot = by_id[sid]
        fc = read_json(data / "forecast" / f"{sid}.json")
        if not fc or not fc.get("time"):
            print(f"  {sid}: no forecast file")
            continue
        tide = read_json(data / "tides" / f"{spot['tide_station']}.json")
        wins = good_windows(spot, fc, tide, now, mode)
        print(f"  {sid}: {len(wins)} Good window(s)")
        if wins:
            out.append((spot, wins))
    return out


def message(found: list[tuple], mode: str, data_age_h: float | None) -> tuple[str, str]:
    n = len(found)
    title = f"{TITLE_PREFIX}: {n} spot{'s' if n != 1 else ''} look Good"
    lines = []
    for k, (spot, wins) in enumerate(found):
        block = [spot["name"], *(f"  {describe(w)}" for w in wins)]
        # ntfy turns messages over 4 KB into attachments; stay well under.
        if len("\n".join(lines + block).encode()) > MAX_BYTES:
            lines.append(f"…and {n - k} more starred spots; see the app.")
            break
        lines += block
    lines.append(f"Next 2 days, daylight, {MODES[mode]} scoring. "
                 "Open the app for the hour by hour.")
    if data_age_h is not None and data_age_h > STALE_AFTER_H:
        lines.append(f"Note: forecast data is {data_age_h:.0f} h old.")
    return title, "\n".join(lines)


def in_send_window(now: int) -> bool:
    t = local(now)
    return SEND_FROM <= (t.hour, t.minute) < SEND_UNTIL


def data_age_hours(data: Path, now: int) -> float | None:
    stamp = (read_json(data / "index.json") or {}).get("generated_at")
    if not stamp:
        return None
    t = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    return (now - t) / 3600


def run(data: Path, alerts: Path, session, now: int, force: bool = False,
        spots_file: Path = SPOTS_FILE) -> int:
    if not force and not in_send_window(now):
        print(f"{local(now):%H:%M} Pacific is outside the digest window; nothing to do.")
        return 0
    doc = spots.load(spots_file)
    stars, mode, warnings = load_alerts(alerts, {s["id"] for s in doc["spots"]})
    for w in warnings:
        print(f"warning: {w}")
    if not stars:
        print("No stars in alerts.json; nothing to send.")
        return 0
    if not force:
        titles = ntfy.recent_titles(session, DEDUPE_SINCE)
        if titles and any(t.startswith(TITLE_PREFIX) for t in titles):
            print("A digest already went out in the last 6 h; not sending another.")
            return 0
    print(f"Checking {len(stars)} starred spot(s), {MODES[mode]} mode:")
    found = collect(data, doc, stars, now, mode)
    if not found:
        print("Nothing Good in the next 2 days; no digest.")
        if force:
            ntfy.send(session, f"{TITLE_PREFIX} (test): nothing Good",
                      f"Checked {len(stars)} starred spots: no Good window in the next 2 days. "
                      "On a normal evening this sends nothing.", tags="ocean")
        return 0
    title, body = message(found, mode, data_age_hours(data, now))
    print(title + "\n" + body)
    ntfy.send(session, title, body, tags="ocean,star")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--alerts", type=Path, default=SPOTS_FILE.parent / "alerts.json")
    ap.add_argument("--force", action="store_true",
                    help="send now, whatever the time, even if a digest already went out")
    args = ap.parse_args(argv)
    return run(args.data, args.alerts, make_session(), int(time.time()), args.force)


if __name__ == "__main__":
    sys.exit(main())
