// ⚽ 축구 보드판 Service Worker
const CACHE_NAME = 'soccer-board-v3.3.2';
const ASSETS = [
  './index.html',
  './soccer_board_v3.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js',
];

// 설치: 모든 파일 캐시
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(ASSETS).catch(err => {
        console.warn('일부 캐시 실패 (무시):', err);
      });
    })
  );
  self.skipWaiting();
});

// 활성화: 이전 버전 캐시 자동 삭제 후 즉시 제어권 획득
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// 요청 가로채기: Network First 전략
// - 온라인: 항상 네트워크에서 최신 파일 가져온 후 캐시 갱신
// - 오프라인: 캐시에서 가져옴
self.addEventListener('fetch', event => {
  // GET 요청만 처리
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request)
      .then(networkRes => {
        // 유효한 응답이면 캐시에 저장
        if (networkRes && networkRes.status === 200 && networkRes.type !== 'opaque') {
          const resClone = networkRes.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, resClone));
        }
        return networkRes;
      })
      .catch(() => {
        // 오프라인: 캐시에서 반환
        return caches.match(event.request).then(cached => {
          return cached || new Response('오프라인 상태입니다.', {
            status: 503,
            headers: { 'Content-Type': 'text/plain; charset=utf-8' }
          });
        });
      })
  );
});
