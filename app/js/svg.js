// SVG builders. Each returns a markup string; colours come from CSS variables
// so dark and light themes both work.

const REL_CLASS = { offshore: 'off', cross: 'cross', onshore: 'on', o: 'off', c: 'cross', n: 'on' };
export const relClass = (r) => REL_CLASS[r] || 'none';

// Wind against the beach. North is up; the beach line runs across the spot's
// facing direction with sea on the facing side. The arrow points the way the
// wind is blowing (from `windFrom` toward the opposite side).
export function windDiagram(facing, windFrom, relation) {
  const arrow = windFrom == null ? '' : `
    <g transform="rotate(${windFrom})" class="wind-arrow ${relClass(relation)}">
      <line x1="0" y1="-58" x2="0" y2="36" />
      <polygon points="0,58 -13,32 13,32" />
    </g>`;
  return `<svg class="wind-diagram" viewBox="-80 -80 160 160" role="img"
    aria-label="Wind ${relation || 'unknown'} against the beach">
    <defs><clipPath id="wd-clip"><circle r="78" /></clipPath></defs>
    <g clip-path="url(#wd-clip)">
      <g transform="rotate(${facing})">
        <rect class="sea" x="-120" y="-120" width="240" height="120" />
        <rect class="land" x="-120" y="0" width="240" height="120" />
        <path class="shore" d="M-120 0 Q-90 -7 -60 0 T0 0 T60 0 T120 0" />
        <text class="sea-label" x="0" y="-62" text-anchor="middle">SEA</text>
      </g>
    </g>
    <circle class="ring" r="78" />
    <text class="north" x="0" y="-66" text-anchor="middle" dy="0.35em">N</text>
    ${arrow}
  </svg>`;
}

// Small arrow showing the way a swell or wind travels (from `dir` to the opposite side).
export function dirArrow(dir, cls = '') {
  if (dir == null) return '';
  return `<svg class="dir-arrow ${cls}" viewBox="-10 -10 20 20" aria-hidden="true">
    <g transform="rotate(${dir})"><path d="M0 -8 L0 8 M-5 3 L0 8 L5 3" /></g></svg>`;
}

// 72 h outlook bars for the spot list, coloured by wind.
export function sparkline(heights, wind, max) {
  const n = heights.length;
  if (!n) return '';
  const w = 2;
  const h = 28;
  const scale = h / Math.max(max, 3);
  const bars = heights.map((v, i) => {
    const bh = Math.max(1, (v || 0) * scale);
    return `<rect class="bar ${relClass(wind[i])}" x="${i * w}" y="${(h - bh).toFixed(1)}"
      width="${w - 0.5}" height="${bh.toFixed(1)}" />`;
  }).join('');
  return `<svg class="spark" viewBox="0 0 ${n * w} ${h}" preserveAspectRatio="none" aria-hidden="true">${bars}</svg>`;
}

// The hour scrubber strip: one bar per hour (height = wave height, colour =
// wind), night shaded, day boundaries labelled.
export function scrubberStrip({ times, heights, relations, nights, days, barW, h, max }) {
  const top = 22;
  const plot = h - top;
  const scale = plot / Math.max(max, 4);
  const t0 = times[0];
  const x = (t) => ((t - t0) / 3600) * barW;
  const shade = nights.map(([a, b]) =>
    `<rect class="night" x="${x(a).toFixed(1)}" y="${top}" width="${(x(b) - x(a)).toFixed(1)}" height="${plot}" />`).join('');
  const bars = heights.map((v, i) => {
    const bh = Math.max(2, (v || 0) * scale);
    return `<rect class="bar ${relClass(relations[i])}" x="${i * barW + 1}" y="${(h - bh).toFixed(1)}"
      width="${barW - 2}" height="${bh.toFixed(1)}" rx="1" />`;
  }).join('');
  const labels = days.map(({ t, label }) =>
    `<line class="day-line" x1="${x(t)}" x2="${x(t)}" y1="0" y2="${h}" />
     <text class="day-label" x="${x(t) + 4}" y="14">${label}</text>`).join('');
  return `<svg class="strip" width="${times.length * barW}" height="${h}" aria-hidden="true">
    ${shade}${labels}${bars}</svg>`;
}

// One day's tide curve with a marker at time t.
export function tideCurve(tide, dayStart, t) {
  const { time, height } = tide.hourly;
  const pts = [];
  for (let i = 0; i < time.length; i++) {
    if (time[i] >= dayStart && time[i] <= dayStart + 86400 && height[i] != null) pts.push([time[i], height[i]]);
  }
  if (pts.length < 2) return '';
  const W = 300;
  const H = 70;
  const lo = Math.min(-1, ...pts.map((p) => p[1]));
  const hi = Math.max(6, ...pts.map((p) => p[1]));
  const px = (u) => ((u - dayStart) / 86400) * W;
  const py = (v) => 6 + (1 - (v - lo) / (hi - lo)) * (H - 12);
  const d = pts.map(([u, v], i) => `${i ? 'L' : 'M'}${px(u).toFixed(1)} ${py(v).toFixed(1)}`).join(' ');
  const area = `${d} L${px(pts[pts.length - 1][0]).toFixed(1)} ${H} L${px(pts[0][0]).toFixed(1)} ${H} Z`;
  // Height at t by linear interpolation along the day's points.
  let marker = '';
  for (let i = 0; i + 1 < pts.length; i++) {
    if (t >= pts[i][0] && t <= pts[i + 1][0]) {
      const f = (t - pts[i][0]) / (pts[i + 1][0] - pts[i][0]);
      const v = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f;
      marker = `<line class="now-line" x1="${px(t)}" x2="${px(t)}" y1="0" y2="${H}" />
        <circle class="now-dot" cx="${px(t).toFixed(1)}" cy="${py(v).toFixed(1)}" r="5" />`;
      break;
    }
  }
  const zero = lo < 0 ? `<line class="zero" x1="0" x2="${W}" y1="${py(0)}" y2="${py(0)}" />` : '';
  return `<svg class="tide-curve" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <path class="area" d="${area}" /><path class="line" d="${d}" />${zero}${marker}</svg>`;
}
