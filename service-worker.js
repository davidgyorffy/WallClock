const CACHE_NAME = "wallclock-v87";
const INDEX_CACHE_KEY = "./index.html?v=87";
const APP_FILES = [INDEX_CACHE_KEY, "./manifest.json?v=87"];

self.addEventListener("install", function(event) {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return Promise.all(APP_FILES.map(function(url) {
        return fetch(url, { cache: "no-store" })
          .then(function(response) {
            if (response && response.ok) return cache.put(url, response.clone());
          })
          .catch(function(){});
      }));
    })
  );
});

self.addEventListener("activate", function(event) {
  event.waitUntil(
    caches.keys()
      .then(function(keys) {
        return Promise.all(keys.filter(function(k){ return k !== CACHE_NAME; })
          .map(function(k){ return caches.delete(k); }));
      })
      .then(function(){ return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function(event) {
  if (event.request.method !== "GET") return;

  var url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  /* gamma.json must never come from an old cache. */
  if (url.pathname.endsWith("/gamma.json")) {
    event.respondWith(fetch(event.request, { cache: "no-store" }));
    return;
  }

  /* Navigations and index.html are always network-first. */
  if (event.request.mode === "navigate" ||
      event.request.destination === "document" ||
      url.pathname.endsWith("/index.html")) {
    event.respondWith(
      fetch(event.request, { cache: "no-store" })
        .then(function(response) {
          if (response && response.ok) {
            caches.open(CACHE_NAME).then(function(cache) {
              cache.put(INDEX_CACHE_KEY, response.clone()).catch(function(){});
            });
          }
          return response;
        })
        .catch(function(){ return caches.match(INDEX_CACHE_KEY); })
    );
    return;
  }

  event.respondWith(
    fetch(event.request, { cache: "no-store" })
      .then(function(response) {
        if (response && response.ok) {
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(event.request, response.clone()).catch(function(){});
          });
        }
        return response;
      })
      .catch(function(){ return caches.match(event.request); })
  );
});
