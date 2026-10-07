// Pure data helpers: no DOM, no fetch. Unit-tested in tests/js/.

export const TZ = 'America/Los_Angeles';
const HOUR = 3600;

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];

export function compass(deg) {
  if (deg == null) return '–';
  return COMPASS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
}

// Same rule as pipeline/geo.py in_window: clockwise from `from` to `to`, inclusive.
export function inWindow(dir, from, to) {
  if (dir == null) return null;
  const d = ((dir % 360) + 360) % 360;
  const a = ((from % 360) + 360) % 360;
  const b = ((to % 360) + 360) % 360;
  return a <= b ? d >= a && d <= b : d >= a || d <= b;
}

// Index of the hour containing `t` in an ascending hourly `times` array,
// clamped to the array. Returns -1 for an empty array.
export function hourIndex(times, t) {
  if (!times || !times.length) return -1;
  if (t < times[0]) return 0;
  let lo = 0;
  let hi = times.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (times[mid] <= t) lo = mid; else hi = mid - 1;
  }
  return lo;
}

// Index of the entry whose time is closest to `t`, or -1 if none within maxGap seconds.
export function nearestIndex(times, t, maxGap = HOUR) {
  const i = hourIndex(times, t);
  if (i < 0) return -1;
  let best = i;
  if (i + 1 < times.length && Math.abs(times[i + 1] - t) < Math.abs(times[i] - t)) best = i + 1;
  return Math.abs(times[best] - t) <= maxGap ? best : -1;
}

const TRAINS = [
  ['Primary swell', 'swell_wave'],
  ['Secondary swell', 'secondary_swell_wave'],
  ['Tertiary swell', 'tertiary_swell_wave'],
  ['Wind waves', 'wind_wave'],
];

// Swell trains present at hour i, biggest first, each flagged in/out of the spot's window.
// Wind waves are local chop, so they get no window flag.
export function swellTrains(fc, i, window) {
  const m = fc.marine;
  const out = [];
  for (const [label, key] of TRAINS) {
    const height = m[`${key}_height`]?.[i];
    if (height == null || height < 0.1) continue;
    const dir = m[`${key}_direction`]?.[i] ?? null;
    out.push({
      label,
      kind: key === 'wind_wave' ? 'wind' : 'swell',
      height,
      period: m[`${key}_period`]?.[i] ?? null,
      dir,
      inWindow: key === 'wind_wave' ? null : inWindow(dir, window.from, window.to),
    });
  }
  return out.sort((a, b) => (a.kind === b.kind ? b.height - a.height : a.kind === 'wind' ? 1 : -1));
}

// Tide at time t: interpolated height, rising flag, and the next high/low.
export function tideAt(tide, t) {
  if (!tide?.hourly?.time?.length) return null;
  const { time, height, rising } = tide.hourly;
  const i = hourIndex(time, t);
  if (t < time[0] || t > time[time.length - 1] + HOUR) return null;
  let h = height[i];
  if (i + 1 < time.length && height[i] != null && height[i + 1] != null) {
    const f = (t - time[i]) / (time[i + 1] - time[i]);
    h = height[i] + (height[i + 1] - height[i]) * Math.min(Math.max(f, 0), 1);
  }
  const next = (tide.extremes || []).find((x) => x.t > t) || null;
  const prev = [...(tide.extremes || [])].reverse().find((x) => x.t <= t) || null;
  // Between two extremes the direction is unambiguous; prefer that to the hourly flag.
  const isRising = next ? next.type === 'H' : rising[i];
  return { height: h == null ? null : Math.round(h * 10) / 10, rising: isRising, next, prev };
}

// Live buoy reading against what the forecast said for the same hour.
export function buoyVsForecast(buoy, fc) {
  const obs = buoy?.latest;
  if (!obs || obs.wave_height_ft == null) return null;
  const i = nearestIndex(fc.time, obs.time, 90 * 60);
  if (i < 0) return { obs, forecast: null, delta: null };
  const m = fc.marine;
  const forecast = {
    time: fc.time[i],
    height: m.wave_height[i],
    period: m.wave_period[i],
    dir: m.wave_direction[i],
    water: m.sea_surface_temperature[i],
  };
  const delta = forecast.height == null ? null
    : Math.round((obs.wave_height_ft - forecast.height) * 10) / 10;
  return { obs, forecast, delta };
}

export function distanceMi(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * r / 2) ** 2
    + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin((lon2 - lon1) * r / 2) ** 2;
  return 3958.8 * 2 * Math.asin(Math.sqrt(a));
}

// WMO weather codes, collapsed to what matters at the beach.
export function weatherLabel(code) {
  if (code == null) return '';
  if (code === 0) return 'Clear';
  if (code <= 2) return 'Partly cloudy';
  if (code === 3) return 'Overcast';
  if (code === 45 || code === 48) return 'Fog';
  if (code >= 51 && code <= 57) return 'Drizzle';
  if (code >= 61 && code <= 67) return 'Rain';
  if (code >= 71 && code <= 77) return 'Snow';
  if (code >= 80 && code <= 82) return 'Showers';
  if (code >= 95) return 'Thunderstorm';
  return '';
}

export const RELATION = { o: 'offshore', c: 'cross', n: 'onshore' };

// ---- Formatting (California time regardless of the phone's zone) ----------

const fmtCache = {};
function fmt(opts) {
  const key = JSON.stringify(opts);
  fmtCache[key] ||= new Intl.DateTimeFormat('en-US', { timeZone: TZ, ...opts });
  return fmtCache[key];
}

export const fmtTime = (u) => (u == null ? '–' : fmt({ hour: 'numeric', minute: '2-digit' }).format(u * 1000));
export const fmtHour = (u) => fmt({ hour: 'numeric' }).format(u * 1000);
export const fmtWeekday = (u) => fmt({ weekday: 'short' }).format(u * 1000);
export const fmtDate = (u) => fmt({ weekday: 'short', month: 'short', day: 'numeric' }).format(u * 1000);

export function localDayKey(u) {
  return fmt({ year: 'numeric', month: '2-digit', day: '2-digit' }).format(u * 1000);
}

export function fmtAge(seconds) {
  if (seconds < 90) return 'just now';
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 6) / 10;
  if (h < 48) return `${h % 1 ? h.toFixed(1) : h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

export const ft = (v) => (v == null ? '–' : v.toFixed(1));
export const whole = (v) => (v == null ? '–' : String(Math.round(v)));
