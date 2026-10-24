'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const Module = require('node:module');
const fs = require('node:fs');
const path = require('node:path');

process.env.FINQUERY_GOOGLE_CLIENT_ID = '216957728290-6h80djpq7ouk2cmd5jgjr08j6233voes.apps.googleusercontent.com';
process.env.FINQUERY_SESSION_PEPPER = 'qa-only-local-pepper-not-for-production-with-64-characters';
process.env.DATABASE_URL = 'postgresql://fake:fake@localhost/qa';
const users = new Map(), sessions = new Map(), audit = [];
const select = (a) => a ? [structuredClone(a)] : [];
const userView = u => ({id:u.id,email:u.email,google_sub:u.google_sub,full_name:u.full_name,avatar_url:u.avatar_url,role:u.role,status:u.status});
const saveUser = (u, email, sub, name, avatar) => {
  u.email=email;u.google_sub=sub;u.full_name=name;u.avatar_url=avatar;u.last_login_at=new Date().toISOString();
  return userView(u);
};
function query(sql,args=[]) {
  const s=sql.replace(/\s+/g,' ').trim().toUpperCase();
  if(s.startsWith('SELECT ID,EMAIL,GOOGLE_SUB FROM PUBLIC.FINQUERY_USERS WHERE GOOGLE_SUB=')) return select([...users.values()].find(u=>u.google_sub===args[0]));
  if(s.startsWith('SELECT ID,GOOGLE_SUB FROM PUBLIC.FINQUERY_USERS WHERE EMAIL=')) return select([...users.values()].find(u=>u.email===args[0]));
  if(s.startsWith('SELECT ID,EMAIL,FULL_NAME,AVATAR_URL,ROLE,STATUS FROM PUBLIC.FINQUERY_USERS WHERE GOOGLE_SUB=')) return select([...users.values()].find(u=>u.google_sub===args[0]));
  if(s.startsWith('UPDATE PUBLIC.FINQUERY_USERS SET EMAIL=')) {
    const u=[...users.values()].find(u=>u.google_sub===args[1]);
    return select(u?saveUser(u,args[0],args[1],args[2],args[3]):null);
  }
  if(s.startsWith('UPDATE PUBLIC.FINQUERY_USERS SET GOOGLE_SUB=')) {
    const u=[...users.values()].find(u=>u.email===args[0]&&!u.google_sub);
    return select(u?saveUser(u,args[0],args[1],args[2],args[3]):null);
  }
  if(s.startsWith('INSERT INTO PUBLIC.FINQUERY_USERS(')) {
    let u=[...users.values()].find(u=>u.google_sub===args[1]);
    if(!u){u={id:crypto.randomUUID(),role:'user',status:'active'};users.set(u.id,u);}
    if([...users.values()].some(other=>other.id!==u.id&&other.email===args[0])){const e=new Error('duplicate email');e.code='23505';throw e;}
    return [saveUser(u,args[0],args[1],args[2],args[3])];
  }
  if(s.startsWith('INSERT INTO PUBLIC.FINQUERY_SESSIONS')) {
    sessions.set(args[1],{id:crypto.randomUUID(),user_id:args[0],token_hash:args[1],expires_at:Date.now()+86400000,revoked_at:null});
    return [];
  }
  if(s.startsWith('SELECT U.ID,U.EMAIL,U.FULL_NAME')) {
    const se=sessions.get(args[0]),u=se&&users.get(se.user_id);
    if(!se||!u||se.revoked_at||se.expires_at<=Date.now())return [];
    return [Object.assign(userView(u),{session_id:se.id})];
  }
  if(s.startsWith('UPDATE PUBLIC.FINQUERY_SESSIONS SET REVOKED_AT=')) {
    for(const se of sessions.values())if((s.includes('TOKEN_HASH=')&&se.token_hash===args[0])||(s.includes('USER_ID=')&&se.user_id===args[0]))se.revoked_at=new Date().toISOString();
    return [];
  }
  if(s.startsWith('INSERT INTO PUBLIC.FINQUERY_AUDIT')) {audit.push({actor_email:args[0],action:args[1],target_email:args[2]});return [];}
  if(s.startsWith('SELECT ID,EMAIL,FULL_NAME,ROLE,STATUS,CREATED_AT')) return [...users.values()].map(userView);
  if(s.startsWith('SELECT ID,ACTOR_EMAIL,ACTION')) return audit.slice().reverse().map((a,i)=>({...a,id:i+1,created_at:new Date().toISOString()}));
  if(s.startsWith('SELECT ID,EMAIL,ROLE,STATUS FROM PUBLIC.FINQUERY_USERS WHERE ID=')) return select(users.get(args[0]));
  if(s.startsWith("UPDATE PUBLIC.FINQUERY_USERS SET STATUS='BLOCKED'")) {
    const u=users.get(args[0]);if(!u)return [];u.status='blocked';return [userView(u)];
  }
  if(s.startsWith("UPDATE PUBLIC.FINQUERY_USERS SET STATUS='ACTIVE'")) {
    const u=users.get(args[0]);if(!u)return [];u.status='active';return [userView(u)];
  }
  if(s.startsWith("UPDATE PUBLIC.FINQUERY_USERS SET ROLE=")) {
    const u=users.get(args[0]);if(!u)return [];u.role=args[1];return [userView(u)];
  }
  throw new Error('Unmocked SQL: '+s.slice(0,150));
}
const oldLoad=Module._load;
Module._load=function(request){if(request==='@neondatabase/serverless')return {neon:()=>query};return oldLoad.apply(this,arguments);};
const handler=require('../api/index.js');
Module._load=oldLoad;

const {publicKey,privateKey}=crypto.generateKeyPairSync('rsa',{modulusLength:2048});
const jwk=Object.assign(publicKey.export({format:'jwk'}),{kid:'finquery-qa-key',alg:'RS256',use:'sig'});
function jwt(sub,email) {
  const b64=x=>Buffer.from(JSON.stringify(x)).toString('base64url');
  const h=b64({alg:'RS256',kid:jwk.kid,typ:'JWT'});
  const p=b64({sub,email,email_verified:true,name:email.split('@')[0],iss:'https://accounts.google.com',
    aud:process.env.FINQUERY_GOOGLE_CLIENT_ID,exp:Math.floor(Date.now()/1000)+300,iat:Math.floor(Date.now()/1000)});
  return h+'.'+p+'.'+crypto.sign('RSA-SHA256',Buffer.from(h+'.'+p),privateKey).toString('base64url');
}
global.fetch=async url=>{
  if(String(url).startsWith('https://www.googleapis.com/oauth2/v3/certs'))
    return {ok:true,json:async()=>({keys:[jwk]})};
  if(String(url).startsWith('https://nckhtop1.github.io/'))
    return {ok:true,url:String(url),headers:{get:k=>k==='content-type'?'text/html':''},text:async()=>'<html><head></head><body><main>FinQuery</main></body></html>'};
  throw Error('Unexpected network request: '+url);
};
async function send(route,method='GET',body=null,cookie='',origin='https://finquery.info.vn') {
  const req={method,url:'/'+route,query:{route},body,headers:{host:'finquery.info.vn',origin,cookie}};
  const response={statusCode:200,headers:{},body:'',writeHead(status,headers){this.statusCode=status;Object.assign(this.headers,headers||{});return this;},end(value){this.body=value||'';return this;}};
  await handler(req,response);
  return {...response,json:()=>JSON.parse(response.body||'{}')};
}
function cookie(response){return String(response.headers['Set-Cookie']||'').split(';')[0];}
test('PandaStudy contract: one verified Google sub -> one persistent FinQuery account',async()=>{
  assert.equal((await send('api/auth/session')).json().authenticated,false);
  const invalid=await send('api/auth/google','POST',{credential:'invalid'},'');
  assert.equal(invalid.statusCode,401);
  const unauth=await send('financial-report/index.html');
  assert.equal(unauth.statusCode,307);
  assert.match(unauth.headers.Location,/login/);
  const a=await send('api/auth/google','POST',{credential:jwt('sub-100','alpha@example.com')});
  assert.equal(a.statusCode,200,a.body);
  assert.equal(a.json().user.status,'active');
  const aId=a.json().user.id;
  assert.ok(aId);
  const aAgain=await send('api/auth/google','POST',{credential:jwt('sub-100','alpha@example.com')},cookie(a));
  assert.equal(aAgain.json().user.id,aId);
  const renamed=await send('api/auth/google','POST',{credential:jwt('sub-100','alpha.renamed@example.com')},cookie(aAgain));
  assert.equal(renamed.json().user.id,aId,'Google email changes must not create new user');
  const b=await send('api/auth/google','POST',{credential:jwt('sub-200','beta@example.com')});
  assert.equal(b.statusCode,200,b.body);
  assert.notEqual(b.json().user.id,aId);
  assert.equal(users.size,2);
  assert.equal((await send('api/admin/users','GET',null,cookie(b))).statusCode,403);
  const content=await send('financial-report/index.html','GET',null,cookie(b));
  assert.equal(content.statusCode,200,content.body);
  assert.match(content.body,/finquery-nav-admin/);
  assert.match(content.body,/Quản trị hệ thống/);
  assert.match(content.body,/api\/auth\/session/);
});
test('Verified owner is linked once; admin stays server-authorized',async()=>{
  const owner={id:crypto.randomUUID(),email:'ngochailuong7274@gmail.com',google_sub:null,role:'owner',status:'active',full_name:'Owner',avatar_url:''};
  users.set(owner.id,owner);
  const login=await send('api/auth/google','POST',{credential:jwt('verified-owner-sub',owner.email)});
  assert.equal(login.statusCode,200,login.body);
  assert.equal(login.json().user.id,owner.id);
  assert.equal(login.json().user.role,'owner');
  assert.equal(users.get(owner.id).google_sub,'verified-owner-sub');
  const admin=await send('api/admin/users','GET',null,cookie(login));
  assert.equal(admin.statusCode,200,admin.body);
  assert.equal(admin.json().users.length,3);
  const beta=[...users.values()].find(u=>u.email==='beta@example.com');
  const denySelf=await send('api/admin/user','POST',{id:owner.id,action:'block'},cookie(login));
  assert.equal(denySelf.statusCode,403);
  const changed=await send('api/admin/user','POST',{id:beta.id,action:'block'},cookie(login));
  assert.equal(changed.statusCode,200,changed.body);
  assert.equal(users.get(beta.id).status,'blocked');
  const blocked=await send('api/auth/google','POST',{credential:jwt('sub-200','beta@example.com')});
  assert.equal(blocked.statusCode,403);
  assert.equal(blocked.json().code,'BLOCKED');
  assert.equal((await send('api/auth/google','POST',{credential:jwt('sub-300','intruder@example.com')},'','https://evil.example')).statusCode,403);
  const other=await send('api/auth/google','POST',{credential:jwt('different-google-sub',owner.email)});
  assert.equal(other.statusCode,409);
});
test('Static sign-in and admin UI reference backend-controlled roles',()=>{
  const root=path.resolve(__dirname,'..');
  const login=fs.readFileSync(path.join(root,'login.html'),'utf8');
  const loginJs=fs.readFileSync(path.join(root,'login.js'),'utf8');
  const admin=fs.readFileSync(path.join(root,'admin.html'),'utf8');
  const config=JSON.parse(fs.readFileSync(path.join(root,'vercel.json'),'utf8'));
  assert.match(login,/<script src="\/login.js"/);
  assert.match(loginJs,/\/api\/auth\/google/);
  assert.match(loginJs,/\/api\/auth\/session/);
  assert.match(admin,/\/api\/admin\/users/);
  assert.match(admin,/\/api\/admin\/user/);
  assert.ok(config.rewrites.some(r=>r.source==='/api/admin/:path'));
});
