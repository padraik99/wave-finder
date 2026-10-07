import assert from 'node:assert/strict';
import { test } from 'node:test';
import { sunTimes } from '../../app/js/sun.js';

// Open-Meteo sunrise/sunset from the live data branch (2026-10-07 and
// 2026-10-22, local midnights in PDT), for spots spanning the coast.
const CASES = [
  { id: 'mavericks', lat: 37.4925, lon: -122.501, days: [
    [1791356400, 1791382260, 1791423832], [1792652400, 1792679107, 1792718592]] },
  { id: 'north_jetty_humboldt', lat: 40.768, lon: -124.237, days: [
    [1791356400, 1791382783, 1791424115], [1792652400, 1792679761, 1792718744]] },
  { id: 'pismo_pier', lat: 35.138, lon: -120.644, days: [
    [1791356400, 1791381731, 1791423467], [1792652400, 1792678490, 1792718316]] },
];

for (const c of CASES) {
  test(`sunrise/sunset match Open-Meteo within 2 min at ${c.id}`, () => {
    for (const [midnight, rise, set] of c.days) {
      const t = sunTimes(midnight, c.lat, c.lon);
      assert.ok(Math.abs(t.sunrise - rise) <= 120, `sunrise off by ${t.sunrise - rise}s`);
      assert.ok(Math.abs(t.sunset - set) <= 120, `sunset off by ${t.sunset - set}s`);
    }
  });
}

test('first light is 24-32 min before sunrise in October California', () => {
  for (const c of CASES) {
    const t = sunTimes(c.days[0][0], c.lat, c.lon);
    const lead = (t.sunrise - t.firstLight) / 60;
    const lag = (t.lastLight - t.sunset) / 60;
    assert.ok(lead > 24 && lead < 32, `${c.id} lead ${lead}`);
    assert.ok(lag > 24 && lag < 32, `${c.id} lag ${lag}`);
  }
});
