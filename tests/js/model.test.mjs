import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  buoyVsForecast, compass, fmtAge, hourIndex, inWindow, nearestIndex, swellTrains, tideAt,
} from '../../app/js/model.js';

test('compass points', () => {
  assert.equal(compass(0), 'N');
  assert.equal(compass(290), 'WNW');
  assert.equal(compass(359), 'N');
  assert.equal(compass(-90), 'W');
  assert.equal(compass(null), '–');
});

test('inWindow matches the pipeline rule, including wrap past north', () => {
  assert.equal(inWindow(285, 250, 320), true);
  assert.equal(inWindow(200, 250, 320), false);
  assert.equal(inWindow(10, 300, 30), true);
  assert.equal(inWindow(200, 300, 30), false);
  assert.equal(inWindow(null, 0, 90), null);
});

test('hourIndex and nearestIndex', () => {
  const t = [100, 3700, 7300];
  assert.equal(hourIndex(t, 50), 0);
  assert.equal(hourIndex(t, 3700), 1);
  assert.equal(hourIndex(t, 7000), 1);
  assert.equal(hourIndex(t, 99999), 2);
  assert.equal(hourIndex([], 1), -1);
  assert.equal(nearestIndex(t, 7000), 2);
  assert.equal(nearestIndex(t, 99999), -1);
});

const fc = {
  time: [0, 3600],
  marine: {
    wave_height: [4.2, 4.4], wave_period: [9.6, 9.8], wave_direction: [283, 284],
    sea_surface_temperature: [59.8, 59.7],
    swell_wave_height: [3.1, 3.2], swell_wave_direction: [305, 303], swell_wave_period: [5.1, 5.5],
    secondary_swell_wave_height: [3.5, 1.9], secondary_swell_wave_direction: [200, 219],
    secondary_swell_wave_period: [14, 9.8],
    tertiary_swell_wave_height: [null, null], tertiary_swell_wave_direction: [null, null],
    tertiary_swell_wave_period: [null, null],
    wind_wave_height: [0.3, 0.2], wind_wave_direction: [341, 339], wind_wave_period: [1.4, 1.2],
  },
};

test('swellTrains sorts swells by height, flags window, puts wind waves last', () => {
  const trains = swellTrains(fc, 0, { from: 250, to: 320 });
  assert.deepEqual(trains.map((t) => t.label), ['Secondary swell', 'Primary swell', 'Wind waves']);
  assert.equal(trains[0].inWindow, false); // 200 is south of the window
  assert.equal(trains[1].inWindow, true);
  assert.equal(trains[2].inWindow, null);
});

test('tideAt interpolates and reads direction from the next extreme', () => {
  const tide = {
    extremes: [{ t: 0, v: 5, type: 'H' }, { t: 21600, v: 1, type: 'L' }],
    hourly: { time: [0, 3600, 7200], height: [5, 4, 3], rising: [false, false, false] },
  };
  const r = tideAt(tide, 1800);
  assert.equal(r.height, 4.5);
  assert.equal(r.rising, false);
  assert.equal(r.next.type, 'L');
  assert.equal(tideAt(tide, 999999), null);
  assert.equal(tideAt(null, 0), null);
});

test('buoyVsForecast compares the reading with the matching forecast hour', () => {
  const buoy = { latest: { time: 3000, wave_height_ft: 5.0 } };
  const r = buoyVsForecast(buoy, fc);
  assert.equal(r.forecast.time, 3600);
  assert.equal(r.delta, 0.6);
  assert.equal(buoyVsForecast({ latest: { time: 99999, wave_height_ft: 5 } }, fc).forecast, null);
  assert.equal(buoyVsForecast({ latest: null }, fc), null);
});

test('fmtAge', () => {
  assert.equal(fmtAge(30), 'just now');
  assert.equal(fmtAge(25 * 60), '25 min ago');
  assert.equal(fmtAge(3 * 3600), '3 h ago');
  assert.equal(fmtAge(5400), '1.5 h ago');
});
