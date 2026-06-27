/**
 * RAPID — Frontend Configuration
 *
 * This file is loaded before any page script.
 * To point the frontend at a different backend, set:
 *
 *   window.RAPID_API_URL = "https://api.yourdomain.com"
 *
 * in your deployment's index.html <head>, OR inject it via nginx
 * sub_filter, OR override it here for a self-hosted build.
 *
 * Priority: window.RAPID_API_URL > meta[name=rapid-api] > default
 */
(function () {
  // 1. Explicit override on window (set by deployment wrapper / nginx)
  if (window.RAPID_API_URL) return;

  // 2. <meta name="rapid-api" content="https://..."> in the page <head>
  const meta = document.querySelector('meta[name="rapid-api"]');
  if (meta && meta.content) {
    window.RAPID_API_URL = meta.content.replace(/\/$/, '');
    return;
  }

  // 3. Same-origin API on /api (used when nginx proxies /api → backend)
  //    If the page is served from https://app.example.com the API is
  //    reachable at https://app.example.com/api — no CORS needed.
  const loc = window.location;
  if (loc.hostname !== 'localhost' && loc.hostname !== '127.0.0.1') {
    window.RAPID_API_URL = loc.origin + '/api';
    return;
  }

  // 4. Local development fallback
  window.RAPID_API_URL = 'http://localhost:8000';
})();
