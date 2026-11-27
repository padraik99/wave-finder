"""Face-height rule of thumb: pipeline/score.py and app/js/model.js must agree.

tests/cases/faces.json is shared with tests/js/faces.test.mjs. If the formula
changes on purpose, regenerate it from face_range (see REGENERATE below) and
update model.js faceRange to match.
"""

import json
from pathlib import Path

from pipeline.score import face_range, fc_period

CASES = json.loads((Path(__file__).parent / "cases" / "faces.json").read_text("utf-8"))

REGENERATE = """
from pipeline.score import face_range
cases = [{"hs": hs, "period": p, "expected": face_range(hs, p)}
         for hs in (0, 8, 12, 14, 15, 15.4, 16.7, 18, 22, 25, 30, None)
         for p in (8, 10, 12, 13.5, 14, 15, 16, 17, 18, 20, None)]
"""


def test_shared_cases():
    for c in CASES["cases"]:
        assert face_range(c["hs"], c["period"]) == c["expected"], c


def test_matches_the_two_calibration_swells():
    assert face_range(22, 16) == [40, 55]   # Nov 14 2026: NWS called 40-50 ft faces
    assert face_range(15, 15) == [25, 35]   # Nov 25 2026: about 30 ft faces filmed


def test_longer_period_means_bigger_faces_and_range_is_never_empty():
    assert face_range(15, 18)[1] > face_range(15, 12)[1]
    for c in CASES["cases"]:
        if c["expected"]:
            assert c["expected"][1] > c["expected"][0]


def test_fc_period_takes_the_longer_period():
    m = {"wave_period": [16.0, None], "swell_wave_period": [13.5, None]}
    assert fc_period(m, 0) == 16.0 and fc_period(m, 1) is None
