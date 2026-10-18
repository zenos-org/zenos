// ZENOS Messages service worker: offline shell + Web Push.
// The page itself is fetched fresh first (falls back to cache offline), so a phone always gets the latest screen.
// Static parts (icons, avatars, call code) are served from cache at once and refreshed in the background.
// Messages, keys and attachments (/api/*) are never cached.
const CACHE = "zenos-msg-v12";
const SHELL = ["/", "/app-icon.svg", "/app-icon-180.png", "/app-icon-512.png", "/manifest.webmanifest", "/zcall.js", "/lk/livekit-client.umd.js", "/lk/livekit-client.e2ee.worker.js"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => {})))));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
const isStatic = (p) => p.startsWith("/av/") || p.startsWith("/lk/") || p.startsWith("/pdf/") || p === "/zcall.js" || p.startsWith("/app-icon") || p === "/manifest.webmanifest";
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/") || url.pathname === "/link") return;
  if (isStatic(url.pathname)) {
    e.respondWith(caches.open(CACHE).then(async (c) => {
      const hit = await c.match(e.request);
      const net = fetch(e.request).then((r) => { if (r.ok) c.put(e.request, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok && url.pathname === "/") { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, cp)); }
    return r;
  }).catch(() => caches.match(e.request)));
});
self.addEventListener("push", (e) => {
  let d = { title: "ZENOS", body: "New message" };
  try { d = e.data.json(); } catch (_) {}
  e.waitUntil(self.registration.showNotification(d.title || "ZENOS", {
    body: d.body || "", icon: "/app-icon.svg", badge: "/app-icon.svg",
    tag: d.tag || "zenos", renotify: true, requireInteraction: d.red === true, data: { url: d.url || "/" },
  }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => {
    for (const c of cs) if ("focus" in c) return c.focus();
    return self.clients.openWindow(url);
  }));
});
