self.addEventListener('install', (e) => {
  console.log('[Service Worker] Install');
});

self.addEventListener('fetch', (e) => {
  // Minimal fetch listener to satisfy PWA requirements
  e.respondWith(
    fetch(e.request).catch(() => {
      return new Response('Network error occurred');
    })
  );
});
