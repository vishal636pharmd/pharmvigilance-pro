// PVPro Service Worker — handles real push notifications

const CACHE_NAME = "pvpro-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

// ── This is what fires when server sends a push notification ──────────────
// This runs even when the browser is CLOSED — exactly like WhatsApp
self.addEventListener("push", function(event) {
    let data = {};
    try {
        data = event.data.json();
    } catch(e) {
        data = {
            title: "PVPro",
            body: event.data ? event.data.text() : "New update",
            url: "/"
        };
    }

    const options = {
        body:    data.body    || "Tap to open PVPro",
        icon:    data.icon    || "/static/icon-192.png",
        badge:   data.badge   || "/static/icon-192.png",
        vibrate: [200, 100, 200],   // vibration pattern like WhatsApp
        data:    { url: data.url || "/" },
        actions: [
            { action: "open",    title: "Open PVPro" },
            { action: "dismiss", title: "Dismiss" }
        ],
        requireInteraction: true   // stays visible until tapped (like WhatsApp)
    };

    event.waitUntil(
        self.registration.showNotification(data.title || "PVPro", options)
    );
});

// ── When user taps the notification ──────────────────────────────────────
self.addEventListener("notificationclick", function(event) {
    event.notification.close();

    if (event.action === "dismiss") return;

    const url = new URL(event.notification.data.url || "/", self.location.origin).href;

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true })
               .then(function(clientList) {
                   // If PVPro is already open, focus it and navigate
                   for (let client of clientList) {
                       if ("focus" in client) {
                           client.focus();
                           client.navigate(url);
                           return;
                       }
                   }
                   // Otherwise open a new window
                   if (clients.openWindow) {
                       return clients.openWindow(url);
                   }
               })
    );
});

// Basic fetch handler (offline fallback)
self.addEventListener("fetch", e => {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
