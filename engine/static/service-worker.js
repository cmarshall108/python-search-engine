const CACHE_NAME = 'smartsearch-cache-v1';

// Assets to cache for offline use
const ASSETS_TO_CACHE = [
  '/static/css/enhanced-style.css',
  '/static/js/enhanced-search.js',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css',
  'https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@300;400;500&display=swap'
];

// Install service worker and cache assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Service worker: Caching assets');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => self.skipWaiting())
  );
});

// Clean up old caches on activation
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME)
          .map(name => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Network first, fallback to cache strategy
self.addEventListener('fetch', event => {
  // Only handle GET requests
  if (event.request.method !== 'GET') return;
  
  // Skip API calls and WebSocket connections
  if (event.request.url.includes('/api/') || 
      event.request.url.includes('/ws/')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Clone the response to store in cache
        const responseClone = response.clone();
        
        caches.open(CACHE_NAME).then(cache => {
          // Only cache successful responses
          if (response.status === 200) {
            cache.put(event.request, responseClone);
          }
        });
        
        return response;
      })
      .catch(() => {
        // If network fails, try to get from cache
        return caches.match(event.request)
          .then(cachedResponse => {
            if (cachedResponse) {
              return cachedResponse;
            }
            
            // For HTML navigation requests, return the offline page
            if (event.request.headers.get('Accept').includes('text/html')) {
              return caches.match('/offline.html')
                .then(offlineResponse => {
                  return offlineResponse || new Response(
                    'You are offline. Please try again when you have an internet connection.',
                    { 
                      headers: { 'Content-Type': 'text/html' },
                      status: 503
                    }
                  );
                });
            }
            
            // Return empty response if nothing found
            return new Response('Not found', { status: 404 });
          });
      })
  );
});
