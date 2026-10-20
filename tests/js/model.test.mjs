import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  buoyVsForecast, compass, fmtAge, hourIndex, hourScore, inWindow, nearestIndex, sizeScore, swellTrains,
  tideAt, tideClass, tideSuits, wetsuitFor, whenToGo, windScore,
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
  assert.equal(r.where, 'spot');
  assert.equal(r.forecast.periodKind, 'mean');
});

test('buoyVsForecast prefers the forecast made at the buoy itself', () => {
  const buoy = {
    latest: { time: 3600, wave_height_ft: 5.0 },
    forecast: {
      time: [0, 3600], wave_height: [4.0, 4.8], wave_peak_period: [13, 14], wave_period: [9, 9],
      wave_direction: [290, 290], sea_surface_temperature: [57, 57],
    },
  };
  const r = buoyVsForecast(buoy, fc);
  assert.equal(r.where, 'buoy');
  assert.equal(r.delta, 0.2);
  assert.equal(r.forecast.period, 14);
  assert.equal(r.forecast.periodKind, 'peak');
});

test('fmtAge', () => {
  assert.equal(fmtAge(30), 'just now');
  assert.equal(fmtAge(25 * 60), '25 min ago');
  assert.equal(fmtAge(3 * 3600), '3 h ago');
  assert.equal(fmtAge(5400), '1.5 h ago');
});

test('size score suits the mode', () => {
  assert.equal(sizeScore(4, 'bb'), 1);
  assert.ok(sizeScore(9, 'bb') < sizeScore(4, 'bb'));
  assert.ok(sizeScore(9, 'surf') > sizeScore(4, 'surf'));
  assert.ok(sizeScore(20, 'surf') < sizeScore(8, 'surf'));
  assert.ok(sizeScore(20, 'surf', true) > sizeScore(8, 'surf', true)); // big-wave spot
  assert.equal(sizeScore(null), 0);
});

test('wind score: light wind forgives direction, strong onshore does not', () => {
  assert.equal(windScore('offshore', 10), 1);
  assert.equal(windScore('onshore', 3), 0.95);
  assert.equal(windScore('onshore', 20), 0.25);
  assert.ok(windScore('cross', 10) > windScore('onshore', 10));
  assert.ok(hourScore({ h: 4, rel: 'offshore', mph: 8, tideOk: false }) < hourScore({ h: 4, rel: 'offshore', mph: 8 }));
});

// One local day (Oct 20 2026, PDT) of hourly tide: low at 06:00, high at 18:00.
const DAY0 = Date.UTC(2026, 9, 20, 7) / 1000; // local midnight
const tideDay = {
  hourly: {
    time: Array.from({ length: 24 }, (_, k) => DAY0 + k * 3600),
    height: Array.from({ length: 24 }, (_, k) => 3 + 2 * Math.cos(((k - 18) / 24) * 2 * Math.PI)),
    rising: Array.from({ length: 24 }, (_, k) => k >= 6 && k < 18),
  },
  extremes: [],
};

test('tide class follows the day range', () => {
  assert.equal(tideClass(tideDay, DAY0 + 6 * 3600), 'low');
  assert.equal(tideClass(tideDay, DAY0 + 12 * 3600), 'mid');
  assert.equal(tideClass(tideDay, DAY0 + 18 * 3600), 'high');
  assert.equal(tideSuits('low_to_mid', 'mid'), true);
  assert.equal(tideSuits('mid', 'high'), false);
  assert.equal(tideSuits('mid', null), null);
});

test('whenToGo finds the clean daylight window', () => {
  const n = 24;
  const time = Array.from({ length: n }, (_, k) => DAY0 + k * 3600);
  // Offshore 07-10, onshore and blown out after; dark before 7 and after 18.
  const rel = time.map((_, k) => (k >= 7 && k <= 10 ? 'offshore' : 'onshore'));
  const fcDay = {
    time,
    marine: { wave_height: time.map(() => 4) },
    weather: { wind_speed_10m: time.map((_, k) => (k <= 10 ? 6 : 18)) },
    derived: { wind_relation: rel },
  };
  const spot = { tide_preference: 'any' };
  const isDaylight = (t) => t >= DAY0 + 7 * 3600 && t < DAY0 + 18 * 3600;
  const w = whenToGo({ fc: fcDay, tide: tideDay, spot, mode: 'bb', from: DAY0, isDaylight });
  assert.equal(w.length, 1);
  assert.equal(w[0].start, DAY0 + 7 * 3600);
  assert.equal(w[0].end, DAY0 + 11 * 3600);
  assert.equal(w[0].label, 'Good');
  // Nothing worth it: tiny and onshore all day.
  fcDay.marine.wave_height = time.map(() => 0.5);
  assert.deepEqual(whenToGo({ fc: fcDay, tide: tideDay, spot, from: DAY0, isDaylight }), []);
});

test('wetsuit rule of thumb', () => {
  assert.equal(wetsuitFor(50), '5/4 with hood and booties');
  assert.equal(wetsuitFor(58), '4/3');
  assert.equal(wetsuitFor(62), '3/2');
  assert.equal(wetsuitFor(null), null);
});
