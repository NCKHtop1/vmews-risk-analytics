/* FinQuery Google greeting + avatar, with no account dropdown.
 * The browser-only Google profile is for display, not access control.
 * Neither Google ID tokens nor client secrets are stored.
 */
(function () {
  'use strict';

  var meta = document.querySelector('meta[name="finquery-google-client-id"]');
  var clientId = meta && String(meta.getAttribute('content') || '').trim();
  var root = document.getElementById('finquery-google-account');
  if (!root || !/^[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com$/i.test(clientId || '')) return;

  var signIn = document.getElementById('finquery-google-signin');
  var identity = document.getElementById('finquery-google-identity');
  var greeting = document.getElementById('finquery-google-greeting');
  var avatar = document.getElementById('finquery-google-avatar');
  var fallback = document.getElementById('finquery-google-avatar-fallback');
  var status = document.getElementById('finquery-google-status');
  if (!signIn || !identity || !greeting || !avatar || !fallback) return;

  // Keep the existing key so the user's already displayed Google session survives.
  var STORAGE_KEY = 'finquery_google_profile_v1';
  var activeProfile = null;

  function getStorage() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (_) { return null; }
  }
  function setStorage(profile) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(profile)); } catch (_) {}
  }
  function clearStorage() {
    try { localStorage.removeItem(STORAGE_KEY); } catch (_) {}
  }
  function daypart(hour) {
    if (hour >= 5 && hour < 11) return 'Xin chào buổi sáng';
    if (hour >= 11 && hour < 14) return 'Xin chào buổi trưa';
    if (hour >= 14 && hour < 18) return 'Xin chào buổi chiều';
    return 'Xin chào buổi tối';
  }
  function safePicture(value) {
    try {
      var url = new URL(String(value || ''));
      if (url.protocol !== 'https:' || url.username || url.password ||
          (url.hostname !== 'googleusercontent.com' && !url.hostname.endsWith('.googleusercontent.com'))) return '';
      return url.href.length <= 2048 ? url.href : '';
    } catch (_) { return ''; }
  }
  function cleanProfile(input) {
    if (!input || typeof input.name !== 'string' || !input.name.trim() ||
        input.name.length > 80 || typeof input.sub !== 'string' ||
        !/^[A-Za-z0-9_-]{3,150}$/.test(input.sub) ||
        !Number.isFinite(input.expiresAt) || input.expiresAt <= Date.now()) return null;
    return {
      sub: input.sub,
      name: input.name.trim(),
      picture: safePicture(input.picture),
      expiresAt: input.expiresAt
    };
  }
  function updateGreeting() {
    if (activeProfile) greeting.textContent = daypart(new Date().getHours()) + ', ' + activeProfile.name + '!';
  }
  function updateAvatar(profile) {
    fallback.textContent = (Array.from(profile.name)[0] || 'G').toUpperCase();
    fallback.hidden = false;
    avatar.hidden = true;
    avatar.onload = null;
    avatar.onerror = null;
    var src = safePicture(profile.picture);
    if (!src) {
      avatar.removeAttribute('src');
      return;
    }
    avatar.onload = function () {
      avatar.hidden = false;
      fallback.hidden = true;
    };
    avatar.onerror = function () {
      avatar.hidden = true;
      fallback.hidden = false;
    };
    avatar.referrerPolicy = 'no-referrer';
    avatar.src = src;
  }
  function showSignedOut() {
    activeProfile = null;
    identity.hidden = true;
    signIn.hidden = false;
    if (status) status.textContent = 'Đăng nhập bằng Google để hiển thị lời chào và ảnh đại diện.';
  }
  function showSignedIn(input) {
    var profile = cleanProfile(input);
    if (!profile) {
      clearStorage();
      showSignedOut();
      return;
    }
    activeProfile = profile;
    updateGreeting();
    updateAvatar(profile);
    identity.hidden = false;
    signIn.hidden = true;
    if (status) status.textContent = 'Đã hiển thị tên và ảnh Google.';
  }
  function readCachedProfile() {
    try {
      var profile = cleanProfile(JSON.parse(getStorage() || 'null'));
      if (profile) return profile;
    } catch (_) {}
    clearStorage();
    return null;
  }
  function decodeCredential(credential) {
    // These claims are for cosmetic display ONLY. Signature verification and
    // authorization require a separate server-side authentication system.
    if (typeof credential !== 'string' || credential.split('.').length !== 3) return null;
    try {
      var encoded = credential.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      var raw = atob(encoded + '='.repeat((4 - encoded.length % 4) % 4));
      var claims = JSON.parse(new TextDecoder().decode(Uint8Array.from(raw, function (c) {
        return c.charCodeAt(0);
      })));
      if (claims.aud !== clientId ||
          !['accounts.google.com', 'https://accounts.google.com'].includes(claims.iss) ||
          !Number.isFinite(Number(claims.exp)) || Number(claims.exp) <= Date.now() / 1000) return null;
      return cleanProfile({
        sub: claims.sub,
        name: claims.name,
        picture: claims.picture,
        expiresAt: Math.min(Number(claims.exp) * 1000, Date.now() + 60 * 60 * 1000)
      });
    } catch (_) { return null; }
  }
  function onCredential(response) {
    var profile = decodeCredential(response && response.credential);
    if (!profile) {
      if (status) status.textContent = 'Không đọc được thông tin Google. Vui lòng thử đăng nhập lại.';
      return;
    }
    setStorage(profile);
    showSignedIn(profile);
  }
  function onGoogleReady() {
    if (!window.google || !google.accounts || !google.accounts.id) {
      if (status) status.textContent = 'Không thể tải đăng nhập Google.';
      return;
    }
    try {
      root.hidden = false;
      google.accounts.id.initialize({client_id: clientId, callback: onCredential, auto_select: false});
      google.accounts.id.renderButton(signIn, {
        type: 'standard', theme: 'outline', size: 'medium',
        text: 'signin_with', shape: 'pill', locale: 'vi', width: 180
      });
      var cached = readCachedProfile();
      if (cached) showSignedIn(cached);
      else showSignedOut();
    } catch (_) {
      if (status) status.textContent = 'Đăng nhập Google chưa sẵn sàng. Vui lòng tải lại trang.';
    }
  }
  setInterval(function () {
    if (!activeProfile) return;
    if (activeProfile.expiresAt <= Date.now()) {
      clearStorage();
      showSignedOut();
    } else updateGreeting();
  }, 60 * 1000);

  var script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client?hl=vi';
  script.async = true;
  script.defer = true;
  script.onload = onGoogleReady;
  script.onerror = function () {
    if (status) status.textContent = 'Không thể tải Google Identity Services.';
  };
  document.head.appendChild(script);
})();
