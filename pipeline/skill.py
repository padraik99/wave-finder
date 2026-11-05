"""How the wave forecast has been doing at each buoy, over the last week.

Each run pairs the buoy's readings with the forecast for the buoy's own
position, one pair per forecast hour, and appends them to a log kept on the
data branch (skill/<buoy>.json). The summary goes into buoys/<buoy>.json so the
app can say "the forecast has run 0.8 ft low here this week".

The forecast hours compared are the latest model run's, so this measures the
model's short-range bias at the buoy, not how good a 3-day forecast was.
"""

# A reading counts for a forecast hour if it is within this of the hour.
MATCH_S = 20 * 60
KEEP_DAYS = 7
# Fewer pairs than this and the summary says nothing (half a day of hours).
MIN_PAIRS = 12


def new_pairs(met: list[dict], forecast: dict | None, now: int, have: set[int]) -> list[dict]:
    """One {t, obs, fc} per past forecast hour not already logged, using the
    reading nearest the hour (within MATCH_S)."""
    if not forecast or not forecast.get("time"):
        return []
    readings = [(r["time"], r["wave_height_ft"]) for r in met
                if r.get("wave_height_ft") is not None and r.get("time")]
    out = []
    for t, fc in zip(forecast["time"], forecast["wave_height"], strict=True):
        if t > now or t in have or fc is None:
            continue
        near = min(readings, key=lambda r: abs(r[0] - t), default=None)
        if near and abs(near[0] - t) <= MATCH_S:
            out.append({"t": t, "obs": near[1], "fc": fc})
    return out


def update(log: list[dict] | None, met: list[dict], forecast: dict | None, now: int,
           keep_days: int = KEEP_DAYS) -> list[dict]:
    """The log with this run's new pairs added and anything too old dropped."""
    log = list(log or [])
    log += new_pairs(met, forecast, now, {p["t"] for p in log})
    cutoff = now - keep_days * 86400
    return sorted((p for p in log if p["t"] >= cutoff), key=lambda p: p["t"])


def summarize(log: list[dict], now: int, days: int = KEEP_DAYS) -> dict | None:
    """Mean of (buoy - forecast) and mean absolute gap, in ft. Positive bias:
    the buoy has run bigger than forecast."""
    pairs = [p for p in log if p["t"] >= now - days * 86400]
    if len(pairs) < MIN_PAIRS:
        return None
    diffs = [p["obs"] - p["fc"] for p in pairs]
    return {
        "days": days,
        "pairs": len(pairs),
        "since": pairs[0]["t"],
        "bias_ft": round(sum(diffs) / len(diffs), 1),
        "mean_abs_ft": round(sum(abs(d) for d in diffs) / len(diffs), 1),
    }
