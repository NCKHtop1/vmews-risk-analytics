'use strict';
/* Deterministic unit + regression suite for Google Identity Services UI.
 * This test never uses a real Google account; Google OAuth discovery has a
 * separate read-only remote probe in CI. The identity is cosmetic only.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'frontend', 'index.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'frontend', 'google-signin.js'), 'utf8');
const build = fs.readFileSync(path.join(root, 'scripts', 'build_cdn.py'), 'utf8');
const clientId = html.match(/<meta name="finquery-google-client-id" content="([^"]+)">/)?.[1];
const verifiedClientId = '216957728290-6h80djpq7ouk2cmd5jgjr08j6233voes.apps.googleusercontent.com';

assert.equal(clientId, verifiedClientId, 'Client ID must match the one issued by Google');
assert.match(clientId, /^[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com$/);
assert.ok(!html.includes('5jgir08j'), 'The former invalid_client typo is forbidden');
assert.ok(!html.includes('client-secret'), 'Google Client Secret must not be embedded');
assert.match(html, /defer src="google-signin.js"/);
assert.match(build, /front \/ 'google-signin\.js'/);
for (const id of [
  'finquery-google-account', 'finquery-google-signin', 'finquery-google-identity',
  'finquery-google-avatar', 'finquery-google-panel-avatar', 'finquery-user-trigger',
  'finquery-user-menu', 'finquery-user-menu-close', 'finquery-google-greeting',
  'finquery-google-profile-name', 'finquery-google-profile-email', 'finquery-nickname',
  'finquery-nickname-save', 'finquery-favorite-input', 'finquery-favorite-form',
  'finquery-favorite-list', 'finquery-favorite-count', 'finquery-google-signout'
]) assert.ok(html.includes('id="' + id + '"'), 'Missing account UI element: ' + id);
assert.match(html, /@media\(max-width:700px\)\{\.finquery-google-account/);
assert.match(html, /Cá nhân hóa chỉ lưu trên trình duyệt này/);

if (process.env.FINQUERY_VERIFY_BUNDLE === '1') {
  const bundle = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const bId = bundle.match(/<meta name="finquery-google-client-id" content="([^"]+)"/)?.[1];
  assert.equal(bId, verifiedClientId, 'Standalone CDN HTML must match Google Client ID');
  assert.ok(bundle.includes('id="finquery-user-trigger"'));
  assert.ok(bundle.includes('function safePicture('));
  assert.ok(bundle.includes('function readPreferences('));
  assert.ok(bundle.includes('finquery-favorite-list'));
  assert.ok(bundle.includes('"symbol":"MBB"'), 'Existing report data must survive build');
  assert.ok(bundle.includes('finquery-visitor-total'), 'Existing visitor counter must survive build');
}

const store = new Map();
function fakeJwt(claims) {
  const b64 = obj => Buffer.from(JSON.stringify(obj)).toString('base64url');
  return b64({alg: 'RS256', typ: 'JWT'}) + '.' + b64(claims) + '.placeholder-signature';
}
class FakeNode {
  constructor(tag, id) {
    this.tagName = tag.toUpperCase();
    this.id = id || '';
    this.children = [];
    this.hidden = false;
    this.textContent = '';
    this.value = '';
    this.placeholder = '';
    this.href = '';
    this.src = '';
    this.className = '';
    this.title = '';
    this.listeners = {};
    this.attributes = {};
    this.focused = false;
  }
  appendChild(node) { this.children.push(node); node.parent = this; return node; }
  replaceChildren(...nodes) { this.children = [...nodes]; for (const n of nodes) n.parent = this; }
  removeAttribute(name) { delete this.attributes[name]; if (name === 'src') this.src = ''; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  addEventListener(name, cb) { this.listeners[name] = cb; }
  contains(other) {
    return other === this || this.children.some(child => child.contains(other));
  }
  focus() { this.focused = true; }
  click() { this.listeners.click?.({target: this, preventDefault() {}}); }
  submit() { this.listeners.submit?.({target: this, preventDefault() {}}); }
}
function makeApp() {
  let hour = 8;
  let options, intervalTick, rendered = false, autoSelectDisabled = false;
  const ids = {};
  const names = [
    'finquery-google-account','finquery-google-signin','finquery-google-identity',
    'finquery-google-greeting','finquery-user-trigger','finquery-user-menu',
    'finquery-user-menu-close','finquery-google-avatar','finquery-google-avatar-fallback',
    'finquery-google-panel-avatar','finquery-google-panel-fallback','finquery-google-shortname',
    'finquery-google-profile-name','finquery-google-profile-email',
    'finquery-nickname','finquery-nickname-save','finquery-favorite-form',
    'finquery-favorite-input','finquery-favorite-list','finquery-favorite-empty',
    'finquery-favorite-count','finquery-google-signout','finquery-google-status','finquery-user-feedback'
  ];
  for (const name of names) ids[name] = new FakeNode('div', name);
  const parent = ids['finquery-google-account'];
  const signed = ids['finquery-google-identity'];
  parent.appendChild(ids['finquery-google-signin']);
  parent.appendChild(signed);
  signed.appendChild(ids['finquery-user-trigger']);
  signed.appendChild(ids['finquery-user-menu']);
  ids['finquery-user-menu'].hidden = true;
  ids['finquery-google-account'].hidden = true;
  ids['finquery-google-identity'].hidden = true;
  const docListeners = {};
  const google = {accounts: {id: {
    initialize(o) { options = o; },
    renderButton(node, cfg) {
      assert.equal(node, ids['finquery-google-signin']);
      assert.equal(cfg.locale, 'vi');
      rendered = true;
    },
    disableAutoSelect() { autoSelectDisabled = true; }
  }}};
  const document = {
    querySelector: selector => selector === 'meta[name="finquery-google-client-id"]'
      ? {getAttribute: key => key === 'content' ? clientId : null} : null,
    getElementById: id => ids[id] || null,
    createElement: tag => new FakeNode(tag),
    addEventListener: (event, cb) => {docListeners[event] = cb;},
    head: {appendChild(node) {
      assert.match(node.src, /^https:\/\/accounts\.google\.com\/gsi\/client/);
      node.onload();
    }}
  };
  class FakeDate extends Date {
    getHours() { return hour; }
  }
  const env = {
    window: {google, location: {href: 'https://finquery.info.vn/financial-report/index.html?symbol=MBB&mode=quarter'}},
    google, document, URL, localStorage: {
      getItem: key => store.get(key) || null,
      setItem: (key, value) => store.set(key, value),
      removeItem: key => store.delete(key)
    },
    Date: FakeDate, TextDecoder, Uint8Array, atob: b64 => Buffer.from(b64, 'base64').toString('binary'),
    setInterval: cb => {intervalTick = cb; return 1;}
  };
  vm.runInNewContext(js, env, {filename: 'google-signin.js', timeout: 2000});
  return {
    ids, document, docListeners, google, store,
    get options() { return options; },
    get rendered() { return rendered; },
    get autoSelectDisabled() { return autoSelectDisabled; },
    hour: h => {hour = h;}, tick: () => intervalTick(),
    login: claims => options.callback({credential: fakeJwt(claims)})
  };
}
const a = makeApp();
const by = id => a.ids['finquery-' + id];
assert.equal(a.rendered, true);
assert.equal(by('google-account').hidden, false);
assert.equal(by('google-identity').hidden, true);

const claimsA = {
  aud: clientId, iss: 'https://accounts.google.com', sub: 'account-a-001',
  name: 'Hailn', email: 'example-a@gmail.com', email_verified: true,
  picture: 'https://lh3.googleusercontent.com/a/test-avatar-A',
  exp: Math.floor(Date.now() / 1000) + 1800
};
for (const [hour, period] of [
  [8,'Xin chào buổi sáng'], [12,'Xin chào buổi trưa'],
  [16,'Xin chào buổi chiều'], [21,'Xin chào buổi tối']
]) {
  a.hour(hour);
  a.login(claimsA);
  assert.equal(by('google-greeting').textContent, period + ', Hailn!');
  assert.equal(by('google-identity').hidden, false);
  assert.equal(by('google-signin').hidden, true);
}
assert.equal(by('google-profile-email').textContent, claimsA.email);
assert.equal(by('google-avatar').src, claimsA.picture, 'Google avatar URL should be loaded');
by('google-avatar').onload();
assert.equal(by('google-avatar').hidden, false, 'Photo becomes visible once loaded');
assert.equal(by('google-avatar-fallback').hidden, true);
assert.equal(by('google-panel-avatar').src, claimsA.picture);
assert.ok(a.store.has('finquery_google_profile_v1'), 'Temporary profile should persist without token');
assert.ok(!a.store.get('finquery_google_profile_v1').includes('placeholder-signature'), 'Never persist JWT');

by('user-trigger').click();
assert.equal(by('user-menu').hidden, false);
assert.equal(by('user-trigger').getAttribute('aria-expanded'), 'true');
assert.equal(by('user-menu-close').focused, true);
a.docListeners.keydown({key: 'Escape'});
assert.equal(by('user-menu').hidden, true);
assert.equal(by('user-trigger').getAttribute('aria-expanded'), 'false');

by('user-trigger').click();
a.docListeners.pointerdown({target: new FakeNode('div')});
assert.equal(by('user-menu').hidden, true, 'Click outside should close panel');

by('nickname').value = '  Anh Hải  ';
by('nickname-save').click();
assert.equal(by('google-greeting').textContent, 'Xin chào buổi tối, Anh Hải!');
assert.equal(by('google-shortname').textContent, 'Anh Hải');
assert.equal(JSON.parse(a.store.get('finquery_google_preferences_v1_account-a-001')).nickname, 'Anh Hải');

by('favorite-input').value = 'fpt';
by('favorite-form').submit();
by('favorite-input').value = 'MBB';
by('favorite-form').submit();
assert.equal(by('favorite-count').textContent, '2/8');
assert.equal(by('favorite-empty').hidden, true);
assert.equal(by('favorite-list').children.length, 2);
assert.equal(by('favorite-list').children[0].children[0].textContent, 'FPT');
assert.match(by('favorite-list').children[0].children[0].href, /symbol=FPT&mode=quarter#market$/);
assert.equal(JSON.parse(a.store.get('finquery_google_preferences_v1_account-a-001')).favorites.join(','), 'FPT,MBB');
by('favorite-input').value = 'MBB';
by('favorite-form').submit();
assert.equal(by('favorite-list').children.length, 2, 'Repeated symbol must not duplicate');
by('favorite-input').value = '<img>';
by('favorite-form').submit();
assert.equal(by('favorite-list').children.length, 2, 'Invalid ticker must be rejected');
by('favorite-list').children[0].children[1].click();
assert.equal(by('favorite-count').textContent, '1/8');
assert.equal(by('favorite-list').children[0].children[0].textContent, 'MBB');

by('user-trigger').click();
by('google-signout').click();
assert.equal(a.autoSelectDisabled, true);
assert.equal(by('google-identity').hidden, true);
assert.equal(by('user-menu').hidden, true);
assert.equal(a.store.has('finquery_google_profile_v1'), false);
assert.ok(a.store.has('finquery_google_preferences_v1_account-a-001'),
  'Sign out clears session but preserves local preferences for next visit');

// Test cross-account isolation in the same browser.
const claimsB = {...claimsA, sub: 'account-b-002', name: 'Người dùng B', email: 'example-b@gmail.com',
  picture: 'https://untrusted.example/evil.png'};
a.login(claimsB);
assert.equal(by('google-greeting').textContent, 'Xin chào buổi tối, Người dùng B!');
assert.equal(by('favorite-count').textContent, '0/8');
assert.equal(by('google-avatar').src, '', 'Non-Google avatar URL must be blocked');
assert.equal(by('google-avatar-fallback').hidden, false);
a.login(claimsA);
assert.equal(by('google-greeting').textContent, 'Xin chào buổi tối, Anh Hải!');
assert.equal(by('favorite-count').textContent, '1/8');
assert.equal(by('favorite-list').children[0].children[0].textContent, 'MBB');

by('nickname').value = '';
by('nickname-save').click();
assert.equal(by('google-greeting').textContent, 'Xin chào buổi tối, Hailn!');
assert.equal(JSON.parse(a.store.get('finquery_google_preferences_v1_account-a-001')).nickname, '');
a.login({...claimsA, aud: 'unregistered-client.apps.googleusercontent.com'});
assert.equal(by('google-greeting').textContent, 'Xin chào buổi tối, Hailn!', 'Invalid token must not replace profile');
a.login({...claimsA, exp: 100});
assert.equal(by('google-greeting').textContent, 'Xin chào buổi tối, Hailn!');
a.login({...claimsA, email_verified: false, picture: 'javascript:alert(1)'});
assert.equal(by('google-profile-email').textContent, 'Tài khoản Google');
assert.equal(by('google-avatar').src, '');
assert.equal(by('google-avatar-fallback').hidden, false);
assert.equal(by('google-signout').hidden, false);

const freshApp = makeApp();
assert.equal(freshApp.ids['finquery-google-identity'].hidden, false, 'Reload restores non-expired profile');
assert.equal(freshApp.ids['finquery-favorite-count'].textContent, '1/8');
assert.equal(freshApp.ids['finquery-google-greeting'].textContent, 'Xin chào buổi sáng, Hailn!');
a.store.set('finquery_google_profile_v1', JSON.stringify({name: 'Legacy name', expiresAt: Date.now() + 360000}));
const legacyApp = makeApp();
assert.equal(legacyApp.ids['finquery-google-identity'].hidden, true, 'Legacy cache missing Google sub must sign out safely');
assert.equal(a.store.has('finquery_google_profile_v1'), false);

console.log('PASS: verified Google Client ID, Google avatar and fallback, user menu, keyboard, greeting, nickname, favorites, local per-user isolation, logout, JWT hygiene and standalone UI contract.');
