// faceRange against the cases pipeline/score.py face_range also passes
// (tests/test_faces.py reads the same file).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { faceRange, fcPeriod } from '../../app/js/model.js';

const CASES = JSON.parse(readFileSync(new URL('../cases/faces.json', import.meta.url), 'utf8'));

test('face range matches the Python twin', () => {
  for (const c of CASES.cases) assert.deepEqual(faceRange(c.hs, c.period), c.expected, JSON.stringify(c));
});

test('fcPeriod takes the longer period', () => {
  const m = { wave_period: [16, null], swell_wave_period: [13.5, null] };
  assert.equal(fcPeriod(m, 0), 16);
  assert.equal(fcPeriod(m, 1), null);
});
