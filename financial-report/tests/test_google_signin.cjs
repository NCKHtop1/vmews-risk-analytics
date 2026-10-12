'use strict';
/* Zero-dependency display-personalization regression checks.
 * These assertions do not test Google's real popup/consent configuration.
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

assert.match(clientId || '', /^[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com$/);
// Pin the exact public identifier copied from the Google Cloud OAuth client screen.
// A regex alone passed the former misread j/i ID, yet Google rejected it with 401.
const verifiedClientId = '216957728290-6h80djpq7ouk2cmd5jgjr08j6233voes.apps.googleusercontent.com';
assert.equal(clientId, verifiedClientId, 'Google Client ID differs from Google Cloud; check every character');
assert.ok(!html.includes('5jgir08j'), 'Do not reintroduce the rejected 401 Client ID');
assert.match(html, /id="finquery-google-account"/);
assert.match(html, /id="finquery-google-greeting"/);
assert.match(html, /id="finquery-google-signout"/);
assert.match(html, /defer src="google-signin.js"/);
assert.match(build, /front \/ 'google-signin\.js'/);
assert.ok(!html.includes('client-secret'), 'Never embed a client secret in the page');
if (process.env.FINQUERY_VERIFY_BUNDLE === '1') {
  const bundle = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const bundleClientId = bundle.match(/<meta name="finquery-google-client-id" content="([^"]+)"/)?.[1];
  assert.equal(bundleClientId, clientId, 'Generated standalone HTML has a different Google Client ID');
  assert.match(bundle, /id="finquery-google-signin"/);
  assert.match(bundle, /https:\/\/accounts\.google\.com\/gsi\/client/);
  assert.ok(!bundle.includes('5jgir08j'), 'Stale Client ID leaked into generated HTML');
}


function fakeJwt(claims) {
  const b64 = o => Buffer.from(JSON.stringify(o)).toString('base64url');
  return b64({alg: 'RS256', typ: 'JWT'}) + '.' + b64(claims) + '.placeholder-signature';
}

function setup() {
  let hour = 8;
  let opts, rendered = false, detached = false;
  const storage = new Map();
  const ids = {};
  for (const key of ['finquery-google-account', 'finquery-google-signin',
    'finquery-google-identity', 'finquery-google-greeting',
    'finquery-google-signout', 'finquery-google-status']) {
    ids[key] = {hidden: true, textContent: '', listeners: {},
      addEventListener(name, cb) { this.listeners[name] = cb; }};
  }
  const google = {accounts: {id: {
    initialize(o) { opts = o; },
    renderButton(el, cfg) { assert.equal(el, ids['finquery-google-signin']); rendered = true; assert.equal(cfg.locale, 'vi'); },
    disableAutoSelect() { detached = true; }
  }}};
  const document = {
    getElementById: id => ids[id] || null,
    querySelector: selector => selector === 'meta[name="finquery-google-client-id"]' ?
      {getAttribute: key => key === 'content' ? clientId : null} : null,
    createElement: tag => { assert.equal(tag, 'script'); return {src: '', async: false, defer: false, onload: null, onerror: null}; },
    head: {appendChild(el) { assert.match(el.src, /^https:\/\/accounts\.google\.com\/gsi\/client/); el.onload(); }}
  };
  class LocalDate extends Date {
    getHours() { return hour; }
  }
  const env = {
    document, window: {google}, google, localStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, val) => storage.set(key, val),
      removeItem: key => storage.delete(key)
    },
    Date: LocalDate, Number, String, JSON, Object, Uint8Array, TextDecoder,
    atob: encoded => Buffer.from(encoded, 'base64').toString('binary'),
    setInterval: () => 1
  };
  vm.runInNewContext(js, env, {filename: 'google-signin.js', timeout: 1500});
  return {ids, google, storage, opts, rendered, setHour: n => {hour = n;},
    disabled: () => detached};
}

const app = setup();
assert.equal(app.rendered, true, 'Google login must render after SDK loads');
assert.equal(app.ids['finquery-google-account'].hidden, false);
assert.equal(app.ids['finquery-google-identity'].hidden, true);
const claims = {
  aud: clientId, iss: 'https://accounts.google.com', sub: 'subject-test',
  name: 'Nguyễn Văn A', exp: Math.floor(Date.now() / 1000) + 1800
};
const cases = [
  [8, 'Xin chào buổi sáng'], [12, 'Xin chào buổi trưa'],
  [16, 'Xin chào buổi chiều'], [20, 'Xin chào buổi tối']
];
for (const [hour, text] of cases) {
  app.setHour(hour);
  app.opts.callback({credential: fakeJwt(claims)});
  assert.equal(app.ids['finquery-google-greeting'].textContent, text + ', Nguyễn Văn A!');
  assert.equal(app.ids['finquery-google-identity'].hidden, false);
  assert.equal(app.ids['finquery-google-signin'].hidden, true);
  assert.ok(app.storage.has('finquery_google_profile_v1'));
}
app.ids['finquery-google-signout'].listeners.click();
assert.equal(app.disabled(), true);
assert.equal(app.ids['finquery-google-identity'].hidden, true);
assert.equal(app.ids['finquery-google-signin'].hidden, false);
assert.equal(app.storage.has('finquery_google_profile_v1'), false);
app.opts.callback({credential: fakeJwt({...claims, aud: 'other-client.apps.googleusercontent.com'})});
assert.equal(app.ids['finquery-google-identity'].hidden, true);
app.opts.callback({credential: fakeJwt({...claims, exp: 100})});
assert.equal(app.ids['finquery-google-identity'].hidden, true);

console.log('PASS: Google web Client ID, opt-in GIS button, greetings, logout, invalid claims, bundle wiring.');
