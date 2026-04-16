// ── SERVICE WORKER — Scanner Produse ARAFURA ──────────────────────
// Versiune cache — schimba acest string la fiecare deploy pentru a forta update
const CACHE_VERSION = 'arafura-scanner-v33';
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  'https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js',
];
// config.js NU se cacheaza — se incarca mereu fresh din retea

// ── INSTALL: cacheeaza toate resursele ────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then(cache => cache.addAll(ASSETS))
      .then(() => self.skipWaiting())  // activeaza imediat, nu asteapta reload
  );
});

// ── ACTIVATE: sterge cache-urile vechi ────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_VERSION)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())  // preia controlul imediat
  );
});

// ── FETCH: network-first pentru index.html, cache-first pentru rest ─
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Pentru Supabase — mereu network (nu cacheeaza date live)
  if (url.hostname.includes('supabase.co')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Pentru config.js — mereu network (credentiale, nu se cacheaza)
  if (url.pathname.endsWith('config.js')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Pentru index.html — network-first (sa primeasca update-urile)
  if (url.pathname.endsWith('index.html') || url.pathname.endsWith('/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          // Salveaza versiunea noua in cache
          const clone = response.clone();
          caches.open(CACHE_VERSION).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))  // offline: serveste din cache
    );
    return;
  }

  // Pentru restul (JS, CSS, etc.) — cache-first
  event.respondWith(
    caches.match(event.request)
      .then(cached => cached || fetch(event.request))
  );
});

// ── MESSAGE: primeste comanda de update de la pagina ─────────────
self.addEventListener('message', event => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});
