// app/js/model.js + sun.js against the cases pipeline/score.py also passes
// (tests/test_score.py reads the same file), so the app and the evening
// digest agree on what a Good window is.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import {
  daylightFor, hourScore, scoreLabel, sizeScore, tideClasses, whenToGo, windScore,
} from '../../app/js/model.js';
import { sunTimes } from '../../app/js/sun.js';

const CASES = JSON.parse(readFileSync(new URL('../cases/scoring.json', import.meta.url), 'utf8'));
const close = (a, b, msg) => assert.ok(Math.abs(a - b) <= 1e-9, `${msg}: ${a} vs ${b}`);

test('size, wind and hour scores', () => {
  for (const c of CASES.size) close(sizeScore(c.h, c.mode, c.expert), c.expected, JSON.stringify(c));
  for (const c of CASES.wind) close(windScore(c.rel, c.mph), c.expected, JSON.stringify(c));
  for (const c of CASES.hour) close(hourScore(c), c.expected, JSON.stringify(c));
  for (const c of CASES.label) assert.equal(scoreLabel(c.s), c.expected);
});

test('tide classes', () => {
  const c = CASES.tide_classes;
  assert.deepEqual(tideClasses(c.tide, c.times), c.expected);
});

test('sun times', () => {
  for (const c of CASES.sun) {
    const got = sunTimes(c.midnight, c.lat, c.lon);
    for (const [k, v] of Object.entries(c.expected)) {
      assert.ok(Math.abs(got[k] - v) <= 1, `${k} at ${c.lat} ${c.midnight}: ${got[k]} vs ${v}`);
    }
  }
});

for (const c of CASES.when_to_go) {
  test(`whenToGo: ${c.name}`, () => {
    const isDaylight = daylightFor(c.fc, c.spot.lat, c.spot.lon);
    assert.equal(c.fc.time.filter(isDaylight).length, c.expected_daylight_hours);
    const wins = whenToGo({
      fc: c.fc, tide: c.tide, spot: c.spot, mode: c.mode, from: c.from, hours: c.hours, isDaylight, max: c.max,
    });
    assert.deepEqual(
      wins.map((w) => ({ start: w.start, end: w.end, peak_i: w.peak.i, label: w.label })),
      c.expected.map(({ start, end, peak_i, label }) => ({ start, end, peak_i, label })),
    );
    wins.forEach((w, k) => close(w.score, c.expected[k].score, c.name));
  });
}
