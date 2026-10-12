/* FinQuery Google sign-in for display personalization only.
 * This does not grant access or authorize financial data/API requests.
 * Tokens are deliberately NOT stored. Server-side ID-token verification
 * must be added before this identity is used for permissions.
 */
(function () {
  'use strict';

  var clientMeta = document.querySelector('meta[name="finquery-google-client-id"]');
  var clientId = clientMeta && (clientMeta.getAttribute('content') || '').trim();
  var root = document.getElementById('finquery-google-account');
  // Do not load third-party Google scripts or show an inert login button
  // until the site owner supplies a Google OAuth Web Client ID.
  if (!root || !/^[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com$/i.test(clientId || '')) return;

  var signin = document.getElementById('finquery-google-signin');
  var identity = document.getElementById('finquery-google-identity');
  var greeting = document.getElementById('finquery-google-greeting');
  var signout = document.getElementById('finquery-google-signout');
  var status = document.getElementById('finquery-google-status');
  if (!signin || !identity || !greeting || !signout) return;

  var STORAGE_KEY = 'finquery_google_profile_v1';
  var activeProfile = null;

  function daypart(hour) {
    if (hour >= 5 && hour < 11) return 'Xin chào buổi sáng';
    if (hour >= 11 && hour < 14) return 'Xin chào buổi trưa';
    if (hour >= 14 && hour < 18) return 'Xin chào buổi chiều';
    return 'Xin chào buổi tối';
  }

  function notify(message) {
    if (status) status.textContent = message || '';
  }

  function showSignedOut() {
    activeProfile = null;
    identity.hidden = true;
    signin.hidden = false;
    notify('Bạn chưa đăng nhập Google.');
  }

  function showSignedIn(profile) {
    if (!profile || !profile.name || !Number.isFinite(profile.expiresAt) || profile.expiresAt <= Date.now()) {
      showSignedOut();
      return;
    }
    activeProfile = profile;
    greeting.textContent = daypart(new Date().getHours()) + ', ' + profile.name + '!';
    identity.hidden = false;
    signin.hidden = true;
    notify('Đã kết nối với tài khoản Google để hiển thị lời chào.');
  }

  function readCachedProfile() {
    try {
      var profile = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (profile && typeof profile.name === 'string' && profile.name.length <= 80 &&
          Number.isFinite(profile.expiresAt) && profile.expiresAt > Date.now()) return profile;
      localStorage.removeItem(STORAGE_KEY);
    } catch (_) { /* Storage may be disabled. */ }
    return null;
  }

  function decodeCredential(jwt) {
    // JWT is parsed ONLY for the non-security-sensitive display name.
    // The Google GIS callback provides the ID token; no local permission is granted.
    if (typeof jwt !== 'string') return null;
    var parts = jwt.split('.');
    if (parts.length !== 3) return null;
    try {
      var base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      var raw = atob(base64 + '='.repeat((4 - base64.length % 4) % 4));
      var claims = JSON.parse(new TextDecoder().decode(Uint8Array.from(raw, function (character) {
        return character.charCodeAt(0);
      })));
      if (!Number.isFinite(Number(claims.exp)) || claims.aud !== clientId ||
          !['accounts.google.com', 'https://accounts.google.com'].includes(claims.iss) ||
          !claims.sub || Number(claims.exp) <= Date.now() / 1000) return null;
      var name = String(claims.name || '').trim().slice(0, 80);
      if (!name) return null;
      return {name: name, expiresAt: Math.min(Number(claims.exp) * 1000, Date.now() + 60 * 60 * 1000)};
    } catch (_) { return null; }
  }

  function onGoogleCredential(response) {
    var profile = decodeCredential(response && response.credential);
    if (!profile) {
      notify('Không xác định được thông tin tài khoản. Vui lòng đăng nhập lại.');
      return;
    }
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(profile)); } catch (_) {}
    showSignedIn(profile);
  }

  function onGoogleReady() {
    if (!window.google || !google.accounts || !google.accounts.id) {
      notify('Không thể tải tính năng đăng nhập Google.');
      return;
    }
    try {
      root.hidden = false;
      google.accounts.id.initialize({client_id: clientId, callback: onGoogleCredential, auto_select: false});
      google.accounts.id.renderButton(signin, {
        type: 'standard', theme: 'outline', size: 'medium',
        text: 'signin_with', shape: 'pill', locale: 'vi', width: 180
      });
      var cached = readCachedProfile();
      if (cached) showSignedIn(cached);
      else showSignedOut();
    } catch (_) {
      notify('Đăng nhập Google chưa sẵn sàng. Vui lòng thử tải lại trang.');
    }
  }

  signout.addEventListener('click', function () {
    try { localStorage.removeItem(STORAGE_KEY); } catch (_) {}
    try { if (window.google && google.accounts && google.accounts.id) google.accounts.id.disableAutoSelect(); } catch (_) {}
    showSignedOut();
  });

  // Update the greeting when the user's local time crosses a daypart boundary.
  setInterval(function () {
    if (activeProfile && activeProfile.expiresAt <= Date.now()) {
      try { localStorage.removeItem(STORAGE_KEY); } catch (_) {}
      showSignedOut();
    } else if (activeProfile) {
      greeting.textContent = daypart(new Date().getHours()) + ', ' + activeProfile.name + '!';
    }
  }, 60 * 1000);

  var script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client?hl=vi';
  script.async = true;
  script.defer = true;
  script.onload = onGoogleReady;
  script.onerror = function () { notify('Không thể tải đăng nhập Google.'); };
  document.head.appendChild(script);
})();
