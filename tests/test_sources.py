from datetime import date

import pytest

from pipeline import buoys, openmeteo, tides
from pipeline.http import FetchError, get_json

from .conftest import (
    CDIP_TXT,
    DEAD_TXT,
    NDBC_SPEC,
    NDBC_TXT,
    NOW,
    FakeResponse,
    FakeSession,
    marine_location,
    weather_location,
)

# --- Open-Meteo -----------------------------------------------------------------


def test_marine_params_batch_all_points():
    p = openmeteo.marine_params([(37.1, -122.1), (36.9, -121.9)], 16)
    assert p["latitude"] == "37.1000,36.9000"
    assert p["longitude"] == "-122.1000,-121.9000"
    assert "swell_wave_period" in p["hourly"]
    assert p["timeformat"] == "unixtime"
    assert p["forecast_days"] == 16


def test_parse_marine_converts_metres_to_feet():
    out = openmeteo.parse_marine([marine_location(wave_m=2.0)] * 2, 2)
    assert len(out) == 2
    assert out[0]["wave_height"][0] == 6.6
    assert out[0]["swell_wave_direction"][0] == 285
    assert out[0]["sea_surface_temperature"][0] == 55.4  # 13 °C


def test_parse_marine_single_location_dict():
    assert len(openmeteo.parse_marine(marine_location(), 1)) == 1


def test_parse_marine_wrong_count_raises():
    with pytest.raises(FetchError):
        openmeteo.parse_marine([marine_location()], 2)


def test_parse_marine_unknown_unit_raises():
    loc = marine_location()
    loc["hourly_units"]["wave_height"] = "fathoms"
    with pytest.raises(FetchError, match="unrecognised unit"):
        openmeteo.parse_marine(loc, 1)


def test_open_meteo_error_payload_raises():
    with pytest.raises(FetchError, match="bad lat"):
        openmeteo.parse_marine({"error": True, "reason": "bad lat"}, 1)


def test_parse_weather_includes_sun_times():
    out = openmeteo.parse_weather([weather_location()], 1)[0]
    assert out["wind_speed_10m"][0] == 8.0
    assert len(out["sun"]) == 2
    assert out["sun"][0]["sunset"] > out["sun"][0]["sunrise"]


def test_http_error_raises():
    s = FakeSession({"x": FakeResponse(400, body={"error": True}, text="bad request")})
    with pytest.raises(FetchError, match="HTTP 400"):
        get_json(s, "https://x/")


# --- Tides ----------------------------------------------------------------------


def test_tide_params():
    p = tides.params("9414131", date(2026, 10, 6), 17)
    assert p["begin_date"] == "20261006"
    assert p["end_date"] == "20261023"
    assert p["interval"] == "hilo"
    assert p["datum"] == "MLLW"
    assert p["units"] == "english"


def test_parse_hilo_and_interpolate():
    from .conftest import COOPS_HILO

    ext = tides.parse_hilo(COOPS_HILO)
    assert [e["type"] for e in ext] == ["H", "L", "H", "L"]
    h = tides.interpolate_hourly(ext)
    # 02:00 to 20:00 inclusive, hourly.
    assert len(h["time"]) == 19
    assert h["height"][0] == 5.5          # at the first high
    assert h["height"][3] == 3.0          # midway between 5.5 and 0.5
    assert h["height"][6] == 0.5          # at the low
    assert h["rising"][0] is False        # falling toward the low
    assert h["rising"][7] is True         # rising toward the 14:00 high
    assert min(h["height"]) >= 0.5 and max(h["height"]) <= 5.5


def test_parse_hilo_error_raises():
    with pytest.raises(FetchError, match="No Predictions"):
        tides.parse_hilo({"error": {"message": "No Predictions data was found."}})


# --- Buoys ----------------------------------------------------------------------


def test_parse_met_newest_first_with_units():
    rows = buoys.parse_met(NDBC_TXT)
    assert rows[0]["time"] > rows[1]["time"]
    r = rows[0]
    assert r["wave_height_ft"] == 6.9
    assert r["dominant_period_s"] == 14
    assert r["wind_speed_mph"] == 15.7
    assert r["water_temp_f"] == 58.6
    assert rows[1]["wave_height_ft"] is None  # MM


def test_parse_spec_compass_directions():
    r = buoys.parse_spec(NDBC_SPEC)[0]
    assert r["swell_dir_deg"] == 292.5
    assert r["wind_wave_dir_deg"] == 315
    assert r["swell_period_s"] == 14.3
    assert buoys.parse_spec(NDBC_SPEC)[1]["steepness"] is None


def test_summary_and_liveness():
    met = buoys.parse_met(NDBC_TXT)
    s = buoys.summarise("46012", met, buoys.parse_spec(NDBC_SPEC), NOW)
    assert s["latest"]["wave_height_ft"] == 6.9
    assert len(s["met"]) == 3  # 3-day-old row dropped from 48 h history
    assert buoys.is_live(s, NOW, 6)

    dead = buoys.summarise("46059", buoys.parse_met(DEAD_TXT), None, NOW)
    assert not buoys.is_live(dead, NOW, 6)
    assert dead["met"] == []


def test_cdip_buoy_without_wind():
    s = buoys.summarise("46214", buoys.parse_met(CDIP_TXT), None, NOW)
    assert s["latest"]["wind_speed_mph"] is None
    assert s["latest"]["wave_height_ft"] == 4.9


def test_buoy_fetch_tolerates_missing_spec():
    def route(url, params):
        if url.endswith(".spec"):
            return FakeResponse(404, text="nope")
        return FakeResponse(200, text=NDBC_TXT)

    s = buoys.fetch(FakeSession({"realtime2": route}), "46012", NOW)
    assert s["latest_spectral"] is None
    assert s["latest"] is not None


def test_parse_table_rejects_html():
    with pytest.raises(ValueError):
        buoys.parse_table("<html>maintenance</html>")
