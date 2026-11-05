import json
from pathlib import Path

import pytest

from pipeline import digest, spots
from pipeline.config import SPOTS_FILE
from tests.conftest import FakeResponse, FakeSession

H = 3600
OCT31 = 1793430000          # 2026-10-31 00:00 PDT
SIX_PM = OCT31 + 18 * H     # 6 PM PDT


def forecast(height=5.0, rel="offshore", mph=3.0, days=3):
    n = days * 24 + 2
    mids = [OCT31, OCT31 + 24 * H, OCT31 + 49 * H]  # Nov 1 has 25 hours
    return {
        "time": [OCT31 + k * H for k in range(n)],
        "marine": {"wave_height": [height] * n},
        "weather": {"wind_speed_10m": [mph] * n},
        "derived": {"wind_relation": [rel] * n},
        "sun": [{"date": m} for m in mids[:days]],
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    data = tmp_path / "data"
    (data / "forecast").mkdir(parents=True)
    alerts = tmp_path / "alerts.json"

    def write(stars, fcs, mode="surf"):
        alerts.write_text(json.dumps({"mode": mode, "stars": stars}), "utf-8")
        for sid, fc in fcs.items():
            (data / "forecast" / f"{sid}.json").write_text(json.dumps(fc), "utf-8")
        (data / "index.json").write_text(json.dumps({"generated_at": "2026-11-01T00:30:00Z"}))

    return data, alerts, write


def session(titles=()):
    lines = "\n".join(json.dumps({"event": "message", "title": t}) for t in titles)
    return FakeSession({"ntfy.sh": FakeResponse(200, text=lines)})


def test_sends_one_digest_with_good_windows(setup):
    data, alerts, write = setup
    write(["pleasure_point", "steamer_lane"], {
        "pleasure_point": forecast(),
        "steamer_lane": forecast(height=0.5, rel="onshore", mph=18),
    })
    s = session()
    assert digest.run(data, alerts, s, SIX_PM) == 0
    assert len(s.posts) == 1
    url, body, headers = s.posts[0]
    text = body.decode()
    assert headers["Title"] == "Wave Finder evening: 1 spot look Good"
    assert "Pleasure Point" in text and "Steamer Lane" not in text
    # Two daylight windows: Sunday (DST ends that morning) and Monday.
    assert "Sun " in text and "Mon " in text
    assert "5.0 ft, offshore 3 mph" in text


def test_nothing_good_sends_nothing(setup):
    data, alerts, write = setup
    write(["pleasure_point"], {"pleasure_point": forecast(height=0.5, rel="onshore", mph=18)})
    s = session()
    digest.run(data, alerts, s, SIX_PM)
    assert s.posts == []


def test_outside_the_evening_window_does_nothing(setup):
    data, alerts, write = setup
    write(["pleasure_point"], {"pleasure_point": forecast()})
    s = session()
    digest.run(data, alerts, s, SIX_PM - 3 * H)
    digest.run(data, alerts, s, SIX_PM + 4 * H)
    assert s.posts == [] and s.calls == []


def test_backup_run_does_not_double_up(setup):
    data, alerts, write = setup
    write(["pleasure_point"], {"pleasure_point": forecast()})
    s = session(["Wave Finder evening: 1 spot look Good"])
    digest.run(data, alerts, s, SIX_PM + H)
    assert s.posts == []


def test_force_sends_a_test_note_when_nothing_is_good(setup):
    data, alerts, write = setup
    write(["pleasure_point"], {"pleasure_point": forecast(height=0.5, rel="onshore", mph=18)})
    s = session(["Wave Finder evening: 1 spot look Good"])
    digest.run(data, alerts, s, OCT31 + 9 * H, force=True)
    assert len(s.posts) == 1
    assert "(test)" in s.posts[0][2]["Title"]


def test_long_digest_stays_under_ntfy_limit():
    spot = {"name": "A very long beach name for testing"}
    win = {"start": SIX_PM, "end": SIX_PM + 3 * H, "score": 0.9,
           "peak": {"h": 5.0, "rel": "offshore", "mph": 4, "cls": "mid"}}
    _, body = digest.message([(spot, [win, win, win])] * 60, "surf", None)
    assert len(body.encode()) < 3600
    assert "more starred spots" in body


def test_unknown_ids_are_dropped(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"mode": "bb", "stars": ["mavericks", "nope", "mavericks"]}))
    stars, mode, warnings = digest.load_alerts(p, {"mavericks"})
    assert stars == ["mavericks"] and mode == "bb" and len(warnings) == 1
    assert digest.load_alerts(tmp_path / "missing.json", set())[0] == []


def test_alerts_file_in_repo_is_valid():
    doc = json.loads((Path(SPOTS_FILE).parent / "alerts.json").read_text("utf-8"))
    known = {s["id"] for s in spots.load()["spots"]}
    assert doc.get("mode") in ("surf", "bb")
    unknown = [s for s in doc.get("stars", []) if s not in known]
    assert not unknown, f"alerts.json names spots not in spots.json: {unknown}"
