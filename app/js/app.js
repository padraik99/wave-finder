// Wave Finder app: hash-routed screens.
//   #/            opener: region wheel and starred spots
//   #/zone/<id>   one zone's spots, now + 72 h outlook
//   #/spot/<id>   spot detail with the hour scrubber and live buoy panel

import {
  aboutOpen, clearMemo, getJSON, goodConnection, isStarred, lastZone, noteAboutOpen, noteRecent,
  noteZone, recentSpots, starredSpots, toggleStar,
} from './data.js';
import {
  RELATION, buoyVsForecast, compass, distanceMi, fmtAge, fmtDate, fmtHour, fmtTime, fmtWeekday,
  ft, hourIndex, localDayKey, swellTrains, tideAt, weatherLabel, whole,
} from './model.js';
import { sunTimes } from './sun.js';
import { dirArrow, relClass, scrubberStrip, sparkline, tideCurve, windDiagram } from './svg.js';

const $app = document.getElementById('app');
const BAR_W = 12;
const STALE_AFTER_S = 2.5 * 3600; // fetch runs hourly; allow a late run or two

// The wheel's three zones, north to south, each a list of spots.json regions.
const ZONES = [
  { id: 'norcal', name: 'NorCal', regions: ['north_coast', 'san_francisco', 'half_moon_bay', 'santa_cruz'] },
  { id: 'central', name: 'Central', regions: ['slo', 'santa_barbara'] },
  { id: 'socal', name: 'SoCal', regions: ['orange_county'] },
];

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));
const now = () => Math.floor(Date.now() / 1000);

// ---- Shared ---------------------------------------------------------------

async function loadCore(fresh) {
  const [index, spots] = await Promise.all([
    getJSON('index.json', { fresh }),
    getJSON('spots.json', { fresh }),
  ]);
  return { index: index.data, spots: spots.data, fromCache: index.fromCache };
}

function freshness(generatedAt, fromCache) {
  const age = now() - Date.parse(generatedAt) / 1000;
  const text = `Forecast updated ${fmtAge(age)}`;
  if (fromCache) return `<p class="banner warn">Offline. Showing saved data · ${esc(text)}</p>`;
  if (age > STALE_AFTER_S) return `<p class="banner warn">${esc(text)}. The data feed may be stuck.</p>`;
  return `<p class="updated">${esc(text)}</p>`;
}

function errorScreen(err, what = "Couldn't load data and nothing is saved yet.") {
  $app.innerHTML = `<main class="screen">
    <header class="top"><a class="icon-btn" href="#/" aria-label="Back">←</a><h1>Wave Finder</h1></header>
    <p class="banner warn">${esc(what)}<br><small>${esc(err.message)}</small></p>
    <button class="btn" onclick="location.reload()">Try again</button></main>`;
}

// Zone of a region. A region missing from ZONES (added to spots.json later)
// goes by its spots' latitude, so it still shows up somewhere sensible.
function zoneOf(regionId, spots) {
  const z = ZONES.find((zz) => zz.regions.includes(regionId));
  if (z) return z.id;
  const lats = spots.spots.filter((s) => s.region === regionId).map((s) => s.lat);
  const lat = lats.reduce((a, b) => a + b, 0) / (lats.length || 1);
  return lat > 36.5 ? 'norcal' : lat > 34.2 ? 'central' : 'socal';
}

function zoneRegions(zoneId, spots) {
  return spots.regions.filter((r) => zoneOf(r.id, spots) === zoneId);
}

// Spots of a zone in list order: north to south as spots.json has them.
function zoneSpots(zoneId, spots) {
  const ids = zoneRegions(zoneId, spots).map((r) => r.id);
  return ids.flatMap((rid) => spots.spots.filter((s) => s.region === rid));
}

// Conditions right now from the 72 h outlook in index.json.
function nowFor(entry, t) {
  const o = entry?.outlook;
  const i = o ? Math.floor((t - o.start) / 3600) : -1;
  if (!o || i < 0 || i >= o.wave_height.length) return null;
  return {
    h: o.wave_height[i],
    rel: RELATION[o.wind[i]],
    wind: o.wind_speed[i],
    rest: o.wave_height.slice(i),
    restWind: o.wind.slice(i),
  };
}

const starBtn = (id, name) => {
  const on = isStarred(id);
  return `<button class="star${on ? ' on' : ''}" data-star="${esc(id)}" aria-pressed="${on}"
    aria-label="${on ? 'Unstar' : 'Star'} ${esc(name)}">${on ? '★' : '☆'}</button>`;
};

function bindStars(root, onChange) {
  root.querySelectorAll('[data-star]').forEach((b) => {
    b.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      const on = toggleStar(b.dataset.star);
      b.classList.toggle('on', on);
      b.textContent = on ? '★' : '☆';
      b.setAttribute('aria-pressed', on);
      b.setAttribute('aria-label', b.getAttribute('aria-label').replace(/^(Un)?[Ss]tar/, on ? 'Unstar' : 'Star'));
      onChange?.();
    };
  });
}

function spotRow(s, cur, maxH) {
  return `<li class="spot-item">${starBtn(s.id, s.name)}<a class="spot-row" href="#/spot/${esc(s.id)}">
    <span class="spot-name">${esc(s.name)}${s.skill === 'expert_only' ? ' <span class="tag">experts</span>' : ''}</span>
    <span class="spot-now"><b>${ft(cur?.h)}</b><small>ft</small></span>
    <span class="chip ${relClass(cur?.rel)}">${cur?.rel ? `${esc(cur.rel)} ${whole(cur.wind)}` : 'no data'}</span>
    ${sparkline(cur?.rest || [], cur?.restWind || '', maxH)}
  </a></li>`;
}

const WIND_WEIGHT = { offshore: 1, cross: 0.8, onshore: 0.6 };

// The starred spot worth driving to right now: wave height discounted for
// wind (onshore counts for 60 %). Expert-only spots are skipped unless they
// are all that is starred: Mavericks shouldn't win every day.
function bestOf(list) {
  const scored = list.filter((x) => x.cur?.h != null)
    .map((x) => ({ ...x, score: x.cur.h * (WIND_WEIGHT[x.cur.rel] ?? 0.5) }));
  const pool = scored.some((x) => x.spot.skill !== 'expert_only')
    ? scored.filter((x) => x.spot.skill !== 'expert_only') : scored;
  return pool.sort((a, b) => b.score - a.score)[0] || null;
}

// ---- Opener -----------------------------------------------------------------

// Half wheel on the left edge, centre at (0, R). The slot pointing straight
// right is always the selection; the zones rotate through it. Zone k sits at
// angle WHEEL_STEP * (k - middle) on the unrotated wheel, so turning the
// wheel by -that angle brings it into the slot.
const WHEEL_R = 175;
const WHEEL_STEP = 50;
const wheelAngle = (k) => WHEEL_STEP * (k - (ZONES.length - 1) / 2);

function wheelSvg(selected, counts) {
  const R = WHEEL_R;
  const r = 70;
  const pt = (rad, deg) => {
    const a = (deg * Math.PI) / 180;
    return [rad * Math.cos(a), R + rad * Math.sin(a)].map((v) => v.toFixed(1));
  };
  const wedges = ZONES.map((z, k) => {
    const c = wheelAngle(k);
    const a0 = c - WHEEL_STEP / 2 + 1;
    const a1 = c + WHEEL_STEP / 2 - 1;
    const [lx, ly] = pt((R + r) / 2, c).map(Number);
    const n = counts[z.id] || 0;
    return `<a href="#/zone/${z.id}" class="wedge${z.id === selected ? ' sel' : ''}${n ? '' : ' empty'}"
        data-zone="${z.id}" aria-label="${esc(z.name)}, ${n} spots">
      <path d="M${pt(R, a0)} A${R} ${R} 0 0 1 ${pt(R, a1)} L${pt(r, a1)} A${r} ${r} 0 0 0 ${pt(r, a0)} Z"></path>
      <g class="w-label" style="transform-origin: ${lx}px ${ly + 8}px">
        <text x="${lx}" y="${ly}" text-anchor="middle" class="w-name">${esc(z.name)}</text>
        <text x="${lx}" y="${ly + 17}" text-anchor="middle" class="w-count">${n} spots</text>
      </g>
    </a>`;
  }).join('');
  return `<svg class="wheel" viewBox="0 0 ${R + 16} ${2 * R}" width="${R + 16}" height="${2 * R}">
    <g class="rotor">${wedges}</g>
    <polygon class="slot" points="${R + 15},${R - 10} ${R + 15},${R + 10} ${R + 3},${R}"></polygon>
  </svg>`;
}

// First sentence of a spot's notes: its one-line "what's special here".
const feature = (notes) => (notes || '').split(/(?<=\.)\s/)[0];

function starCards(zone, stars) {
  const here = stars.filter((x) => zoneOf(x.spot.region, x.spots) === zone.id);
  if (!here.length) {
    return `<p class="muted hint">No starred beaches in ${esc(zone.name)} yet. Open the list and tap ☆ to add some.</p>`;
  }
  const best = bestOf(here);
  return `${best && here.length > 1 ? `<p class="best-line">Best right now: <b>${esc(best.spot.name)}</b>
      <small>(height, discounted for cross and onshore wind${best.spot.skill === 'expert_only' ? '' : '; expert-only left out'})</small></p>` : ''}
    <ul class="star-cards">${here.map(({ spot, cur }) => `<li><a class="star-card${best && here.length > 1 && best.spot.id === spot.id ? ' top' : ''}" href="#/spot/${esc(spot.id)}">
      <span class="sc-head"><span class="star-name">${esc(spot.name)}</span>
        <b class="sc-num">${ft(cur?.h)}<small> ft</small></b></span>
      <span class="sc-wind"><span class="chip ${relClass(cur?.rel)}">${cur?.rel ? `${esc(cur.rel)} ${whole(cur.wind)}` : 'no data'}</span>
        ${spot.skill === 'expert_only' ? '<span class="tag">experts only</span>' : ''}
        ${spot.bodyboard ? '<span class="tag bb">good for bodyboarding</span>' : ''}</span>
      <span class="sc-feature">${esc(feature(spot.notes))}</span>
    </a></li>`).join('')}</ul>`;
}

async function renderOpener(fresh = false) {
  let core;
  try {
    core = await loadCore(fresh);
  } catch (err) {
    errorScreen(err);
    return;
  }
  const { index, spots, fromCache } = core;
  // A zone opened from here starts at the top; only Back from a spot restores.
  ZONES.forEach((z) => { try { sessionStorage.removeItem(`wf-scroll-${z.id}`); } catch { /* none */ } });
  const byId = Object.fromEntries(index.spots.map((s) => [s.id, s]));
  const t = now();
  const counts = Object.fromEntries(ZONES.map((z) => [z.id, zoneSpots(z.id, spots).length]));
  let selected = lastZone();
  if (!counts[selected]) selected = ZONES.find((z) => counts[z.id])?.id || ZONES[0].id;
  const zoneById = (id) => ZONES.find((z) => z.id === id);

  const stars = starredSpots()
    .map((id) => spots.spots.find((s) => s.id === id))
    .filter(Boolean)
    .map((spot) => ({ spot, spots, cur: nowFor(byId[spot.id], t) }));

  $app.innerHTML = `<main class="screen opener">
    <header class="opener-top">
      <div><p class="eyebrow">California surf</p><h1>Wave Finder</h1></div>
      <button class="icon-btn" id="refresh" aria-label="Refresh">⟳</button>
    </header>
    ${freshness(index.generated_at, fromCache)}
    <div class="opener-body">
      <nav class="wheel-wrap" aria-label="Regions">${wheelSvg(selected, counts)}</nav>
      <div class="zone-pick">
        <p class="eyebrow">Region</p>
        <p class="zone-name" id="zone-name">${esc(zoneById(selected).name)}</p>
        <p class="muted" id="zone-desc"></p>
        <a class="btn primary go" id="go" href="#/zone/${selected}">Show beaches</a>
        <p class="fine">Spin the wheel, or tap a zone.</p>
      </div>
    </div>
    <section class="starred" aria-live="polite">
      <h2 class="eyebrow" id="star-head"></h2>
      <div id="zone-stars"></div>
    </section>
    <svg class="waves" viewBox="0 0 400 120" preserveAspectRatio="none" aria-hidden="true">
      <path class="w1" d="M-20 50 C 60 30 120 70 200 48 S 330 30 420 50 L420 120 L-20 120 Z"></path>
      <path class="w2" d="M-20 72 C 70 52 140 92 220 70 S 340 56 420 72 L420 120 L-20 120 Z"></path>
      <path class="w3" d="M-20 94 C 80 78 160 108 240 92 S 350 84 420 94 L420 120 L-20 120 Z"></path>
    </svg>
  </main>`;

  document.getElementById('refresh').onclick = () => { clearMemo(); renderOpener(true); };
  const pick = (id) => {
    selected = id;
    noteZone(id);
    const zone = zoneById(id);
    document.getElementById('go').href = `#/zone/${id}`;
    document.getElementById('zone-name').textContent = zone.name;
    document.getElementById('zone-desc').textContent = zoneRegions(id, spots).map((r) => r.name).join(' · ');
    document.getElementById('star-head').textContent = `Starred in ${zone.name}`;
    document.getElementById('zone-stars').innerHTML = starCards(zone, stars);
    $app.querySelectorAll('.wedge').forEach((w) => w.classList.toggle('sel', w.dataset.zone === id));
  };
  // Spin: drag the wheel up or down; it turns with the finger, within the
  // first and last zones (plus a little give), then snaps to the nearest one.
  const wrap = $app.querySelector('.wheel-wrap');
  const rotor = $app.querySelector('.rotor');
  const wedgeEls = [...$app.querySelectorAll('.wedge')];
  const live = ZONES.map((z, k) => k).filter((k) => counts[ZONES[k].id]);
  const maxTurn = -wheelAngle(live[0]);
  const minTurn = -wheelAngle(live[live.length - 1]);
  let turn = 0;
  const turnTo = (deg) => {
    turn = deg;
    rotor.style.setProperty('--turn', `${deg}deg`);
    wedgeEls.forEach((w, k) => {
      const off = Math.abs(wheelAngle(k) + deg) / WHEEL_STEP;
      w.style.opacity = w.classList.contains('empty') ? 0.3 : Math.max(0.45, 1 - off * 0.45).toFixed(2);
    });
  };
  const nearest = (deg) => live.reduce((best, k) =>
    (Math.abs(wheelAngle(k) + deg) < Math.abs(wheelAngle(best) + deg) ? k : best), live[0]);
  const spinTo = (id) => {
    const k = ZONES.findIndex((z) => z.id === id);
    turnTo(-wheelAngle(k));
    pick(id);
  };
  spinTo(selected);

  let drag = null;
  let dragged = false;
  wrap.addEventListener('pointerdown', (e) => {
    drag = { y: e.clientY, turn };
    dragged = false;
  });
  window.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dy = e.clientY - drag.y;
    if (Math.abs(dy) > 6) {
      dragged = true;
      rotor.classList.add('dragging');
    }
    if (dragged) turnTo(Math.min(Math.max(drag.turn + dy * 0.4, minTurn - 12), maxTurn + 12));
  });
  const release = () => {
    if (!drag) return;
    drag = null;
    rotor.classList.remove('dragging');
    if (dragged) spinTo(ZONES[nearest(turn)].id);
  };
  window.addEventListener('pointerup', release);
  window.addEventListener('pointercancel', release);

  // Tap a zone to spin it into the slot; tap the one in the slot to open it.
  wedgeEls.forEach((w) => {
    w.onclick = (e) => {
      if (dragged || w.classList.contains('empty')) {
        e.preventDefault();
        dragged = false;
        return;
      }
      if (w.dataset.zone !== selected) {
        e.preventDefault();
        spinTo(w.dataset.zone);
      }
    };
  });
  prefetch(index);
}

// ---- Zone list ----------------------------------------------------------------

async function renderZone(zoneId, fresh = false) {
  const zone = ZONES.find((z) => z.id === zoneId);
  if (!zone) {
    location.hash = '#/';
    return;
  }
  let core;
  try {
    core = await loadCore(fresh);
  } catch (err) {
    errorScreen(err);
    return;
  }
  const { index, spots, fromCache } = core;
  noteZone(zoneId);
  const byId = Object.fromEntries(index.spots.map((s) => [s.id, s]));
  const t = now();
  const regions = zoneRegions(zoneId, spots);
  const list = zoneSpots(zoneId, spots);
  const maxH = Math.max(3, ...list.flatMap((s) => byId[s.id]?.outlook?.wave_height || [0]));
  const cur = Object.fromEntries(list.map((s) => [s.id, nowFor(byId[s.id], t)]));
  const starred = list.filter((s) => isStarred(s.id));

  const sections = regions.map((r) => {
    const rows = list.filter((s) => s.region === r.id).map((s) => spotRow(s, cur[s.id], maxH)).join('');
    return `<section class="region" id="r-${esc(r.id)}">
      <h2>${esc(r.name)} <small>${esc(r.description || '')}</small></h2>
      <ul class="spot-list">${rows}</ul></section>`;
  }).join('');

  $app.innerHTML = `<main class="screen home">
    <header class="top"><a class="icon-btn" href="#/" aria-label="Back to regions">←</a><h1>${esc(zone.name)}</h1>
      <button class="icon-btn" id="refresh" aria-label="Refresh">⟳</button></header>
    ${freshness(index.generated_at, fromCache)}
    ${regions.length > 1 ? `<nav class="region-chips">${regions.map((r) =>
      `<a class="chip-link" href="#/" data-jump="r-${esc(r.id)}">${esc(r.name)}</a>`).join('')}</nav>` : ''}
    <p class="legend"><span class="chip off">offshore</span><span class="chip cross">cross</span>
      <span class="chip on">onshore</span> wind mph · bars: next 72 h</p>
    ${starred.length ? `<section class="region"><h2>★ Starred here</h2>
      <ul class="spot-list">${starred.map((s) => spotRow(s, cur[s.id], maxH)).join('')}</ul></section>` : ''}
    ${sections || '<p class="muted">No spots here yet.</p>'}
    <footer class="credits">Forecasts: Open-Meteo (CC BY 4.0). Tides: NOAA CO-OPS. Buoys: NOAA NDBC, Scripps CDIP.</footer>
  </main>`;

  document.getElementById('refresh').onclick = () => { clearMemo(); renderZone(zoneId, true); };
  $app.querySelectorAll('[data-jump]').forEach((a) => {
    a.onclick = (e) => {
      e.preventDefault();
      document.getElementById(a.dataset.jump)?.scrollIntoView({ behavior: 'smooth' });
    };
  });
  // Re-render so the "Starred here" section and the twin star buttons agree.
  bindStars($app, () => {
    keepScroll(zoneId);
    renderZone(zoneId).then(() => restoreScroll(zoneId));
  });
  $app.querySelectorAll('.spot-row').forEach((a) => { a.addEventListener('click', () => keepScroll(zoneId)); });
  prefetch(index);
}

// Coming back from a spot lands where the list was left.
function keepScroll(zoneId) {
  try { sessionStorage.setItem(`wf-scroll-${zoneId}`, String(window.scrollY)); } catch { /* none */ }
}

function restoreScroll(zoneId) {
  let y = 0;
  try { y = Number(sessionStorage.getItem(`wf-scroll-${zoneId}`)) || 0; } catch { /* none */ }
  window.scrollTo(0, y);
}

// Refresh starred spots and the last few opened while the connection is good,
// so they work offline at the beach.
function prefetch(index) {
  if (!goodConnection()) return;
  const byId = Object.fromEntries(index.spots.map((s) => [s.id, s]));
  const ids = [...new Set([...starredSpots(), ...recentSpots().slice(0, 3)])];
  for (const id of ids) {
    const s = byId[id];
    if (!s) continue;
    getJSON(s.forecast).catch(() => {});
    if (s.tide_station) getJSON(`tides/${s.tide_station}.json`).catch(() => {});
    if (s.active_buoy) getJSON(`buoys/${s.active_buoy}.json`).catch(() => {});
  }
}

// ---- Spot detail -----------------------------------------------------------

async function renderSpot(id) {
  let core;
  try {
    core = await loadCore(false);
  } catch (err) {
    errorScreen(err);
    return;
  }
  const spot = core.spots.spots.find((s) => s.id === id);
  const entry = core.index.spots.find((s) => s.id === id);
  if (!spot || !entry) {
    location.hash = '#/';
    return;
  }
  noteRecent(id);
  const back = `#/zone/${zoneOf(spot.region, core.spots)}`;
  $app.innerHTML = `<main class="screen spot"><header class="top">
    <a class="icon-btn" href="${back}" aria-label="Back">←</a><h1>${esc(spot.name)}</h1></header>
    <p class="updated">Loading forecast…</p></main>`;

  const opt = (p) => (p ? getJSON(p).then((r) => r.data).catch(() => null) : Promise.resolve(null));
  let fcRes;
  try {
    fcRes = await getJSON(entry.forecast);
  } catch (err) {
    errorScreen(err, `${spot.name} isn't saved for offline yet. Open it once with signal and it will be.`);
    return;
  }
  const [tide, buoy] = await Promise.all([
    opt(entry.tide_station && `tides/${entry.tide_station}.json`),
    opt(entry.active_buoy && `buoys/${entry.active_buoy}.json`),
  ]);
  if (location.hash !== `#/spot/${id}`) return; // user navigated away while loading
  new SpotView(spot, entry, fcRes.data, tide, buoy, core).mount(fcRes.fromCache || core.fromCache);
}

class SpotView {
  constructor(spot, entry, fc, tide, buoy, core) {
    Object.assign(this, { spot, entry, fc, tide, buoy, core });
    this.days = this.buildDays();
    this.i = -1;
  }

  // Local days from the forecast's sun list, with first/last light computed here.
  buildDays() {
    const { lat, lon } = this.spot;
    return (this.fc.sun || []).map((d) => ({ ...d, ...sunTimes(d.date, lat, lon), sunrise: d.sunrise, sunset: d.sunset }));
  }

  dayFor(t) {
    const key = localDayKey(t);
    return this.days.find((d) => localDayKey(d.date + 12 * 3600) === key) || null;
  }

  mount(fromCache) {
    const { spot, fc } = this;
    const zone = zoneOf(spot.region, this.core.spots);
    const order = zoneSpots(zone, this.core.spots);
    const k = order.findIndex((s) => s.id === spot.id);
    const prev = order[k - 1];
    const next = order[k + 1];
    this.neighbours = { prev, next };
    const t = now();
    const nights = [];
    for (let k = 0; k < this.days.length; k++) {
      const d = this.days[k];
      if (k === 0) nights.push([fc.time[0], d.firstLight]);
      const next = this.days[k + 1];
      nights.push([d.lastLight, next ? next.firstLight : fc.time[fc.time.length - 1] + 3600]);
    }
    const dayMarks = this.days.map((d) => ({ t: d.date, label: fmtDate(d.date + 43200) }));
    const max = Math.max(...fc.marine.wave_height.filter((v) => v != null), 4);
    const todayKey = localDayKey(t);

    $app.innerHTML = `<main class="screen spot">
      <header class="top"><a class="icon-btn" href="#/zone/${zone}" aria-label="Back">←</a>
        <h1>${esc(spot.name)}</h1>${starBtn(spot.id, spot.name)}</header>
      ${freshness(fc.marine_updated || this.core.index.generated_at, fromCache)}
      <details class="card notes" id="about"${aboutOpen() ? ' open' : ''}>
        <summary><h3>About this spot</h3></summary>
        <p>${esc(spot.notes || '')}</p>
        ${spot.skill === 'expert_only' || spot.bodyboard ? `<p class="tags">${
          spot.skill === 'expert_only' ? '<span class="tag">experts only</span>' : ''}${
          spot.bodyboard ? '<span class="tag bb">good for bodyboarding</span>' : ''}</p>` : ''}
        <dl class="facts">
          <div><dt>Faces</dt><dd>${compass(spot.facing_deg)} (${spot.facing_deg}°)</dd></div>
          <div><dt>Swell window</dt><dd>${compass(spot.swell_window.from)} to ${compass(spot.swell_window.to)}</dd></div>
          <div><dt>Break</dt><dd class="cap">${esc(spot.break_type || '–')}</dd></div>
          <div><dt>Best tide</dt><dd class="cap">${esc((spot.tide_preference || '–').replace(/_/g, ' '))}</dd></div>
        </dl>
      </details>
      <section class="hero" aria-live="polite">
        <div class="hero-num"><span id="hero-h">–</span><small>ft</small></div>
        <div class="hero-sub"><span id="hero-when"></span><span id="hero-wx"></span></div>
      </section>
      <section class="scrubber">
        <div class="day-chips" id="day-chips">${this.days.map((d, k) => {
          const key = localDayKey(d.date + 43200);
          return `<button class="day-chip" data-day="${k}">${key === todayKey ? 'Today' : fmtWeekday(d.date + 43200)}
            <small>${fmtDate(d.date + 43200).split(', ')[1] || ''}</small></button>`;
        }).join('')}</div>
        <div class="strip-wrap"><div class="strip-scroll" id="strip">
          ${scrubberStrip({ times: fc.time, heights: fc.marine.wave_height, relations: fc.derived.wind_relation,
            nights, days: dayMarks, barW: BAR_W, h: 110, max })}
        </div><div class="needle" aria-hidden="true"></div></div>
        <div class="step-row">
          <button class="btn" data-step="-3">−3 h</button>
          <button class="btn" data-step="-1">−1 h</button>
          <button class="btn primary" id="now-btn">Now</button>
          <button class="btn" data-step="1">+1 h</button>
          <button class="btn" data-step="3">+3 h</button>
        </div>
      </section>
      <section class="cards">
        <article class="card" id="c-swell"></article>
        <article class="card" id="c-wind"></article>
        <article class="card" id="c-tide"></article>
        <div class="card-pair">
          <article class="card small" id="c-water"></article>
          <article class="card small" id="c-air"></article>
        </div>
        <article class="card" id="c-sun"></article>
        <article class="card" id="c-buoy">${this.buoyCard()}</article>
      </section>
      ${prev || next ? `<nav class="neighbours">
        ${prev ? `<a class="btn" href="#/spot/${esc(prev.id)}">← ${esc(prev.name)}</a>` : '<span></span>'}
        ${next ? `<a class="btn" href="#/spot/${esc(next.id)}">${esc(next.name)} →</a>` : ''}
      </nav>` : ''}
    </main>`;

    bindStars($app);
    document.getElementById('about').addEventListener('toggle', (e) => noteAboutOpen(e.target.open));
    this.bindSwipe();
    this.strip = document.getElementById('strip');
    this.bindScrubber();
    this.select(hourIndex(fc.time, t), false);
  }

  bindScrubber() {
    const strip = this.strip;
    const pad = () => strip.clientWidth / 2 - BAR_W / 2;
    const svg = strip.querySelector('svg');
    const sync = () => {
      svg.style.marginLeft = `${pad()}px`;
      svg.style.marginRight = `${pad()}px`;
    };
    sync();
    window.addEventListener('resize', () => { sync(); this.scrollTo(this.i, false); });

    let raf = 0;
    strip.addEventListener('scroll', () => {
      if (this.programmatic) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const i = Math.round(strip.scrollLeft / BAR_W);
        this.select(Math.min(Math.max(i, 0), this.fc.time.length - 1), false, true);
      });
    }, { passive: true });
    strip.addEventListener('click', (e) => {
      const rect = svg.getBoundingClientRect();
      this.select(Math.floor((e.clientX - rect.left) / BAR_W), true);
    });

    document.querySelectorAll('[data-step]').forEach((b) => {
      b.onclick = () => this.select(this.i + Number(b.dataset.step), true);
    });
    document.getElementById('now-btn').onclick = () => this.select(hourIndex(this.fc.time, now()), true);
    document.querySelectorAll('[data-day]').forEach((b) => {
      b.onclick = () => {
        const d = this.days[Number(b.dataset.day)];
        // Jump to the hour containing first light: dawn patrol by default.
        this.select(hourIndex(this.fc.time, d.firstLight ?? d.date + 6 * 3600), true);
      };
    });
  }

  // Swipe sideways (outside the scrubber) for the next or previous spot in the
  // zone. Replaces the history entry so Back still returns to the list.
  bindSwipe() {
    const main = $app.querySelector('main');
    let start = null;
    main.addEventListener('touchstart', (e) => {
      start = e.target.closest('.scrubber') ? null
        : { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
    }, { passive: true });
    main.addEventListener('touchend', (e) => {
      if (!start) return;
      const dx = e.changedTouches[0].clientX - start.x;
      const dy = e.changedTouches[0].clientY - start.y;
      const quick = Date.now() - start.t < 600;
      start = null;
      if (!quick || Math.abs(dx) < 80 || Math.abs(dy) > Math.abs(dx) / 2) return;
      const to = dx < 0 ? this.neighbours.next : this.neighbours.prev;
      if (to) location.replace(`#/spot/${to.id}`);
    });
  }

  scrollTo(i, smooth) {
    this.programmatic = true;
    this.strip.scrollTo({ left: i * BAR_W, behavior: smooth ? 'smooth' : 'instant' });
    clearTimeout(this.progTimer);
    this.progTimer = setTimeout(() => { this.programmatic = false; }, smooth ? 600 : 50);
  }

  select(i, smooth, fromScroll = false) {
    i = Math.min(Math.max(i, 0), this.fc.time.length - 1);
    if (!fromScroll) this.scrollTo(i, smooth);
    if (i === this.i) return;
    this.i = i;
    this.update();
  }

  update() {
    const { fc, spot, i } = this;
    const t = fc.time[i];
    const m = fc.marine;
    const w = fc.weather;
    const day = this.dayFor(t);

    document.getElementById('hero-h').textContent = ft(m.wave_height[i]);
    const isNow = hourIndex(fc.time, now()) === i;
    document.getElementById('hero-when').textContent =
      `${isNow ? 'Now · ' : ''}${fmtDate(t)} ${fmtHour(t)}`;
    document.getElementById('hero-wx').textContent = weatherLabel(w.weather_code[i]);
    document.querySelectorAll('[data-day]').forEach((b) => {
      b.classList.toggle('active', day && this.days[Number(b.dataset.day)] === day);
    });

    // Swell trains
    const trains = swellTrains(fc, i, spot.swell_window);
    document.getElementById('c-swell').innerHTML = `<h3>Swell <small>wave height ${ft(m.wave_height[i])} ft
      · ${whole(m.wave_period[i])} s · ${compass(m.wave_direction[i])}</small></h3>
      ${trains.length ? `<ul class="trains">${trains.map((tr) => `<li class="${tr.inWindow === false ? 'blocked' : ''}">
        ${dirArrow(tr.dir, tr.kind)}
        <span class="tr-main"><b>${ft(tr.height)}</b> ft @ <b>${whole(tr.period)}</b> s</span>
        <span class="tr-dir">${compass(tr.dir)} ${tr.dir == null ? '' : `${Math.round(tr.dir)}°`}</span>
        <span class="tr-label">${tr.label}</span>
        ${tr.inWindow == null ? '<span class="flag none">local chop</span>'
          : tr.inWindow ? '<span class="flag in">in window</span>' : '<span class="flag out">blocked</span>'}
      </li>`).join('')}</ul>` : '<p class="muted">No swell data for this hour.</p>'}`;

    // Wind
    const rel = fc.derived.wind_relation[i];
    document.getElementById('c-wind').innerHTML = `<h3>Wind</h3>
      <div class="wind-row">${windDiagram(spot.facing_deg, w.wind_direction_10m[i], rel)}
        <div class="wind-text">
          <p class="rel ${relClass(rel)}">${esc(rel || 'unknown')}</p>
          <p class="big">${whole(w.wind_speed_10m[i])} <small>mph</small></p>
          <p class="muted">gusts ${whole(w.wind_gusts_10m[i])} mph<br>from ${compass(w.wind_direction_10m[i])}</p>
        </div></div>
      ${spot.big_wave && m.wave_height[i] >= spot.big_wave.min_ft ? `<div class="big-wave">
        <b>Big-wave note</b><p>${esc(spot.big_wave.note)}</p></div>` : ''}`;

    // Tide
    const tideEl = document.getElementById('c-tide');
    const td = this.tide && tideAt(this.tide, t);
    if (!td) {
      tideEl.innerHTML = '<h3>Tide</h3><p class="muted">No tide data for this hour.</p>';
    } else {
      const dayStart = day ? day.date : t - (t % 86400);
      const nx = td.next;
      tideEl.innerHTML = `<h3>Tide <small>${esc(this.tide.name || '')}</small></h3>
        <div class="tide-row"><p class="big">${ft(td.height)} <small>ft</small>
          <span class="tide-dir">${td.rising ? '↑ rising' : '↓ falling'}</span></p>
          ${nx ? `<p class="muted">${nx.type === 'H' ? 'High' : 'Low'} ${ft(nx.v)} ft at ${fmtTime(nx.t)}${
            localDayKey(nx.t) !== localDayKey(t) ? ` ${fmtWeekday(nx.t)}` : ''}</p>` : ''}</div>
        ${tideCurve(this.tide, dayStart, t)}`;
    }

    // Water and air
    document.getElementById('c-water').innerHTML = `<h3>Water</h3>
      <p class="big">${whole(m.sea_surface_temperature[i])}<small>°F</small></p>`;
    document.getElementById('c-air').innerHTML = `<h3>Air</h3>
      <p class="big">${whole(w.temperature_2m[i])}<small>°F</small></p>`;

    // Sun
    document.getElementById('c-sun').innerHTML = day ? `<h3>Sun <small>${fmtDate(day.date + 43200)}</small></h3>
      <dl class="sun">
        <div><dt>First light</dt><dd>${fmtTime(day.firstLight)}</dd></div>
        <div><dt>Sunrise</dt><dd>${fmtTime(day.sunrise)}</dd></div>
        <div><dt>Sunset</dt><dd>${fmtTime(day.sunset)}</dd></div>
        <div><dt>Last light</dt><dd>${fmtTime(day.lastLight)}</dd></div>
      </dl>` : '<h3>Sun</h3><p class="muted">No sun times for this day.</p>';
  }

  // Live buoy: latest reading vs. what the forecast said for that hour.
  buoyCard() {
    const { entry, buoy, spot, fc, core } = this;
    if (!entry.active_buoy || !buoy) {
      return `<h3>Live buoy</h3><p class="muted">No live buoy near this spot right now
        (nearest ${esc(spot.buoy.nearest)}, fallback ${esc(spot.buoy.fallback)} both quiet).</p>`;
    }
    const meta = core.spots.buoys[entry.active_buoy] || {};
    const cmp = buoyVsForecast(buoy, fc);
    const dist = meta.lat != null ? Math.round(distanceMi(spot.lat, spot.lon, meta.lat, meta.lon)) : null;
    const head = `<h3>Live buoy <small>${esc(buoy.name)} (${esc(buoy.id)})${
      entry.active_buoy_role === 'fallback' ? ' · fallback' : ''}</small></h3>`;
    if (!cmp) return `${head}<p class="muted">The buoy is reporting, but not wave height.</p>`;
    const { obs, forecast, delta, where } = cmp;
    const sp = buoy.latest_spectral;
    const verdict = delta == null ? ''
      : Math.abs(delta) < 0.5 ? 'Running about as forecast.'
        : delta > 0 ? `Running ${ft(delta)} ft bigger than forecast.`
          : `Running ${ft(-delta)} ft smaller than forecast.`;
    return `${head}
      <p class="muted">Reading ${fmtAge(now() - obs.time)} (${fmtTime(obs.time)})${dist != null ? ` · ${dist} mi from the spot` : ''}</p>
      <table class="vs">
        <thead><tr><th></th><th>Buoy now</th><th>Forecast ${where === 'buoy' ? 'at buoy' : 'at spot'}</th></tr></thead>
        <tbody>
          <tr><th>Wave height</th><td><b>${ft(obs.wave_height_ft)}</b> ft</td><td>${forecast ? `${ft(forecast.height)} ft` : '–'}</td></tr>
          <tr><th>Period</th><td>${whole(obs.dominant_period_s)} s <small>dominant</small></td><td>${forecast ? `${whole(forecast.period)} s <small>${forecast.periodKind}</small>` : '–'}</td></tr>
          <tr><th>Direction</th><td>${compass(obs.mean_wave_dir_deg)}</td><td>${forecast ? compass(forecast.dir) : '–'}</td></tr>
          <tr><th>Water</th><td>${whole(obs.water_temp_f)}°F</td><td>${forecast ? `${whole(forecast.water)}°F` : '–'}</td></tr>
        </tbody>
      </table>
      ${verdict ? `<p class="verdict ${delta > 0.4 ? 'up' : delta < -0.4 ? 'down' : ''}">${verdict}</p>` : ''}
      ${sp && sp.swell_height_ft != null ? `<p class="muted">Swell part: ${ft(sp.swell_height_ft)} ft @ ${whole(sp.swell_period_s)} s from ${compass(sp.swell_dir_deg)};
        wind waves ${ft(sp.wind_wave_height_ft)} ft.</p>` : ''}
      <p class="fine">${where === 'buoy'
        ? 'Forecast for the buoy\'s own position, so this shows how the model is doing today. Waves at the spot can differ, especially where it is sheltered.'
        : 'Forecast for the spot; the buoy sits offshore, so expect some difference even on a good day.'}</p>`;
  }
}

// ---- Router ---------------------------------------------------------------

function route() {
  const spot = location.hash.match(/^#\/spot\/([\w-]+)/);
  const zone = location.hash.match(/^#\/zone\/([\w-]+)/);
  window.scrollTo(0, 0);
  if (spot) renderSpot(spot[1]);
  else if (zone) renderZone(zone[1]).then(() => restoreScroll(zone[1]));
  else renderOpener();
}

window.addEventListener('hashchange', route);
route();

// ---- Service worker ---------------------------------------------------------

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.register('sw.js').catch(() => {});
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController) return; // first install: nothing to reload
    const bar = document.createElement('button');
    bar.className = 'update-toast';
    bar.textContent = 'App updated. Tap to reload.';
    bar.onclick = () => location.reload();
    document.body.append(bar);
  });
}
