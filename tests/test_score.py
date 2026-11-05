"""pipeline/score.py and sun.py against the cases app/js/model.js also passes
(tests/js/shared-cases.test.mjs reads the same file)."""

import json
from pathlib import Path

import pytest

from pipeline import score, sun

CASES = json.loads((Path(__file__).parent / "cases" / "scoring.json").read_text("utf-8"))


def test_size_score():
    for c in CASES["size"]:
        assert score.size_score(c["h"], c["mode"], c["expert"]) == pytest.approx(
            c["expected"], abs=1e-9), c


def test_wind_score():
    for c in CASES["wind"]:
        assert score.wind_score(c["rel"], c["mph"]) == pytest.approx(c["expected"], abs=1e-9), c


def test_hour_score_and_label():
    for c in CASES["hour"]:
        got = score.hour_score(c["h"], c["rel"], c["mph"], c["tideOk"], c["mode"], c["expert"])
        assert got == pytest.approx(c["expected"], abs=1e-9), c
    for c in CASES["label"]:
        assert score.score_label(c["s"]) == c["expected"]


def test_tide_classes():
    c = CASES["tide_classes"]
    assert score.tide_classes(c["tide"], c["times"]) == c["expected"]
    assert score.tide_classes(None, [1, 2]) == [None, None]


def test_sun_times():
    for c in CASES["sun"]:
        got = sun.sun_times(c["midnight"], c["lat"], c["lon"])
        for k, v in c["expected"].items():
            assert abs(got[k] - v) <= 1, (c, k)


@pytest.mark.parametrize("case", CASES["when_to_go"], ids=lambda c: c["name"])
def test_when_to_go(case):
    spot = case["spot"]
    is_day = score.daylight_for(case["fc"], spot["lat"], spot["lon"])
    assert sum(1 for t in case["fc"]["time"] if is_day(t)) == case["expected_daylight_hours"]
    wins = score.when_to_go(case["fc"], case["tide"], spot, case["from"], is_day,
                            case["mode"], case["hours"], case["max"])
    got = [{"start": w["start"], "end": w["end"], "peak_i": w["peak"]["i"],
            "label": w["label"]} for w in wins]
    want = [{k: w[k] for k in ("start", "end", "peak_i", "label")} for w in case["expected"]]
    assert got == want
    for w, e in zip(wins, case["expected"], strict=True):
        assert w["score"] == pytest.approx(e["score"], abs=1e-9)


def test_cases_cover_dst_and_every_label():
    labels = {w["label"] for c in CASES["when_to_go"] for w in c["expected"]}
    assert {"Good", "Fair"} <= labels
    assert any(c["expected"] == [] for c in CASES["when_to_go"])
    # The first scenario spans 2026-11-01, when Pacific time falls back an hour.
    first = CASES["when_to_go"][0]["fc"]["sun"]
    assert first[1]["date"] - first[0]["date"] == 24 * 3600
    assert first[2]["date"] - first[1]["date"] == 25 * 3600


def test_js_round_matches_math_round():
    assert sun.js_round(2.5) == 3
    assert sun.js_round(-2.5) == -2
    assert score.tide_height_at({"hourly": {"time": [0, 3600], "height": [0.25, 0.25]}}, 0) == 0.3
