// Wave Finder app: two screens, hash-routed.
//   #/            region list (every spot, now + 72 h outlook)
//   #/spot/<id>   spot detail with the hour scrubber and live buoy panel

import { clearMemo, getJSON, goodConnection, noteRecent, recentSpots } from './data.js';
import {
  RELATION, buoyVsForecast, compass, distanceMi, fmtAge, fmtDate, fmtHour, fmtTime, fmtWeekday,
  ft, hourIndex, localDayKey, swellTrains, tideAt, weatherLabel, whole,
} from './model.js';
import { sunTimes } from './sun.js';
import { dirArrow, relClass, scrubberStrip, sparkline, tideCurve, windDiagram } from './svg.js';

const $app = document.getElementById('app');
const BAR_W = 12;
const STALE_AFTER_S = 4.5 * 3600; // fetch runs every 3 h; allow one late run

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

// ---- Region list -----------------------------------------------------------

async function renderHome(fresh = false) {
  let core;
  try {
    core = await loadCore(fresh);
  } catch (err) {
    errorScreen(err);
    return;
  }
  const { index, spots, fromCache } = core;
  const byId = Object.fromEntries(index.spots.map((s) => [s.id, s]));
  const t = now();
  const maxH = Math.max(3, ...index.spots.flatMap((s) => s.outlook?.wave_height || [0]));

  const regions = spots.regions.map((r) => {
    const rows = spots.spots.filter((s) => s.region === r.id).map((s) => {
      const o = byId[s.id]?.outlook;
      const i = o ? Math.floor((t - o.start) / 3600) : -1;
      const ok = o && i >= 0 && i < o.wave_height.length;
      const h = ok ? o.wave_height[i] : null;
      const rel = ok ? RELATION[o.wind[i]] : null;
      const wind = ok ? o.wind_speed[i] : null;
      const rest = ok ? o.wave_height.slice(i) : [];
      const restWind = ok ? o.wind.slice(i) : '';
      return `<li><a class="spot-row" href="#/spot/${esc(s.id)}">
        <span class="spot-name">${esc(s.name)}${s.skill === 'expert_only' ? ' <span class="tag">experts</span>' : ''}</span>
        <span class="spot-now"><b>${ft(h)}</b><small>ft</small></span>
        <span class="chip ${relClass(rel)}">${rel ? `${esc(rel)} ${whole(wind)}` : 'no data'}</span>
        ${sparkline(rest, restWind, maxH)}
      </a></li>`;
    }).join('');
    return `<section class="region" id="r-${esc(r.id)}">
      <h2>${esc(r.name)} <small>${esc(r.description || '')}</small></h2>
      <ul class="spot-list">${rows}</ul></section>`;
  }).join('');

  $app.innerHTML = `<main class="screen home">
    <header class="top"><h1>Wave Finder</h1>
      <button class="icon-btn" id="refresh" aria-label="Refresh">⟳</button></header>
    ${freshness(index.generated_at, fromCache)}
    <nav class="region-chips">${spots.regions.map((r) =>
      `<a class="chip-link" href="#/" data-jump="r-${esc(r.id)}">${esc(r.name)}</a>`).join('')}</nav>
    <p class="legend"><span class="chip off">offshore</span><span class="chip cross">cross</span>
      <span class="chip on">onshore</span> wind mph · bars: next 72 h</p>
    ${regions}
    <footer class="credits">Forecasts: Open-Meteo (CC BY 4.0). Tides: NOAA CO-OPS. Buoys: NOAA NDBC, Scripps CDIP.</footer>
  </main>`;

  document.getElementById('refresh').onclick = () => { clearMemo(); renderHome(true); };
  $app.querySelectorAll('[data-jump]').forEach((a) => {
    a.onclick = (e) => {
      e.preventDefault();
      document.getElementById(a.dataset.jump)?.scrollIntoView({ behavior: 'smooth' });
    };
  });
  prefetchRecent(index);
}

// Refresh the last few opened spots while the connection is good, so they work
// offline at the beach.
function prefetchRecent(index) {
  if (!goodConnection()) return;
  const byId = Object.fromEntries(index.spots.map((s) => [s.id, s]));
  for (const id of recentSpots().slice(0, 3)) {
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
  $app.innerHTML = `<main class="screen spot"><header class="top">
    <a class="icon-btn" href="#/" aria-label="Back">←</a><h1>${esc(spot.name)}</h1></header>
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
      <header class="top"><a class="icon-btn" href="#/" aria-label="Back">←</a>
        <h1>${esc(spot.name)}</h1></header>
      ${freshness(fc.marine_updated || this.core.index.generated_at, fromCache)}
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
        <article class="card notes">
          <h3>About this spot</h3>
          <p>${esc(spot.notes || '')}</p>
          <dl class="facts">
            <div><dt>Faces</dt><dd>${compass(spot.facing_deg)} (${spot.facing_deg}°)</dd></div>
            <div><dt>Swell window</dt><dd>${compass(spot.swell_window.from)} to ${compass(spot.swell_window.to)}</dd></div>
            <div><dt>Break</dt><dd class="cap">${esc(spot.break_type || '–')}</dd></div>
            <div><dt>Best tide</dt><dd class="cap">${esc(spot.tide_preference || '–')}</dd></div>
          </dl>
        </article>
      </section>
    </main>`;

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
        </div></div>`;

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
  const m = location.hash.match(/^#\/spot\/([\w-]+)/);
  window.scrollTo(0, 0);
  if (m) renderSpot(m[1]); else renderHome();
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
