from pipeline import mavericks as mv

H = 3600
NOW = 1793430000 + 10 * H  # 2026-10-31 10:00 PDT
NAMES = {"46059": "West California", "46214": "Point Reyes", "46012": "Half Moon Bay"}


def fc_with(peaks: dict[int, float], base=8.0, hours=200):
    """Mavericks forecast from 2 h ago: `base` ft, with {hours ahead: ft} overrides."""
    start = NOW - NOW % H - 2 * H
    times = [start + k * H for k in range(hours)]
    heights = [peaks.get((t - (NOW - NOW % H)) // H, base) for t in times]
    return {"time": times, "marine": {"wave_height": heights}}


def buoy(period=13.0, age_h=0.5, height=6.0, swell_period=None):
    t = NOW - int(age_h * H)
    return {
        "latest": {"time": t, "wave_height_ft": height, "dominant_period_s": period},
        "latest_spectral": None if swell_period is None
        else {"time": t, "swell_period_s": swell_period},
    }


BUOY_FC = {"time": [NOW - NOW % H + k * H for k in range(-3, 48)],
           "swell_wave_period": [15.0] * 51, "wave_period": [11.0] * 51}


class Fetch:
    def __init__(self, offshore=None):
        self.calls = []
        self.offshore = offshore or buoy()

    def __call__(self, bid):
        self.calls.append(bid)
        return self.offshore if bid == "46059" else buoy(period=12)


def test_quiet_forecast_stays_idle_without_touching_buoys():
    f = Fetch()
    state, msgs = mv.step(None, fc_with({30: 12}), BUOY_FC, NOW, f, NAMES)
    assert state == {"status": "idle"} and msgs == [] and f.calls == []


def test_big_forecast_within_5_days_switches_on_and_checks_buoys():
    f = Fetch()
    state, msgs = mv.step({"status": "idle"}, fc_with({70: 16, 71: 18, 72: 17}), BUOY_FC,
                          NOW, f, NAMES)
    assert state["status"] == "armed" and state["peak_ft"] == 18
    assert [m["title"] for m in msgs] == ["Mavericks Watch on"]
    assert f.calls == ["46059", "46214", "46012"]


def test_big_hour_beyond_5_days_is_ignored():
    state, _ = mv.step(None, fc_with({130: 20}), BUOY_FC, NOW, Fetch(), NAMES)
    assert state["status"] == "idle"


def armed(**over):
    s = {"status": "armed", "armed_at": NOW - 24 * H, "peak_ft": 18, "peak_t": NOW + 40 * H,
         "last_big_t": NOW + 42 * H, "forerunners_at": None}
    return s | over


def test_forerunners_ping_once_and_compare_with_forecast():
    f = Fetch(buoy(period=19))
    state, msgs = mv.step(armed(), fc_with({40: 18}), BUOY_FC, NOW, f, NAMES)
    assert [m["title"] for m in msgs] == ["Mavericks forerunners at 46059"]
    text = msgs[0]["message"]
    assert "shows 19 s" in text
    assert "Forecast at 46059 for that hour: 15 s swell period" in text
    assert "longer than forecast" in text
    assert "46214 Point Reyes" in text and "46012 Half Moon Bay" in text
    assert state["forerunners_at"] == NOW
    _, again = mv.step(state, fc_with({40: 18}), BUOY_FC, NOW + 1800, f, NAMES)
    assert again == []


def test_spectral_swell_period_counts_and_stale_readings_do_not():
    _, msgs = mv.step(armed(), fc_with({40: 18}), BUOY_FC, NOW,
                      Fetch(buoy(period=12, swell_period=18.2)), NAMES)
    assert len(msgs) == 1 and "about as forecast" not in msgs[0]["message"]
    _, msgs = mv.step(armed(), fc_with({40: 18}), BUOY_FC, NOW, Fetch(buoy(19, age_h=5)), NAMES)
    assert msgs == []


def test_period_near_forecast_reads_as_forecast():
    fc = dict(BUOY_FC, swell_wave_period=[18.0] * 51)
    _, msgs = mv.step(armed(), fc_with({40: 18}), fc, NOW, Fetch(buoy(19)), NAMES)
    assert "about as forecast" in msgs[0]["message"]


def test_stands_down_after_the_swell_passes():
    f = Fetch()
    state, msgs = mv.step(armed(last_big_t=NOW - 13 * H, forerunners_at=NOW - 40 * H),
                          fc_with({}), BUOY_FC, NOW, f, NAMES)
    assert state["status"] == "idle" and state["last_watch"]["peak_ft"] == 18
    assert msgs[0]["title"] == "Mavericks Watch off" and "passed" in msgs[0]["message"]
    assert f.calls == []
    # Not yet 12 h after the last big hour: stays on.
    state, msgs = mv.step(armed(last_big_t=NOW - 6 * H), fc_with({}), BUOY_FC, NOW, f, NAMES)
    assert state["status"] == "armed" and msgs == []


def test_downgrade_before_arrival_stands_down_but_a_near_miss_does_not():
    state, msgs = mv.step(armed(), fc_with({40: 12}), BUOY_FC, NOW, Fetch(), NAMES)
    assert state["status"] == "idle" and "dropped to 12 ft" in msgs[0]["message"]
    state, msgs = mv.step(armed(), fc_with({40: 14.5}), BUOY_FC, NOW, Fetch(), NAMES)
    assert state["status"] == "armed" and msgs == []


def test_a_new_swell_rearms_after_standing_down():
    idle = {"status": "idle", "last_watch": {"peak_ft": 18}}
    state, msgs = mv.step(idle, fc_with({}), BUOY_FC, NOW, Fetch(), NAMES)
    assert state == idle and msgs == []
    state, msgs = mv.step(idle, fc_with({50: 21}), BUOY_FC, NOW, Fetch(), NAMES)
    assert state["status"] == "armed" and msgs[0]["title"] == "Mavericks Watch on"
