/* eslint-disable */
/**
 * Service Worker — veille-uptade
 *
 * Stratégies de cache par type de requête :
 *   1. Assets immuables Next.js (/_next/static/*)   → cache-first (déjà long-cachés via headers)
 *   2. Pages HTML (mode: 'navigate')                → stale-while-revalidate (instantané, refresh en BG)
 *   3. API (/api/*) GET                              → network-first avec timeout 3s, fallback cache
 *   4. Reste same-origin (manifest, icons, fonts)    → stale-while-revalidate
 *   5. Cross-origin (Mapbox CDN, etc.)               → passthrough (on n'intercepte pas)
 *   6. Non-GET                                       → passthrough (ne JAMAIS cacher POST/PUT/DELETE)
 *
 * App shell : routes navigables principales pré-cachées au 1er install.
 * Navigation après 1ère visite = instantanée (offline-friendly).
 *
 * Caches versionnés : VERSION change → activate purge les anciens automatiquement.
 */

const VERSION = 'v3-2026-05-28'
const STATIC_CACHE = `veille-static-${VERSION}`
const PAGE_CACHE = `veille-pages-${VERSION}`
const RUNTIME_CACHE = `veille-runtime-${VERSION}`

// App shell : routes navigables principales pré-cachées au 1er install.
// Couvre les destinations probables depuis la sidebar/dashboard.
const APP_SHELL = [
  '/',
  '/dashboard',
  '/carte',
  '/briefing',
  '/affairs',
  '/articles',
  '/manifest.json',
  '/icons/icon-192.svg',
  '/icons/icon-512.svg',
]

// Bornes mémoire pour éviter une explosion silencieuse du cache.
const RUNTIME_CACHE_MAX = 80
const PAGE_CACHE_MAX = 30

// ───────────────────────────── Helpers ─────────────────────────────

async function trimCache(cacheName, maxEntries) {
  const cache = await caches.open(cacheName)
  const keys = await cache.keys()
  if (keys.length <= maxEntries) return
  // Supprime les plus vieux (FIFO).
  await Promise.all(keys.slice(0, keys.length - maxEntries).map((k) => cache.delete(k)))
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request)
  const fetchPromise = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        cache.put(request, response.clone())
      }
      return response
    })
    .catch(() => cached)
  return cached || fetchPromise
}

async function networkFirst(request, cacheName, timeoutMs = 3000) {
  const cache = await caches.open(cacheName)
  try {
    const networkPromise = fetch(request)
    const timeoutPromise = new Promise((_, rej) =>
      setTimeout(() => rej(new Error('sw:timeout')), timeoutMs),
    )
    const response = await Promise.race([networkPromise, timeoutPromise])
    if (response && response.ok) {
      cache.put(request, response.clone())
    }
    return response
  } catch (_e) {
    const cached = await cache.match(request)
    if (cached) return cached
    throw _e
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response && response.ok) {
    cache.put(request, response.clone())
  }
  return response
}

// ───────────────────────────── Install ─────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(STATIC_CACHE)
      // Pas un seul gros .addAll qui échoue à cause d'1 URL : on tolère les fautifs.
      await Promise.allSettled(APP_SHELL.map((url) => cache.add(url).catch(() => null)))
    })(),
  )
  self.skipWaiting()
})

// ───────────────────────────── Activate ────────────────────────────

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(
        keys
          .filter((k) => ![STATIC_CACHE, PAGE_CACHE, RUNTIME_CACHE].includes(k))
          .map((k) => caches.delete(k)),
      )
      await self.clients.claim()
    })(),
  )
})

// ───────────────────────────── Fetch ───────────────────────────────

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return

  let url
  try {
    url = new URL(req.url)
  } catch {
    return
  }
  const sameOrigin = url.origin === self.location.origin

  // 1. Assets immuables Next.js — cache-first, jamais re-fetché.
  if (sameOrigin && url.pathname.startsWith('/_next/static/')) {
    event.respondWith(cacheFirst(req, STATIC_CACHE))
    return
  }

  // 2. Navigation HTML (clic sur Link, F5, etc.) — stale-while-revalidate.
  if (req.mode === 'navigate' && sameOrigin) {
    event.respondWith(
      (async () => {
        const resp = await staleWhileRevalidate(req, PAGE_CACHE)
        // best-effort trim (ne pas bloquer la réponse)
        trimCache(PAGE_CACHE, PAGE_CACHE_MAX).catch(() => null)
        return resp
      })(),
    )
    return
  }

  // 3. API GET — network-first avec timeout 3s, fallback cache.
  if (sameOrigin && url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(req, RUNTIME_CACHE))
    return
  }

  // 4. Tout le reste same-origin (icones, manifest, fonts) — SWR.
  if (sameOrigin) {
    event.respondWith(
      (async () => {
        const resp = await staleWhileRevalidate(req, RUNTIME_CACHE)
        trimCache(RUNTIME_CACHE, RUNTIME_CACHE_MAX).catch(() => null)
        return resp
      })(),
    )
    return
  }

  // 5. Cross-origin (Mapbox CDN, etc.) — passthrough, on n'intercepte pas.
})

// ───────────────────────────── Push (préservé) ─────────────────────

self.addEventListener('push', (event) => {
  if (!event.data) return

  let data
  try {
    data = event.data.json()
  } catch (e) {
    data = { title: 'Veille Média 971', body: event.data.text() }
  }

  const options = {
    body: data.body || '',
    icon: data.icon || '/icons/icon-192.svg',
    badge: data.badge || '/icons/icon-192.svg',
    tag: data.tag || 'veille-default',
    vibrate: [200, 100, 200],
    data: { url: data.url || '/' },
    actions: [{ action: 'open', title: 'Voir' }],
  }

  event.waitUntil(self.registration.showNotification(data.title || '🔔 Veille Média', options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const url = event.notification.data?.url || '/'

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Si l'app est déjà ouverte, focus dessus
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.focus()
        }
      }
      // Sinon, ouvrir une nouvelle fenêtre
      return self.clients.openWindow(url)
    }),
  )
})
