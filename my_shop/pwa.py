import json

import frappe
from werkzeug.wrappers import Response

from frappe.website.page_renderers.base_renderer import BaseRenderer

CACHE_VERSION = "my-shop-v2"

SERVICE_WORKER = """
const CACHE = "%(cache)s";
const SHELL = ["/voice", "/khata", "/shop-settings", "/assets/my_shop/css/shop.css", "/assets/my_shop/icons/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL).catch(() => {})));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

const OFFLINE_PAGE = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline</title><body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#f5f6fa;color:#0f172a;font:18px system-ui;text-align:center">
<div><h1 style="margin:8px 0">You are offline</h1><p>Check your connection and try again.</p>
<button onclick="location.reload()" style="font:700 18px system-ui;padding:14px 24px;border:0;border-radius:16px;background:#4f46e5;color:#fff">Retry</button></div>`;

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.origin === location.origin && url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok && !response.redirected) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request).then((hit) => hit || new Response(OFFLINE_PAGE, { headers: { "Content-Type": "text/html; charset=utf-8" } })))
    );
    return;
  }

  const cacheable = url.pathname.startsWith("/assets/") || url.hostname.endsWith("fonts.googleapis.com") || url.hostname.endsWith("fonts.gstatic.com");
  if (!cacheable) return;
  event.respondWith(
    caches.match(request).then((hit) => {
      const network = fetch(request).then((response) => {
        if (response.ok || response.type === "opaque") {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
      return hit || network;
    })
  );
});
"""


def manifest() -> dict:
	settings = frappe.get_cached_doc("Shop Voice Settings")
	name = settings.shop_name or "My Shop"
	icons = "/assets/my_shop/icons"
	return {
		"name": f"{name} · Voice Billing",
		"short_name": name,
		"description": "Speak an order, get a bill",
		"id": "/voice",
		"start_url": "/voice",
		"scope": "/",
		"display": "standalone",
		"orientation": "portrait",
		"background_color": "#f5f6fa",
		"theme_color": "#4f46e5",
		"lang": "en",
		"icons": [
			{"src": f"{icons}/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
			{"src": f"{icons}/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
			{"src": f"{icons}/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
		],
		"shortcuts": [
			{"name": "New bill", "url": "/voice", "icons": [{"src": f"{icons}/icon-192.png", "sizes": "192x192"}]},
			{"name": "Ledger", "url": "/khata", "icons": [{"src": f"{icons}/icon-192.png", "sizes": "192x192"}]},
		],
	}


class PWARenderer(BaseRenderer):
	ROUTES = {"sw.js", "manifest.webmanifest"}

	def can_render(self):
		return self.path in self.ROUTES

	def render(self):
		if self.path == "sw.js":
			response = Response(SERVICE_WORKER % {"cache": CACHE_VERSION}, mimetype="application/javascript")
			response.headers["Cache-Control"] = "no-cache"
			response.headers["Service-Worker-Allowed"] = "/"
		else:
			response = Response(json.dumps(manifest(), ensure_ascii=False), mimetype="application/manifest+json")
			response.headers["Cache-Control"] = "no-cache"
		return response
