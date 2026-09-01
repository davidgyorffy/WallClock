const CACHE_NAME = "wallclock-v62";
const APP_FILES = ["./index.html?v=62", "./manifest.json?v=62"];

self.addEventListener("install", function(event) {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return Promise.all(
        APP_FILES.map(function(url) {
          return fetch(url, { cache: "reload" })
            .then(function(response) {
              if (response && response.ok) return cache.put(url, response.clone());
            })
            .catch(function(){});
        })
      );
    })
  );
});

self.addEventListener("activate", function(event) {
  event.waitUntil(
    caches.keys()
      .then(function(keys) {
        return Promise.all(
          keys.filter(function(k){ return k !== CACHE_NAME; })
              .map(function(k){ return caches.delete(k); })
        );
      })
      .then(function() { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function(event) {
  if (event.request.method !== "GET") return;

  var url = new URL(event.request.url);

  /* Never intercept API/weather requests. */
  if (url.origin !== self.location.origin) return;

  /* HTML/navigation must always try the actual server first. */
  if (event.request.mode === "navigate" ||
      event.request.destination === "document" ||
      url.pathname.endsWith("/index.html")) {
    event.respondWith(
      fetch(event.request, { cache: "no-store" })
        .then(function(response) {
          if (response && response.ok) {
            var copy = response.clone();
            caches.open(CACHE_NAME).then(function(cache) {
              cache.put("./index.html?v=62", copy).catch(function(){});
            });
          }
          return response;
        })
        .catch(function() {
          return caches.match("./index.html?v=62");
        })
    );
    return;
  }

  /* Other same-origin files: network first, cache fallback. */
  event.respondWith(
    fetch(event.request, { cache: "no-store" })
      .then(function(response) {
        if (response && response.ok) {
          var copy = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(event.request, copy).catch(function(){});
          });
        }
        return response;
      })
      .catch(function() {
        return caches.match(event.request);
      })
  );
});
