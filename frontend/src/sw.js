const CACHE_NAME = 'cognitive-garden-v2';

// 安装时读取 manifest 获取精确资源列表
const MANIFEST_URL = './assets/manifest.json';

async function getPrecacheUrls() {
  const urls = ['/', './index.html', './loading.html', './manifest.json'];
  try {
    const res = await fetch(MANIFEST_URL, { cache: 'no-store' });
    if (!res.ok) return urls;
    const manifest = await res.json();
    // Vite manifest format: { "index.html": { "file": "index-xxx.js", ... } }
    Object.values(manifest).forEach((entry) => {
      if (typeof entry === 'object' && entry.file) {
        urls.push(`./assets/${entry.file}`);
      }
      if (entry.css) {
        entry.css.forEach((css) => urls.push(`./assets/${css}`));
      }
      if (entry.imports) {
        entry.imports.forEach((imp) => {
          const impEntry = manifest[imp];
          if (impEntry && impEntry.file) {
            urls.push(`./assets/${impEntry.file}`);
          }
        });
      }
    });
  } catch (e) {
    console.warn('[SW] Failed to read manifest:', e);
  }
  return urls;
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    getPrecacheUrls().then((urls) => {
      return caches.open(CACHE_NAME).then((cache) => {
        return cache.addAll(urls);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // API requests: network first, then cache
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/') || url.pathname.startsWith('/session/') || url.pathname.startsWith('/graph/') || url.pathname.startsWith('/baseline/') || url.pathname.startsWith('/stt/') || url.pathname.startsWith('/state/') || url.pathname.startsWith('/backup/') || url.pathname.startsWith('/scale/') || url.pathname.startsWith('/lexicon/') || url.pathname.startsWith('/decline/') || url.pathname.startsWith('/notification/')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(JSON.stringify({ offline: true }), {
          headers: { 'Content-Type': 'application/json' },
        });
      })
    );
    return;
  }

  // Static assets: stale-while-revalidate strategy (default)
  event.respondWith(
    caches.match(event.request).then((cached) => {
      // Chart modules: stale-while-revalidate
      if (url.pathname.includes('chart') || url.pathname.includes('radar') || url.pathname.includes('heatmap') || url.pathname.includes('trend')) {
        const fetchPromise = fetch(event.request).then((fetchResponse) => {
          if (fetchResponse.status === 200) {
            const clone = fetchResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return fetchResponse;
        }).catch(() => cached);
        return cached || fetchPromise;
      }
      // Mode modules: cache-first
      if (url.pathname.includes('mode') || url.pathname.includes('modes')) {
        if (cached) return cached;
        return fetch(event.request).then((fetchResponse) => {
          if (fetchResponse.status === 200) {
            const clone = fetchResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return fetchResponse;
        }).catch(() => cached);
      }
      const fetchPromise = fetch(event.request).then((fetchResponse) => {
        if (fetchResponse.status === 200) {
          const clone = fetchResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return fetchResponse;
      }).catch(() => cached);

      return cached || fetchPromise;
    }).catch(() => {
      // Fallback for HTML
      if (event.request.headers.get('accept') && event.request.headers.get('accept').includes('text/html')) {
        return caches.match('./index.html');
      }
      return new Response('Offline', { status: 503 });
    })
  );
});
