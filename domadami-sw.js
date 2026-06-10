// DOMADAMI Service Worker — cache app shell pentru offline
const CACHE = 'domadami-v1';
const CACHED = [
  './domadami.html',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CACHED).catch(() => {})));
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
  // Skip Supabase API requests (vor merge la network sau eseuc -> handled in app)
  if (req.url.includes('supabase.co')) return;
  // Cache-first pentru static
  e.respondWith(
    caches.match(req).then(cached => cached || fetch(req).then(resp => {
      // Cache only same-origin + chart.js
      if (resp.ok && (req.url.includes('domadami.html') || req.url.includes('chart.js'))) {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(req, clone));
      }
      return resp;
    }).catch(() => cached))
  );
});
