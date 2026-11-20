// Wang — Service Worker (sw.js)
// Specialized PWA caching for instant mobile startup & offline resilience

const STATIC_CACHE = 'wang-static-v12';
const FONT_CACHE = 'wang-fonts-v2';
const PAGE_CACHE = 'wang-pages-v3';

const CORE_ASSETS = [
  '/offline/',
  '/static/css/wang.css',
  '/static/css/wang.css?v=24',
  '/static/js/app.js',
  '/static/js/app.js?v=24',
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

// Helper: Normalize navigation URL for fallback cache lookup (strips widget/shortcut action params)
function getCleanRootOrPathRequest(urlObj) {
  const cleanUrl = new URL(urlObj.href);
  cleanUrl.searchParams.delete('action');
  return cleanUrl.toString();
}

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
        const cachedResponse = (await cache.match(request)) || (await caches.match(request, { ignoreSearch: true }));
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

  // 2. Static Assets (CSS, JS, Images, CDNs) — Stale-While-Revalidate with ignoreSearch fallback
  const isStatic =
    url.pathname.startsWith('/static/') ||
    url.origin === 'https://cdn.jsdelivr.net';

  if (isStatic) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {
        const cachedResponse =
          (await cache.match(request)) ||
          (await cache.match(request, { ignoreSearch: true }));
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

  // 3. API JSON GET requests (e.g., /api/wallets/) — Network-First with Cache Fallback
  if (url.pathname.startsWith('/api/')) {
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
          const cachedApi = await caches.match(request);
          if (cachedApi) return cachedApi;
          return new Response(JSON.stringify({ offline: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          });
        })
    );
    return;
  }

  // 4. HTML Navigation / Page requests — Network-First with Full-Shell Page Cache & Offline Fallback
  const isHtml =
    request.mode === 'navigate' ||
    (request.headers.get('accept') && request.headers.get('accept').includes('text/html'));
  const isTurboFrame = Boolean(request.headers.get('Turbo-Frame'));

  if (isHtml) {
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const respUrl = networkResponse.url || '';
            const isRedirectToLogin = respUrl.includes('/login') && !url.pathname.includes('/login');
            if (!isRedirectToLogin) {
              const clone = networkResponse.clone();
              caches.open(PAGE_CACHE).then((cache) => {
                if (!isTurboFrame) {
                  // Full document navigation (contains full #wang-svg-sprite-holder and #sheet-root-container)
                  cache.put(request, clone.clone());
                  const cleanKey = getCleanRootOrPathRequest(url);
                  if (cleanKey !== request.url) {
                    cache.put(cleanKey, clone);
                  }
                } else {
                  // Store Turbo sub-frame under a distinct cache key so it never overwrites full HTML shells
                  const frameId = request.headers.get('Turbo-Frame') || 'frame';
                  const frameKey = request.url + (request.url.includes('?') ? '&' : '?') + '__turbo_frame=' + encodeURIComponent(frameId);
                  cache.put(frameKey, clone);
                }
              });
            }
          }
          return networkResponse;
        })
        .catch(async () => {
          // Network failed (offline / no cellular internet)
          const pageCache = await caches.open(PAGE_CACHE);

          // 1st: If Turbo sub-frame request, check sub-frame cache first
          if (isTurboFrame) {
            const frameId = request.headers.get('Turbo-Frame') || 'frame';
            const frameKey = request.url + (request.url.includes('?') ? '&' : '?') + '__turbo_frame=' + encodeURIComponent(frameId);
            const cachedFrame = await pageCache.match(frameKey);
            if (cachedFrame) return cachedFrame;
          }

          // 2nd: Try exact cached page in PAGE_CACHE
          const cachedPage = await pageCache.match(request);
          if (cachedPage) {
            return cachedPage;
          }

          // 3rd: Try normalized path without ?action=new_expense / ?action=new_income query params
          const cleanKey = getCleanRootOrPathRequest(url);
          const cachedClean = await pageCache.match(cleanKey);
          if (cachedClean) {
            return cachedClean;
          }

          // 4th: Try pathname without query string (e.g. / or /wallets/)
          const pathnameOnly = url.origin + url.pathname;
          const cachedPathname = await pageCache.match(pathnameOnly);
          if (cachedPathname) {
            return cachedPathname;
          }

          // 5th: Fallback to cached root dashboard '/' in PAGE_CACHE (has the full app shell & add-transaction bottom sheet!)
          const cachedRoot = await pageCache.match(url.origin + '/');
          if (cachedRoot) {
            return cachedRoot;
          }

          // 6th: Fallback to cute offline page (from PAGE_CACHE or STATIC_CACHE)
          const offlinePage = (await pageCache.match('/offline/')) || (await caches.match('/offline/'));
          if (offlinePage) {
            return offlinePage;
          }

          // 7th: Basic fallback HTML
          return new Response(
            `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Wang — Offline</title><style>body{font-family:sans-serif;text-align:center;padding:40px;background:#FFF7F3;color:#2D2926;}</style></head><body><h2>You are currently offline</h2><p>Please check your connection and tap retry.</p><button onclick="location.reload()" style="padding:10px 20px;border-radius:12px;background:#FF9E80;color:#fff;border:none;cursor:pointer;font-weight:bold;">Retry</button></body></html>`,
            { headers: { 'Content-Type': 'text/html' } }
          );
        })
    );
    return;
  }

  // 5. Default: Try network, fallback to cache
  event.respondWith(
    fetch(request).catch(() => caches.match(request, { ignoreSearch: true }))
  );
});
