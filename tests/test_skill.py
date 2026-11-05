from pipeline import skill

from .conftest import NOW

H = 3600


def _fc(hours, heights):
    return {"time": [NOW + k * H for k in hours], "wave_height": heights}


def test_pairs_use_the_reading_nearest_each_past_hour():
    met = [
        {"time": NOW - 2 * H + 600, "wave_height_ft": 5.0},   # 10 min after -2 h
        {"time": NOW - H - 1800, "wave_height_ft": 9.9},      # 30 min off: too far
        {"time": NOW - 300, "wave_height_ft": 6.0},
        {"time": NOW - 200, "wave_height_ft": None},
    ]
    fc = _fc([-2, -1, 0, 1], [4.0, 4.5, 5.0, 5.5])
    pairs = skill.new_pairs(met, fc, NOW, set())
    assert pairs == [{"t": NOW - 2 * H, "obs": 5.0, "fc": 4.0}, {"t": NOW, "obs": 6.0, "fc": 5.0}]
    # Hours already logged and future hours are skipped.
    assert skill.new_pairs(met, fc, NOW, {NOW - 2 * H, NOW}) == []
    assert skill.new_pairs(met, None, NOW, set()) == []


def test_update_appends_and_drops_old_pairs():
    old = [{"t": NOW - 8 * 86400, "obs": 1, "fc": 1}, {"t": NOW - 2 * H, "obs": 5.0, "fc": 4.0}]
    met = [{"time": NOW, "wave_height_ft": 6.0}]
    log = skill.update(old, met, _fc([-2, 0], [4.0, 5.0]), NOW)
    assert [p["t"] for p in log] == [NOW - 2 * H, NOW]


def test_summary_needs_enough_pairs_and_signs_the_bias():
    log = [{"t": NOW - k * H, "obs": 5.0, "fc": 4.2} for k in range(skill.MIN_PAIRS)]
    s = skill.summarize(log, NOW)
    assert s["pairs"] == skill.MIN_PAIRS
    assert s["bias_ft"] == 0.8          # buoy ran bigger than forecast
    assert s["mean_abs_ft"] == 0.8
    assert skill.summarize(log[:-1], NOW) is None
