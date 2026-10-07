import json

from pipeline import ntfy, run, spots, staleness, verify

from .conftest import NOW, FakeResponse, FakeSession, healthy_routes


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_full_run_writes_all_outputs(tmp_path, healthy_session):
    assert run.run(tmp_path, healthy_session, now=NOW) == 0
    doc = spots.load()
    index = _load(tmp_path / "index.json")
    assert len(index["spots"]) == len(doc["spots"])
    mav = next(s for s in index["spots"] if s["id"] == "mavericks")
    assert mav["active_buoy"] == "46012" and mav["active_buoy_role"] == "nearest"

    fc = _load(tmp_path / "forecast" / "mavericks.json")
    assert len(fc["time"]) == 48
    assert fc["marine"]["wave_height"][0] == 4.9          # 1.5 m
    assert fc["derived"]["swell_in_window"][0] is True    # 285 in 250-320
    assert fc["derived"]["wind_relation"][0] == "offshore"  # 100 deg wind, 290 facing
    assert fc["sun"]

    tide = _load(tmp_path / "tides" / "9414131.json")
    assert tide["hourly"]["height"]
    buoy = _load(tmp_path / "buoys" / "46012.json")
    assert buoy["latest"]["wave_height_ft"] == 6.9

    meta = _load(tmp_path / "meta.json")
    assert meta["sources"]["marine"]["ok"]
    assert meta["attribution"]
    # One request per Open-Meteo API, not one per spot.
    om_calls = [c for c in healthy_session.calls if "open-meteo" in c[0]]
    assert len(om_calls) == 2


def test_failed_source_keeps_previous_data(tmp_path, healthy_session):
    run.run(tmp_path, healthy_session, now=NOW)
    before = _load(tmp_path / "forecast" / "mavericks.json")

    routes = healthy_routes()
    routes["marine-api.open-meteo.com"] = FakeResponse(503, text="down")
    routes["datagetter"] = FakeResponse(200, body={"error": {"message": "down"}})
    later = NOW + 3 * 3600
    assert run.run(tmp_path, FakeSession(routes), now=later) == 0

    after = _load(tmp_path / "forecast" / "mavericks.json")
    assert after["marine"] == before["marine"]                 # carried over
    assert after["marine_updated"] == before["marine_updated"]
    assert after["weather_updated"] != before["weather_updated"]  # refreshed
    meta = _load(tmp_path / "meta.json")
    assert meta["sources"]["marine"]["ok"] is False
    assert meta["sources"]["marine"]["last_success"] == run.iso(NOW)
    assert "503" in meta["sources"]["marine"]["error"]
    assert meta["sources"]["tides"]["9414131"]["last_success"] == run.iso(NOW)
    assert (tmp_path / "tides" / "9414131.json").exists()


def test_total_outage_exits_nonzero(tmp_path):
    assert run.run(tmp_path, FakeSession({}), now=NOW) == 1


def test_dead_nearest_buoy_falls_back(tmp_path):
    from .conftest import DEAD_TXT

    routes = healthy_routes()
    healthy_ndbc = routes["realtime2"]

    def ndbc(url, params):
        if "46012.txt" in url:
            return FakeResponse(200, text=DEAD_TXT)
        return healthy_ndbc(url, params)

    routes["realtime2"] = ndbc
    run.run(tmp_path, FakeSession(routes), now=NOW)
    mav = next(s for s in _load(tmp_path / "index.json")["spots"] if s["id"] == "mavericks")
    assert mav["active_buoy"] == "46214" and mav["active_buoy_role"] == "fallback"


# --- Staleness ------------------------------------------------------------------


def test_fresh_meta_has_no_problems(tmp_path, healthy_session):
    run.run(tmp_path, healthy_session, now=NOW)
    assert staleness.problems(_load(tmp_path / "meta.json"), NOW + 3600) == []


def test_stale_meta_reports_problems(tmp_path, healthy_session):
    run.run(tmp_path, healthy_session, now=NOW)
    found = staleness.problems(_load(tmp_path / "meta.json"), NOW + 13 * 3600)
    text = "\n".join(found)
    assert "last pipeline run" in text
    assert "marine" in text and "weather" in text
    assert "tide" not in text  # 48 h allowance


def test_missing_meta_is_a_problem():
    assert staleness.problems(None, NOW)


def test_staleness_main_sends_ntfy(tmp_path, monkeypatch, capsys):
    session = FakeSession({})
    monkeypatch.setattr(staleness, "make_session", lambda: session)
    monkeypatch.setenv("NTFY_TOPIC", "secret-topic-abc")
    assert staleness.main(["--meta", str(tmp_path / "missing.json")]) == 1
    assert len(session.posts) == 1
    url, body, headers = session.posts[0]
    assert url == "https://ntfy.sh/secret-topic-abc"
    assert headers["Priority"] == "high"
    assert b"meta.json missing" in body
    assert "secret-topic-abc" not in capsys.readouterr().out


# --- ntfy -----------------------------------------------------------------------


def test_ntfy_skips_without_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    s = FakeSession({})
    assert ntfy.send(s, "t", "m") is False
    assert s.posts == []


def test_ntfy_failure_does_not_leak_topic(monkeypatch, capsys):
    class Failing(FakeSession):
        def post(self, url, data=None, headers=None, timeout=None):
            return FakeResponse(500, text="err")

    assert ntfy.send(Failing({}), "t", "m", topic="hush-hush") is False
    assert "hush-hush" not in capsys.readouterr().out


# --- Verify (offline, against canned responses) ----------------------------------

ACTIVE_XML = """<?xml version="1.0"?><stations>
<station id="46012" lat="37.361" lon="-122.881" name="Half Moon Bay" type="buoy"/>
<station id="46214" lat="37.946" lon="-123.470" name="Point Reyes" type="buoy"/>
</stations>"""


def test_parse_active_stations():
    st = verify.parse_active_stations(ACTIVE_XML)
    assert st["46012"]["lat"] == 37.361


def test_verify_check_all_healthy():
    routes = healthy_routes()
    routes["activestations.xml"] = FakeResponse(200, text=ACTIVE_XML)
    ok, warn, fail = verify.check(FakeSession(routes), spots.load(), NOW)
    assert fail == []
    assert any("Open-Meteo marine @ mavericks" in line for line in ok)
    # Buoys missing from the trimmed XML get a warning, not a failure.
    assert any("not in NDBC active station list" in line for line in warn)


def test_verify_flags_land_points():
    routes = healthy_routes()
    from .conftest import marine_location

    def nulls(url, params):
        n = len(params["latitude"].split(","))
        loc = marine_location()
        loc["hourly"]["wave_height"] = [None] * 48
        return FakeResponse(200, body=[loc] * n)

    routes["marine-api.open-meteo.com"] = nulls
    _, _, fail = verify.check(FakeSession(routes), spots.load(), NOW)
    assert any("on land" in line for line in fail)
