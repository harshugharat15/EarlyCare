// Early Care Service Worker
const CACHE_NAME = 'earlycare-v1';

self.addEventListener('install', function(e) {
  console.log('Early Care Service Worker installed');
});

self.addEventListener('fetch', function(e) {
  e.respondWith(fetch(e.request));
});
