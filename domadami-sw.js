// DOMADAMI Service Worker — network-first pentru HTML (auto-update), cache-first pt static
const CACHE = 'domadami-v2';
const CACHED_STATIC = [
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CACHED_STATIC).catch(() => {})));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const req = e.request;
  // Skip Supabase API requests (vor merge la network sau esec -> handled in app)
  if (req.url.includes('supabase.co')) return;

  // NETWORK-FIRST pentru domadami.html (mereu ia versiunea proaspata cand e online)
  // Fallback la cache DOAR daca reteaua a picat (offline).
  if (req.url.includes('domadami.html') || req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then(resp => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE).then(c => c.put(req, clone));
          }
          return resp;
        })
        .catch(() => caches.match(req).then(cached => cached || caches.match('./domadami.html')))
    );
    return;
  }

  // CACHE-FIRST pentru static (chart.js, iconite etc.) — se schimba rar
  e.respondWith(
    caches.match(req).then(cached => cached || fetch(req).then(resp => {
      if (resp.ok && req.url.includes('chart.js')) {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(req, clone));
      }
      return resp;
    }).catch(() => cached))
  );
});
