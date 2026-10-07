"""Shared fixtures: a fake HTTP session that serves canned responses.

The canned payloads mirror the real formats of each API (checked against live
responses by `python -m pipeline.verify` in the verify-sources workflow).
"""

import json

import pytest

# 2026-10-07 20:00 UTC
NOW = 1791403200

NDBC_TXT = """\
#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft
2026 10 07 17 50 300  7.0  9.0   2.1    14   8.2 290 1016.1  14.2  14.8  11.0   MM -0.6    MM
2026 10 07 17 40 300  7.0  9.0    MM    MM    MM  MM 1016.1  14.2  14.8  11.0   MM   MM    MM
2026 10 07 16 50 310  6.0  8.0   2.0    13   8.0 285 1016.4  14.1  14.7  11.0   MM   MM    MM
2026 10 04 16 50 310  6.0  8.0   1.0    10   7.0 280 1016.4  14.1  14.7  11.0   MM   MM    MM
"""

NDBC_SPEC = """\
#YY  MM DD hh mm WVHT  SwH  SwP  WWH  WWP SwD WWD  STEEPNESS  APD MWD
#yr  mo dy hr mn    m    m  sec    m  sec  -  degT     -      sec degT
2026 10 07 17 40  2.1  1.9 14.3  0.8  5.6 WNW  NW    AVERAGE  8.2 290
2026 10 07 16 40  2.0  1.8 13.3  0.8  5.0  W  NW        N/A  8.0 285
"""

# CDIP buoys on NDBC report no wind columns' values.
CDIP_TXT = """\
#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft
2026 10 07 17 56  MM   MM   MM   1.5    15   9.0 275     MM    MM  15.0    MM   MM   MM    MM
"""

DEAD_TXT = """\
#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft
2026 09 01 00 50 300  7.0  9.0   2.1    14   8.2 290 1016.1  14.2  14.8  11.0   MM   MM    MM
"""

COOPS_HILO = {
    "predictions": [
        {"t": "2026-10-06 02:00", "v": "5.500", "type": "H"},
        {"t": "2026-10-06 08:00", "v": "0.500", "type": "L"},
        {"t": "2026-10-06 14:00", "v": "4.500", "type": "H"},
        {"t": "2026-10-06 20:00", "v": "1.500", "type": "L"},
    ]
}

COOPS_META = {"count": 1, "stations": [{"id": "9414131", "name": "Pillar Point",
                                         "lat": 37.5025, "lng": -122.4822}]}


def _hours(n=48, start=NOW - 18 * 3600):
    return [start + 3600 * i for i in range(n)]


def marine_location(n_hours=48, wave_m=1.5):
    from pipeline.openmeteo import MARINE_HOURLY

    hourly = {"time": _hours(n_hours)}
    units = {"time": "unixtime"}
    for v in MARINE_HOURLY:
        if v.endswith("_height"):
            hourly[v], units[v] = [wave_m] * n_hours, "m"
        elif v.endswith("_direction"):
            hourly[v], units[v] = [285] * n_hours, "°"
        elif v.endswith("_period"):
            hourly[v], units[v] = [14.0] * n_hours, "s"
        else:  # sea_surface_temperature
            hourly[v], units[v] = [13.0] * n_hours, "°C"
    return {"latitude": 37.5, "longitude": -122.5, "hourly_units": units, "hourly": hourly}


def weather_location(n_hours=48):
    days = [NOW - 18 * 3600 + 86400 * d for d in range(2)]
    return {
        "hourly_units": {"time": "unixtime", "wind_speed_10m": "mp/h",
                         "wind_direction_10m": "°", "wind_gusts_10m": "mp/h",
                         "temperature_2m": "°F", "weather_code": "wmo code"},
        "hourly": {"time": _hours(n_hours), "wind_speed_10m": [8.0] * n_hours,
                   "wind_direction_10m": [100] * n_hours, "wind_gusts_10m": [12.0] * n_hours,
                   "temperature_2m": [61.0] * n_hours, "weather_code": [1] * n_hours},
        "daily_units": {"time": "unixtime", "sunrise": "unixtime", "sunset": "unixtime"},
        "daily": {"time": days, "sunrise": [d + 14 * 3600 for d in days],
                  "sunset": [d + 25 * 3600 for d in days]},
    }


class FakeResponse:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    """Routes GETs by URL substring to a handler; records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.posts = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        for key, handler in self.routes.items():
            if key in url:
                return handler(url, params) if callable(handler) else handler
        return FakeResponse(404, text="not found")

    def post(self, url, data=None, headers=None, timeout=None):
        self.posts.append((url, data, headers))
        return FakeResponse(200, body={"id": "x"})


def _multi(make):
    def handler(url, params):
        n = len(params["latitude"].split(","))
        return FakeResponse(200, body=[make() for _ in range(n)])
    return handler


def healthy_routes():
    def ndbc(url, params):
        if url.endswith(".spec"):
            return FakeResponse(200, text=NDBC_SPEC)
        if "/462" in url:
            return FakeResponse(200, text=CDIP_TXT)
        return FakeResponse(200, text=NDBC_TXT)

    return {
        "marine-api.open-meteo.com": _multi(marine_location),
        "api.open-meteo.com": _multi(weather_location),
        "datagetter": FakeResponse(200, body=COOPS_HILO),
        "mdapi": FakeResponse(200, body=COOPS_META),
        "realtime2": ndbc,
    }


@pytest.fixture
def healthy_session():
    return FakeSession(healthy_routes())
