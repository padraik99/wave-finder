"""Alert via ntfy when published data stops updating.

    python -m pipeline.staleness --meta data/meta.json

Catches: the fetch workflow failing or not running, and individual sources
failing for longer than a few cycles. It cannot catch GitHub Actions itself
being down or schedules being disabled, because it runs on the same scheduler;
an external dead-man's switch (see README) covers that.
"""

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import ntfy
from .http import make_session
from .run import read_json

MAX_RUN_AGE_H = 8        # schedule is every 3 h; allow for GitHub's delays
MAX_FORECAST_AGE_H = 12  # Open-Meteo marine / weather
MAX_TIDE_AGE_H = 48      # predictions run 17 days ahead, so this is generous
MAX_BUOY_AGE_H = 12      # all buoy fetches failing = pipeline problem, not one dead buoy


def _age_h(stamp: str | None, now: float) -> float | None:
    if not stamp:
        return None
    t = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    return (now - t) / 3600


def _too_old(stamp, now, limit) -> bool:
    age = _age_h(stamp, now)
    return age is None or age > limit


def problems(meta: dict | None, now: float) -> list[str]:
    if not meta:
        return ["meta.json missing or unreadable: the data pipeline has never run or broke"]
    out = []
    if _too_old(meta.get("generated_at"), now, MAX_RUN_AGE_H):
        out.append(f"last pipeline run {meta.get('generated_at')} is over {MAX_RUN_AGE_H} h old")
    src = meta.get("sources", {})
    for name in ("marine", "weather"):
        s = src.get(name, {})
        if _too_old(s.get("last_success"), now, MAX_FORECAST_AGE_H):
            out.append(f"{name} forecast last succeeded {s.get('last_success')}: "
                       f"{s.get('error') or 'no error recorded'}")
    for station, s in src.get("tides", {}).items():
        if _too_old(s.get("last_success"), now, MAX_TIDE_AGE_H):
            out.append(f"tide station {station} last succeeded {s.get('last_success')}")
    buoy_status = src.get("buoys", {})
    if buoy_status and all(_too_old(s.get("last_success"), now, MAX_BUOY_AGE_H)
                           for s in buoy_status.values()):
        out.append("no buoy fetch has succeeded in the last 12 h")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Alert if published data is stale")
    ap.add_argument("--meta", type=Path, default=Path("data/meta.json"))
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args(argv)
    found = problems(read_json(args.meta), time.time())
    if not found:
        print("Data is fresh.")
        return 0
    msg = "\n".join(f"- {p}" for p in found)
    print("Stale data:\n" + msg)
    if not args.no_notify:
        ntfy.send(make_session(), "Wave Finder data is stale", msg, priority="high",
                  tags="warning")
    return 1


if __name__ == "__main__":
    sys.exit(main())
