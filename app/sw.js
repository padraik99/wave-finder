// Service worker: the app shell is cached on install (works fully offline);
// data is network-first with a timeout, falling back to the last copy.
// __BUILD__ is replaced with the commit id at deploy, so each app release
// installs a fresh shell cache.

const VERSION = '__BUILD__';
const SHELL_CACHE = `wf-shell-${VERSION}`;
const DATA_CACHE = 'wf-data';
const NETWORK_TIMEOUT_MS = 8000;

const SHELL = [
  './',
  'index.html',
  'manifest.webmanifest',
  'css/app.css',
  'js/app.js',
  'js/data.js',
  'js/model.js',
  'js/sun.js',
  'js/svg.js',
  'icons/icon.svg',
  'icons/icon-192.png',
  'icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await cache.addAll(SHELL.map((u) => new Request(u, { cache: 'reload' })));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter((k) => k.startsWith('wf-shell-') && k !== SHELL_CACHE)
      .map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const scope = new URL(self.registration.scope);
  const path = url.pathname.slice(scope.pathname.length);

  if (path.startsWith('data/')) {
    event.respondWith(dataFirst(event, req));
  } else if (req.mode === 'navigate') {
    event.respondWith(shellFirst('index.html', req));
  } else {
    event.respondWith(shellFirst(req, req));
  }
});

async function shellFirst(key, req) {
  const cached = await caches.match(key, { ignoreSearch: true });
  return cached || fetch(req);
}

// Network first; if it fails or takes longer than the timeout, answer from the
// cache and let the network request keep going to refresh the cache.
async function dataFirst(event, req) {
  const cache = await caches.open(DATA_CACHE);
  const network = fetch(req).then(async (res) => {
    if (res.ok) await cache.put(req.url, res.clone());
    return res;
  });
  event.waitUntil(network.catch(() => {}));

  const timeout = new Promise((resolve) => setTimeout(resolve, NETWORK_TIMEOUT_MS, 'timeout'));
  try {
    const winner = await Promise.race([network, timeout]);
    if (winner !== 'timeout' && winner.ok) return winner;
  } catch {
    // Offline: fall through to the cache.
  }
  const cached = await cache.match(req.url);
  if (cached) {
    const headers = new Headers(cached.headers);
    headers.set('x-wf-cache', 'fallback');
    return new Response(cached.body, { status: 200, headers });
  }
  return network; // no cached copy: wait for the network after all (or fail)
}
