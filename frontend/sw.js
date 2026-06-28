/* ── Service Worker: Homelab Dashboard ─────────────────────────
   Cache-first for static assets (JS, CSS, HTML, fonts, images).
   Network-first for API calls (always tries network, falls back to cache).
*/

const CACHE_VERSION = 'v1';
const STATIC_CACHE = `homelab-static-${CACHE_VERSION}`;
const API_CACHE = `homelab-api-${CACHE_VERSION}`;

const STATIC_PRECACHE = [
  '/',
  '/index.html',
  '/css/dashboard.css',
  '/css/theme-light.css',
  '/js/utils.js',
  '/js/charts.js',
  '/js/app.js',
  '/js/theme.js',
  '/js/pwa.js',
  '/js/device_labels.js',
  '/js/docker_status.js',
  '/js/proxmox.js',
  '/js/uptime_kuma.js',
  '/manifest.json',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== API_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

function isApiRequest(url) {
  return url.pathname.startsWith('/api/');
}

function isStaticAsset(url) {
  return (
    /\.(js|css|html|png|svg|ico|json|woff2?|ttf|eot)$/i.test(url.pathname) ||
    url.pathname === '/' ||
    url.origin !== self.location.origin
  );
}

// Cache-first for static assets.
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) {
    // Refresh in background.
    fetch(request).then((resp) => { if (resp && resp.ok) cache.put(request, resp.clone()); }).catch(() => {});
    return cached;
  }
  try {
    const resp = await fetch(request);
    if (resp && resp.ok) cache.put(request, resp.clone());
    return resp;
  } catch (e) {
    return new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}

// Network-first for API calls.
async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const resp = await fetch(request);
    if (resp && resp.ok) cache.put(request, resp.clone());
    return resp;
  } catch (e) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: 'Offline', offline: true }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (_) { return; }

  if (isApiRequest(url)) {
    event.respondWith(networkFirst(req, API_CACHE));
  } else if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(req, STATIC_CACHE));
  }
});