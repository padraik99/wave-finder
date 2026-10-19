// Fetch layer. Data is served from ./data/ (the `data` branch, deployed to
// Pages alongside the app). The service worker answers from its cache when the
// network is down or too slow, and marks such responses so the UI can say so.

const BASE = './data/';
const memo = new Map();

export async function getJSON(path, { fresh = false } = {}) {
  if (!fresh && memo.has(path)) return memo.get(path);
  const p = (async () => {
    // no-cache: revalidate with the server (a cheap 304 when nothing changed)
    // rather than trusting the browser's 10-minute Pages cache.
    const res = await fetch(BASE + path, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    const data = await res.json();
    return { data, fromCache: res.headers.get('x-wf-cache') === 'fallback' };
  })();
  memo.set(path, p);
  p.catch(() => memo.delete(path));
  return p;
}

export function clearMemo() {
  memo.clear();
}

// Small per-phone preferences in localStorage. Storage can be unavailable
// (private mode); then nothing is remembered and the app still works.
function load(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Nothing to remember with.
  }
}

// Remember the last few spots opened, so they can be refreshed in the
// background while signal is good (home Wi-Fi before the drive).
export function recentSpots() {
  return load('wf-recent', []);
}

export function noteRecent(id) {
  save('wf-recent', [id, ...recentSpots().filter((x) => x !== id)].slice(0, 5));
}

export function starredSpots() {
  return load('wf-stars', []);
}

export function isStarred(id) {
  return starredSpots().includes(id);
}

// Returns the new state.
export function toggleStar(id) {
  const list = starredSpots();
  const on = !list.includes(id);
  save('wf-stars', on ? [...list, id] : list.filter((x) => x !== id));
  return on;
}

export const lastZone = () => load('wf-zone', null);
export const noteZone = (id) => save('wf-zone', id);
export const aboutOpen = () => load('wf-about-open', true);
export const noteAboutOpen = (open) => save('wf-about-open', open);

export function goodConnection() {
  const c = navigator.connection;
  if (!navigator.onLine) return false;
  if (!c) return true;
  return !c.saveData && !['slow-2g', '2g', '3g'].includes(c.effectiveType);
}
