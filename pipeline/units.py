"""Unit conversions. Published JSON uses ft, mph and °F."""

FT_PER_M = 3.28084
MPH_PER_MS = 2.236936
MPH_PER_KNOT = 1.150779
MPH_PER_KMH = 0.621371


def _r(x, nd):
    return None if x is None else round(x, nd)


def m_to_ft(x):
    return _r(None if x is None else x * FT_PER_M, 1)


def ms_to_mph(x):
    return _r(None if x is None else x * MPH_PER_MS, 1)


def c_to_f(x):
    return _r(None if x is None else x * 9 / 5 + 32, 1)


# Normalisers keyed by the unit string a source reports.
_HEIGHT = {"ft": lambda x: _r(x, 1), "m": m_to_ft}
_SPEED = {
    "mp/h": lambda x: _r(x, 1),
    "mph": lambda x: _r(x, 1),
    "km/h": lambda x: _r(None if x is None else x * MPH_PER_KMH, 1),
    "m/s": ms_to_mph,
    "kn": lambda x: _r(None if x is None else x * MPH_PER_KNOT, 1),
}
_TEMP = {"°F": lambda x: _r(x, 1), "°C": c_to_f}
_PASS = {"°": lambda x: _r(x, 0), "s": lambda x: _r(x, 1)}


def normaliser(unit: str):
    """Return a function converting values in `unit` to the app's units.

    Raises ValueError for a unit we don't recognise, so a silent API change
    can't publish metres labelled as feet.
    """
    for table in (_HEIGHT, _SPEED, _TEMP, _PASS):
        if unit in table:
            return table[unit]
    raise ValueError(f"unrecognised unit {unit!r}")
