import pytest

from pipeline.geo import (
    angle_diff,
    compass_to_deg,
    destination,
    haversine_km,
    in_window,
    wind_relation,
)
from pipeline.units import c_to_f, m_to_ft, ms_to_mph, normaliser


def test_haversine_sf_to_la():
    # SF City Hall to LA City Hall is ~559 km great-circle.
    assert haversine_km(37.7793, -122.4193, 34.0537, -118.2428) == pytest.approx(559, abs=3)


def test_destination_round_trip():
    lat, lon = destination(37.5, -122.5, 270, 3.0)
    assert lat == pytest.approx(37.5, abs=0.001)
    assert lon < -122.5
    assert haversine_km(37.5, -122.5, lat, lon) == pytest.approx(3.0, abs=0.01)


@pytest.mark.parametrize("a,b,expected", [(10, 350, 20), (0, 180, 180), (90, 90, 0),
                                          (359, 1, 2)])
def test_angle_diff(a, b, expected):
    assert angle_diff(a, b) == expected


@pytest.mark.parametrize("d,start,end,expected", [
    (280, 250, 320, True),
    (240, 250, 320, False),
    (250, 250, 320, True),   # inclusive edges
    (350, 330, 20, True),    # window wrapping through north
    (10, 330, 20, True),
    (100, 330, 20, False),
    (None, 0, 90, None),
])
def test_in_window(d, start, end, expected):
    assert in_window(d, start, end) is expected


@pytest.mark.parametrize("wind_from,facing,expected", [
    (270, 270, "onshore"),   # west wind on a west-facing beach
    (90, 270, "offshore"),
    (0, 270, "cross"),
    (180, 270, "cross"),
    (110, 290, "offshore"),
    (350, 20, "onshore"),
    (None, 270, None),
])
def test_wind_relation(wind_from, facing, expected):
    assert wind_relation(wind_from, facing) == expected


def test_compass_to_deg():
    assert compass_to_deg("N") == 0
    assert compass_to_deg("WNW") == 292.5
    assert compass_to_deg("sw") == 225
    assert compass_to_deg("MM") is None


def test_unit_conversions():
    assert m_to_ft(1.0) == 3.3
    assert ms_to_mph(10) == 22.4
    assert c_to_f(15) == 59.0
    assert m_to_ft(None) is None


def test_normaliser_rejects_unknown_unit():
    assert normaliser("m")(2.0) == 6.6
    assert normaliser("ft")(6.55) == pytest.approx(6.5, abs=0.06)
    assert normaliser("°C")(0) == 32.0
    with pytest.raises(ValueError):
        normaliser("furlongs")
