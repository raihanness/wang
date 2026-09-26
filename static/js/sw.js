// Wang — Service Worker (sw.js)
// Specialized PWA caching for instant mobile startup & offline resilience

const STATIC_CACHE = 'wang-static-v10';
const FONT_CACHE = 'wang-fonts-v2';
const PAGE_CACHE = 'wang-pages-v1';

const CORE_ASSETS = [
  '/offline/',
  '/static/css/wang.css',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/img/icons.svg',
  '/static/img/logo-fix.png',
  '/static/img/favicon.png',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/img/apple-touch-icon.png',
  '/static/fonts/plus-jakarta-sans-latin.woff2',
  '/static/fonts/plus-jakarta-sans-latin-ext.woff2',
  '/static/fonts/plus-jakarta-sans-vietnamese.woff2',
  '/static/fonts/plus-jakarta-sans-cyrillic-ext.woff2',
  '/static/fonts/herr-von-muellerhoff-latin.woff2',
  '/static/fonts/herr-von-muellerhoff-latin-ext.woff2',
  'https://cdn.jsdelivr.net/npm/@hotwired/turbo@8.0.4/dist/turbo.es2017-umd.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'
];

// Install: Pre-cache core app shell & assets with fault-tolerance
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      // Fetch each asset individually so one failure does not abort the install
      return Promise.allSettled(
        CORE_ASSETS.map((url) =>
          cache.add(url).catch((err) => {
            console.warn('[SW] Pre-cache skipped for:', url, err);
          })
        )
      );
    }).then(() => self.skipWaiting())
  );
});

// Activate: Clean up outdated caches & claim clients immediately
self.addEventListener('activate', (event) => {
  const currentCaches = [STATIC_CACHE, FONT_CACHE, PAGE_CACHE];
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => !currentCaches.includes(key))
          .map((key) => {
            console.log('[SW] Removing old cache:', key);
            return caches.delete(key);
          })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Apply optimal caching strategy per request type
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Only handle GET requests; pass POST/PUT/DELETE straight through
  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);

  // 1. Self-Hosted Fonts & Legacy Google Fonts (Cache-First)
  // Font files are immutable; load directly from cache
  const isFont =
    url.pathname.startsWith('/static/fonts/') ||
    url.origin === 'https://fonts.gstatic.com' ||
    url.origin === 'https://fonts.googleapis.com';

  if (isFont) {
    event.respondWith(
      caches.open(FONT_CACHE).then(async (cache) => {
        const cachedResponse = await cache.match(request);
        if (cachedResponse) {
          return cachedResponse;
        }
        try {
          const networkResponse = await fetch(request);
          if (networkResponse && networkResponse.status === 200) {
            cache.put(request, networkResponse.clone());
          }
          return networkResponse;
        } catch (err) {
          // If offline and not in cache, nothing more we can do for fonts
          return cachedResponse || Response.error();
        }
      })
    );
    return;
  }

  // 2. Static Assets (CSS, JS, Images, CDNs) — Stale-While-Revalidate
  const isStatic =
    url.pathname.startsWith('/static/') ||
    url.origin === 'https://cdn.jsdelivr.net';

  if (isStatic) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {
        const cachedResponse = await cache.match(request);
        const fetchPromise = fetch(request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              cache.put(request, networkResponse.clone());
            }
            return networkResponse;
          })
          .catch(() => cachedResponse);

        return cachedResponse || fetchPromise;
      })
    );
    return;
  }

  // 3. HTML Navigation / Page requests — Network-First with Page Cache & Offline Fallback
  const isHtml =
    request.mode === 'navigate' ||
    (request.headers.get('accept') && request.headers.get('accept').includes('text/html'));

  if (isHtml) {
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(PAGE_CACHE).then((cache) => {
              cache.put(request, clone);
            });
          }
          return networkResponse;
        })
        .catch(async () => {
          // Network failed (offline / spotty connection)
          // 1st: Try cached version of this exact page
          const cachedPage = await caches.match(request);
          if (cachedPage) {
            return cachedPage;
          }
          // 2nd: Fallback to cute offline page
          const offlinePage = await caches.match('/offline/');
          if (offlinePage) {
            return offlinePage;
          }
          // 3rd: Basic fallback HTML if offline page was somehow evicted
          return new Response(
            `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Wang — Offline</title><style>body{font-family:sans-serif;text-align:center;padding:40px;background:#FFF7F3;color:#2D2926;}</style></head><body><h2>You are currently offline</h2><p>Please check your connection and tap retry.</p><button onclick="location.reload()" style="padding:10px 20px;border-radius:12px;background:#FF9E80;color:#fff;border:none;cursor:pointer;font-weight:bold;">Retry</button></body></html>`,
            { headers: { 'Content-Type': 'text/html' } }
          );
        })
    );
    return;
  }

  // 4. Default: Try network, fallback to cache
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});
