import copy

import pytest

from pipeline import spots
from pipeline.geo import angle_diff, haversine_km


@pytest.fixture(scope="module")
def doc():
    return spots.load()


def test_spots_file_is_valid(doc):
    assert spots.validate(doc) == []
    assert 20 <= len(doc["spots"]) <= 40


def test_required_regions_present(doc):
    regions = {s["region"] for s in doc["spots"]}
    assert {"north_coast", "half_moon_bay", "santa_cruz", "slo"} <= regions
    assert "mavericks" in {s["id"] for s in doc["spots"]}


def test_buoys_and_tide_stations_are_reasonably_close(doc):
    for s in doc["spots"]:
        b = doc["buoys"][s["buoy"]["nearest"]]
        assert haversine_km(s["lat"], s["lon"], b["lat"], b["lon"]) < 120, s["id"]
        t = doc["tide_stations"][s["tide_station"]]
        assert haversine_km(s["lat"], s["lon"], t["lat"], t["lon"]) < 100, s["id"]


def test_swell_window_faces_the_sea(doc):
    # The middle of the swell window should be within 90 deg of the facing direction.
    for s in doc["spots"]:
        w = s["swell_window"]
        width = (w["to"] - w["from"]) % 360
        mid = (w["from"] + width / 2) % 360
        assert 0 < width <= 180, s["id"]
        assert angle_diff(mid, s["facing_deg"]) <= 90, s["id"]


def test_forecast_point_is_offshore_of_beach(doc):
    for s in doc["spots"]:
        lat, lon = spots.forecast_point(s)
        d = haversine_km(s["lat"], s["lon"], lat, lon)
        assert 1 <= d <= 15, s["id"]
        # California coast faces roughly west, so offshore points sit west or south.
        assert lon <= s["lon"] + 0.01 or lat < s["lat"], s["id"]


def test_validate_catches_bad_references(doc):
    bad = copy.deepcopy(doc)
    bad["spots"][0]["buoy"]["nearest"] = "99999"
    bad["spots"][1]["tide_station"] = "0000000"
    bad["spots"][2]["break_type"] = "slab"
    bad["spots"][3]["id"] = bad["spots"][4]["id"]
    errs = "\n".join(spots.validate(bad))
    assert "99999" in errs
    assert "0000000" in errs
    assert "break_type" in errs
    assert "duplicate" in errs


def test_used_buoys_includes_registry_only_buoys(doc):
    assert "46059" in spots.used_buoys(doc)
