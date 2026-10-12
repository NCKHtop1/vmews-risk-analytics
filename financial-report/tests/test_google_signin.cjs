'use strict';
/* Google Identity Services display-only component regression checks.
 * No interactive Google account is required. OAuth registration has a
 * separate network probe. No JWT grants authorization in this static page.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'frontend/google-signin.js'), 'utf8');
const build = fs.readFileSync(path.join(root, 'scripts/build_cdn.py'), 'utf8');
const clientId = html.match(/<meta name="finquery-google-client-id" content="([^"]+)"/)?.[1];
const validId = '216957728290-6h80djpq7ouk2cmd5jgjr08j6233voes.apps.googleusercontent.com';

assert.equal(clientId, validId, 'Must use the exact Google Cloud OAuth client ID');
assert.match(clientId, /^[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com$/);
assert.ok(!html.includes('5jgir08j'), 'Old invalid_client typo must not return');
assert.ok(!html.includes('client-secret'), 'Never expose a client secret');
assert.match(html, /defer src="google-signin.js"/);
assert.match(build, /front \/ 'google-signin\.js'/);

for (const id of [
  'finquery-google-account', 'finquery-google-signin',
  'finquery-google-identity', 'finquery-google-greeting',
  'finquery-google-avatar', 'finquery-google-avatar-fallback',
  'finquery-google-status'
]) {
  assert.equal((html.match(new RegExp('id="' + id + '"', 'g')) || []).length, 1,
    'Missing or duplicate Google element: ' + id);
}
for (const id of [
  'finquery-user-menu','finquery-user-trigger','finquery-user-menu-close',
  'finquery-google-panel-avatar','finquery-google-shortname',
  'finquery-nickname','finquery-nickname-save','finquery-favorite-form',
  'finquery-favorite-input','finquery-google-signout'
]) assert.ok(!html.includes('id="' + id + '"'), 'Unwanted dropdown setting: ' + id);

const mini = html.slice(html.indexOf('<div class="finquery-google-account"'), html.indexOf('<form id="site-unlock-form"'));
assert.match(mini, /finquery-google-greeting/);
assert.match(mini, /finquery-google-avatar/);
assert.doesNotMatch(mini, /<button|<section|<form|<svg/);
assert.doesNotMatch(js, /readPreferences|prefsKey|favoriteUrl|finquery-user-menu|nicknameSave/);
assert.match(html, /@media\(max-width:700px\)\{\.finquery-google-account/);

if (process.env.FINQUERY_VERIFY_BUNDLE === '1') {
  const bundle = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const bundleId = bundle.match(/<meta name="finquery-google-client-id" content="([^"]+)"/)?.[1];
  assert.equal(bundleId, validId);
  assert.ok(bundle.includes('id="finquery-google-avatar"'));
  assert.ok(!bundle.includes('id="finquery-user-menu"'));
  assert.ok(!bundle.includes('id="finquery-nickname"'));
  assert.ok(!bundle.includes('id="finquery-favorite-form"'));
  assert.ok(bundle.includes('function safePicture('));
  assert.ok(bundle.includes('"symbol":"MBB"'), 'MBB financial report preserved');
  assert.ok(bundle.includes('finquery-visitor-total'), 'Visitor count preserved');
  assert.ok(bundle.includes('data-platform-view="risk"'), 'Risk module preserved');
}

const storage = new Map();
function token(payload) {
  const enc = data => Buffer.from(JSON.stringify(data)).toString('base64url');
  return enc({alg:'RS256',typ:'JWT'}) + '.' + enc(payload) + '.test-signature';
}
function element(id) {
  return {
    id, textContent:'', hidden:true, src:'', listeners:{}, attributes:{},
    setAttribute(key,v){this.attributes[key]=String(v);},
    removeAttribute(key){delete this.attributes[key];if(key==='src')this.src='';}
  };
}
function createApp() {
  let hour=20, now=Date.now(), init, rendered=false, intervalFn;
  const ids={};
  for (const id of [
    'finquery-google-account','finquery-google-signin',
    'finquery-google-identity','finquery-google-greeting',
    'finquery-google-avatar','finquery-google-avatar-fallback',
    'finquery-google-status'
  ]) ids[id]=element(id);
  const google={accounts:{id:{
    initialize(opts){init=opts;},
    renderButton(div,opts){
      assert.equal(div,ids['finquery-google-signin']);
      assert.equal(opts.locale,'vi');
      rendered=true;
    }
  }}};
  const document={
    querySelector:selector=>selector==='meta[name="finquery-google-client-id"]'?
      {getAttribute:attr=>attr==='content'?clientId:null}:null,
    getElementById:id=>ids[id]||null,
    createElement:tag=>{
      assert.equal(tag,'script');
      return {src:'',async:false,defer:false};
    },
    head:{appendChild(script){
      assert.match(script.src,/^https:\/\/accounts\.google\.com\/gsi\/client/);
      script.onload();
    }}
  };
  class TestDate extends Date {
    static now(){return now;}
    getHours(){return hour;}
  }
  const env={document,window:{google},google,Date:TestDate,URL,Array,Number,
    TextDecoder,Uint8Array,
    atob:str=>Buffer.from(str,'base64').toString('binary'),
    localStorage:{
      getItem:key=>storage.get(key)||null,
      setItem:(key,value)=>storage.set(key,value),
      removeItem:key=>storage.delete(key)
    },
    setInterval:fn=>{intervalFn=fn;return 1;}
  };
  vm.runInNewContext(js,env,{filename:'google-signin.js',timeout:2500});
  return {
    ids,login:payload=>init.callback({credential:token(payload)}),
    get rendered(){return rendered;},
    hour:v=>{hour=v;},advance:ms=>{now+=ms;},tick:()=>intervalFn()
  };
}

const app=createApp();
const node=name=>app.ids['finquery-google-'+name];
assert.equal(app.rendered,true);
assert.equal(node('account').hidden,false);
assert.equal(node('identity').hidden,true);
const now=Date.now();
const claims={
  aud:clientId,iss:'https://accounts.google.com',sub:'google-user-001',
  exp:Math.floor(now/1000)+1800,
  name:'Hailn',picture:'https://lh3.googleusercontent.com/a/test-avatar'
};
for (const [hour,part] of [
  [7,'Xin chào buổi sáng'],[12,'Xin chào buổi trưa'],
  [15,'Xin chào buổi chiều'],[20,'Xin chào buổi tối']
]) {
  app.hour(hour);
  app.login(claims);
  assert.equal(node('greeting').textContent,part+', Hailn!');
  assert.equal(node('identity').hidden,false);
  assert.equal(node('signin').hidden,true);
}
assert.equal(node('avatar').src,claims.picture);
assert.equal(node('avatar').hidden,true,'Fallback shown until Google image loads');
assert.equal(node('avatar-fallback').textContent,'H');
assert.equal(node('avatar-fallback').hidden,false);
node('avatar').onload();
assert.equal(node('avatar').hidden,false);
assert.equal(node('avatar-fallback').hidden,true);
node('avatar').onerror();
assert.equal(node('avatar').hidden,true);
assert.equal(node('avatar-fallback').hidden,false);
const cache=storage.get('finquery_google_profile_v1');
assert.ok(cache.includes('"name":"Hailn"'));
assert.ok(cache.includes('"picture":'));
assert.ok(!cache.includes('test-signature'),'No Google JWT persisted');

// Old per-user nicknames must not affect the greeting.
storage.set('finquery_google_preferences_v1_google-user-001',
  JSON.stringify({nickname:'Unused Nickname',favorites:['MBB']}));
app.login(claims);
assert.equal(node('greeting').textContent,'Xin chào buổi tối, Hailn!');
// Changing to a different Google account changes the displayed identity.
app.login({...claims,sub:'google-user-002',name:'Người dùng B',
  picture:'https://fake.example/unsafe-image'});
assert.equal(node('greeting').textContent,'Xin chào buổi tối, Người dùng B!');
assert.equal(node('avatar').src,'','Non-Google avatar URL must be blocked');
assert.equal(node('avatar-fallback').textContent,'N');
const cachedApp=createApp();
assert.equal(cachedApp.ids['finquery-google-greeting'].textContent,
  'Xin chào buổi tối, Người dùng B!');
assert.equal(cachedApp.ids['finquery-google-identity'].hidden,false);

// Reject invalid or expired tokens without replacing current on-screen profile.
app.login({...claims,aud:'unregistered-client.apps.googleusercontent.com'});
assert.equal(node('greeting').textContent,'Xin chào buổi tối, Người dùng B!');
app.login({...claims,exp:100});
assert.equal(node('greeting').textContent,'Xin chào buổi tối, Người dùng B!');

// Expire the in-memory profile after the documented one-hour maximum.
app.advance(3600001);
app.tick();
assert.equal(node('identity').hidden,true);
assert.equal(node('signin').hidden,false);
assert.equal(storage.has('finquery_google_profile_v1'),false);
assert.equal(storage.has('finquery_google_preferences_v1_google-user-001'),true,
  'Simplifying the UI must not erase unrelated existing preferences');

console.log('PASS: greeting + avatar only, no menu/settings, Google OAuth ID, 4 dayparts, photo/fallback, local session cache, safe photos, expiry and standalone build parity.');
