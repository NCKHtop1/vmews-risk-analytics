/* FinQuery: Google profile and per-user local personalization.
 * Google Identity Services supplies the account name, verified email and photo.
 * This client-side display is NOT an authorization/session boundary.
 * No Google token or client secret is persisted or sent to FinQuery.
 * Nicknames and symbols remain on this browser, partitioned by Google "sub".
 */
(function () {
  'use strict';

  var clientMeta = document.querySelector('meta[name="finquery-google-client-id"]');
  var clientId = clientMeta && (clientMeta.getAttribute('content') || '').trim();
  var el = function (id) { return document.getElementById(id); };
  var root = el('finquery-google-account');
  if (!root || !/^[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com$/i.test(clientId || '')) return;

  var signin = el('finquery-google-signin');
  var identity = el('finquery-google-identity');
  var greeting = el('finquery-google-greeting');
  var avatarTrigger = el('finquery-user-trigger');
  var menu = el('finquery-user-menu');
  var menuClose = el('finquery-user-menu-close');
  var avatar = el('finquery-google-avatar');
  var avatarFallback = el('finquery-google-avatar-fallback');
  var panelAvatar = el('finquery-google-panel-avatar');
  var panelFallback = el('finquery-google-panel-fallback');
  var shortName = el('finquery-google-shortname');
  var profileName = el('finquery-google-profile-name');
  var profileEmail = el('finquery-google-profile-email');
  var nicknameInput = el('finquery-nickname');
  var nicknameSave = el('finquery-nickname-save');
  var favoriteForm = el('finquery-favorite-form');
  var favoriteInput = el('finquery-favorite-input');
  var favoriteList = el('finquery-favorite-list');
  var favoriteEmpty = el('finquery-favorite-empty');
  var favoriteCounter = el('finquery-favorite-count');
  var signout = el('finquery-google-signout');
  var status = el('finquery-google-status');
  var feedback = el('finquery-user-feedback');

  if ([signin, identity, greeting, avatarTrigger, menu, menuClose, avatar,
       avatarFallback, panelAvatar, panelFallback, shortName, profileName,
       profileEmail, nicknameInput, nicknameSave, favoriteForm, favoriteInput,
       favoriteList, favoriteEmpty, favoriteCounter, signout].some(function (node) { return !node; })) return;

  var PROFILE_KEY = 'finquery_google_profile_v1'; // preserve old key; require a new "sub" on read
  var PREF_PREFIX = 'finquery_google_preferences_v1_';
  var MAX_FAVORITES = 8;
  var activeProfile = null;
  var preferences = {nickname: '', favorites: []};

  function readStorage(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }
  function writeStorage(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* private mode/quota */ }
  }
  function eraseStorage(key) {
    try { localStorage.removeItem(key); } catch (_) { /* storage blocked */ }
  }
  function daypart(hour) {
    if (hour >= 5 && hour < 11) return 'Xin chào buổi sáng';
    if (hour >= 11 && hour < 14) return 'Xin chào buổi trưa';
    if (hour >= 14 && hour < 18) return 'Xin chào buổi chiều';
    return 'Xin chào buổi tối';
  }
  function cleanNickname(value) {
    return String(value || '').trim().replace(/\s+/g, ' ').slice(0, 32);
  }
  function cleanSymbol(value) {
    var result = String(value || '').trim().toUpperCase();
    return /^[A-Z]{2,5}$/.test(result) ? result : '';
  }
  function safePicture(url) {
    try {
      var parsed = new URL(String(url || ''));
      if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return '';
      if (parsed.hostname !== 'googleusercontent.com' && !parsed.hostname.endsWith('.googleusercontent.com')) return '';
      return parsed.href;
    } catch (_) { return ''; }
  }
  function prefsKey(profile) {
    var sub = String(profile && profile.sub || '');
    return /^[A-Za-z0-9_-]{3,150}$/.test(sub) ? PREF_PREFIX + sub : '';
  }
  function readPreferences(profile) {
    var result = {nickname: '', favorites: []};
    var key = prefsKey(profile);
    if (!key) return result;
    try {
      var saved = JSON.parse(readStorage(key) || 'null');
      if (!saved || typeof saved !== 'object') return result;
      result.nickname = cleanNickname(saved.nickname);
      if (Array.isArray(saved.favorites)) {
        var seen = new Set();
        saved.favorites.forEach(function (value) {
          var symbol = cleanSymbol(value);
          if (symbol && !seen.has(symbol) && result.favorites.length < MAX_FAVORITES) {
            seen.add(symbol);
            result.favorites.push(symbol);
          }
        });
      }
    } catch (_) { /* bad local data */ }
    return result;
  }
  function savePreferences() {
    var key = prefsKey(activeProfile);
    if (key) writeStorage(key, JSON.stringify(preferences));
  }
  function notify(message) {
    if (status) status.textContent = message || '';
    if (feedback) feedback.textContent = message || '';
  }
  function displayName() {
    return preferences.nickname || (activeProfile && activeProfile.name) || '';
  }
  function updateGreeting() {
    if (!activeProfile) return;
    var name = displayName();
    greeting.textContent = daypart(new Date().getHours()) + ', ' + name + '!';
    shortName.textContent = name;
    avatarTrigger.setAttribute('aria-label', 'Mở tài khoản Google của ' + name);
  }
  function setupPhoto(image, fallback, profile) {
    var name = displayName();
    fallback.textContent = (Array.from(name.trim())[0] || 'G').toUpperCase();
    image.hidden = true;
    fallback.hidden = false;
    image.onload = null;
    image.onerror = null;
    var safeUrl = profile ? safePicture(profile.picture) : '';
    if (!safeUrl) {
      image.removeAttribute('src');
      return;
    }
    image.onload = function () {
      image.hidden = false;
      fallback.hidden = true;
    };
    image.onerror = function () {
      image.hidden = true;
      fallback.hidden = false;
    };
    image.referrerPolicy = 'no-referrer';
    image.src = safeUrl;
  }
  function favoriteUrl(symbol) {
    var url = new URL(window.location.href);
    url.searchParams.set('symbol', symbol);
    url.hash = 'market';
    return url.pathname + url.search + url.hash;
  }
  function renderFavorites() {
    favoriteList.replaceChildren();
    favoriteEmpty.hidden = preferences.favorites.length > 0;
    favoriteCounter.textContent = preferences.favorites.length + '/' + MAX_FAVORITES;
    preferences.favorites.forEach(function (symbol) {
      var chip = document.createElement('span');
      chip.className = 'finquery-favorite-chip';
      var link = document.createElement('a');
      link.className = 'finquery-favorite-link';
      link.href = favoriteUrl(symbol);
      link.textContent = symbol;
      link.title = 'Mở FinQuery với mã ' + symbol;
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'finquery-favorite-remove';
      remove.textContent = '×';
      remove.setAttribute('aria-label', 'Bỏ mã ' + symbol + ' khỏi danh sách quan tâm');
      remove.addEventListener('click', function () {
        preferences.favorites = preferences.favorites.filter(function (item) { return item !== symbol; });
        savePreferences();
        renderFavorites();
        notify('Đã bỏ ' + symbol + ' khỏi mã quan tâm.');
      });
      chip.appendChild(link);
      chip.appendChild(remove);
      favoriteList.appendChild(chip);
    });
  }
  function refreshProfile() {
    if (!activeProfile) return;
    updateGreeting();
    profileName.textContent = activeProfile.name;
    profileEmail.textContent = activeProfile.email || 'Tài khoản Google';
    nicknameInput.value = preferences.nickname;
    nicknameInput.placeholder = activeProfile.name;
    setupPhoto(avatar, avatarFallback, activeProfile);
    setupPhoto(panelAvatar, panelFallback, activeProfile);
    renderFavorites();
  }
  function closeMenu(restoreFocus) {
    menu.hidden = true;
    avatarTrigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus && !identity.hidden) avatarTrigger.focus();
  }
  function showSignedOut() {
    closeMenu(false);
    activeProfile = null;
    preferences = {nickname: '', favorites: []};
    identity.hidden = true;
    signin.hidden = false;
    notify('Bạn chưa đăng nhập Google.');
  }
  function showSignedIn(profile) {
    if (!profile || !profile.name || !prefsKey(profile) ||
        !Number.isFinite(profile.expiresAt) || profile.expiresAt <= Date.now()) {
      eraseStorage(PROFILE_KEY);
      showSignedOut();
      return;
    }
    closeMenu(false);
    activeProfile = profile;
    preferences = readPreferences(profile);
    refreshProfile();
    identity.hidden = false;
    signin.hidden = true;
    notify('');
  }
  function readCachedProfile() {
    try {
      var profile = JSON.parse(readStorage(PROFILE_KEY) || 'null');
      if (profile && typeof profile.name === 'string' && profile.name.length <= 80 &&
          prefsKey(profile) && Number.isFinite(profile.expiresAt) && profile.expiresAt > Date.now()) {
        return {
          sub: profile.sub, name: profile.name,
          email: String(profile.email || '').slice(0, 140),
          picture: safePicture(profile.picture),
          expiresAt: profile.expiresAt
        };
      }
    } catch (_) {}
    eraseStorage(PROFILE_KEY);
    return null;
  }
  function decodeCredential(jwt) {
    // Display-only parsing: JWT signature is NOT verified in this static website.
    // Never use this profile to grant permissions or access private APIs.
    if (typeof jwt !== 'string' || jwt.split('.').length !== 3) return null;
    try {
      var encoded = jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      var raw = atob(encoded + '='.repeat((4 - encoded.length % 4) % 4));
      var claims = JSON.parse(new TextDecoder().decode(Uint8Array.from(raw, function (c) {
        return c.charCodeAt(0);
      })));
      if (!Number.isFinite(Number(claims.exp)) || claims.aud !== clientId ||
          !['accounts.google.com', 'https://accounts.google.com'].includes(claims.iss) ||
          !prefsKey({sub: claims.sub}) || Number(claims.exp) <= Date.now() / 1000) return null;
      var name = String(claims.name || '').trim().slice(0, 80);
      if (!name) return null;
      return {
        sub: String(claims.sub),
        name: name,
        email: claims.email_verified === true ? String(claims.email || '').slice(0, 140) : '',
        picture: safePicture(claims.picture),
        expiresAt: Math.min(Number(claims.exp) * 1000, Date.now() + 60 * 60 * 1000)
      };
    } catch (_) { return null; }
  }
  function onGoogleCredential(response) {
    var profile = decodeCredential(response && response.credential);
    if (!profile) {
      notify('Không đọc được thông tin Google. Vui lòng thử đăng nhập lại.');
      return;
    }
    writeStorage(PROFILE_KEY, JSON.stringify(profile));
    showSignedIn(profile);
  }
  function onGoogleReady() {
    if (!window.google || !google.accounts || !google.accounts.id) {
      notify('Không thể tải chức năng đăng nhập Google.');
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
      notify('Đăng nhập Google chưa sẵn sàng. Hãy thử tải lại trang.');
    }
  }

  avatarTrigger.addEventListener('click', function () {
    if (!activeProfile) return;
    var opening = menu.hidden;
    if (opening) {
      menu.hidden = false;
      avatarTrigger.setAttribute('aria-expanded', 'true');
      menuClose.focus();
    } else closeMenu(false);
  });
  menuClose.addEventListener('click', function () { closeMenu(true); });
  document.addEventListener('pointerdown', function (event) {
    if (!menu.hidden && !root.contains(event.target)) closeMenu(false);
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !menu.hidden) closeMenu(true);
  });

  nicknameSave.addEventListener('click', function () {
    if (!activeProfile) return;
    preferences.nickname = cleanNickname(nicknameInput.value);
    savePreferences();
    refreshProfile();
    notify(preferences.nickname ? 'Đã lưu tên gọi của bạn.' : 'Đã trở về tên Google.');
  });
  nicknameInput.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      nicknameSave.click();
    }
  });
  favoriteForm.addEventListener('submit', function (event) {
    event.preventDefault();
    if (!activeProfile) return;
    var symbol = cleanSymbol(favoriteInput.value);
    if (!symbol) { notify('Nhập mã chứng khoán 2–5 chữ cái, ví dụ MBB hoặc FPT.'); return; }
    if (preferences.favorites.includes(symbol)) { notify(symbol + ' đã có trong danh sách.'); return; }
    if (preferences.favorites.length >= MAX_FAVORITES) { notify('Bạn có thể lưu tối đa ' + MAX_FAVORITES + ' mã.'); return; }
    preferences.favorites.push(symbol);
    savePreferences();
    favoriteInput.value = '';
    renderFavorites();
    notify('Đã thêm ' + symbol + ' vào mã quan tâm.');
  });
  signout.addEventListener('click', function () {
    eraseStorage(PROFILE_KEY);
    try { if (window.google && google.accounts && google.accounts.id) google.accounts.id.disableAutoSelect(); } catch (_) {}
    showSignedOut();
  });
  setInterval(function () {
    if (!activeProfile) return;
    if (activeProfile.expiresAt <= Date.now()) {
      eraseStorage(PROFILE_KEY);
      showSignedOut();
    } else updateGreeting();
  }, 60 * 1000);

  var sdk = document.createElement('script');
  sdk.src = 'https://accounts.google.com/gsi/client?hl=vi';
  sdk.async = true;
  sdk.defer = true;
  sdk.onload = onGoogleReady;
  sdk.onerror = function () { notify('Không thể tải đăng nhập Google.'); };
  document.head.appendChild(sdk);
})();
