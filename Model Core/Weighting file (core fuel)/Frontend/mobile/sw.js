"use strict";

// 墨灵移动端离线缓存（仅 HTTPS 下生效；HTTP 局域网自动跳过）。
const CACHE = "moling-mobile-v1";
const ASSETS = ["index.html", "style.css", "app.js", "manifest.json", "icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/v1/mobile/")) {
    event.respondWith(
      caches.match(event.request).then(
        (hit) => hit || fetch(event.request).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          return res;
        }),
      ),
    );
  }
  // API 请求不缓存，直接透传。
});
