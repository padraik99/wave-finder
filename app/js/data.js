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

// Remember the last few spots opened, so they can be refreshed in the
// background while signal is good (home Wi-Fi before the drive).
const RECENT_KEY = 'wf-recent';

export function recentSpots() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY)) || [];
  } catch {
    return [];
  }
}

export function noteRecent(id) {
  try {
    const list = [id, ...recentSpots().filter((x) => x !== id)].slice(0, 5);
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch {
    // Storage unavailable (private mode): nothing to remember.
  }
}

export function goodConnection() {
  const c = navigator.connection;
  if (!navigator.onLine) return false;
  if (!c) return true;
  return !c.saveData && !['slow-2g', '2g', '3g'].includes(c.effectiveType);
}
