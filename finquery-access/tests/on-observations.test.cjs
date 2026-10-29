'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {Writable}=require('node:stream');
const Module=require('node:module');
process.env.DATABASE_URL='postgresql://test:unused@localhost/finquery_qa';
process.env.FINQUERY_SESSION_PEPPER='qa-only-on-write-secret-at-least-32-bytes';
process.env.FINQUERY_GOOGLE_CLIENT_ID='qa-public-client-id';
const OWNER='ngochailuong7274@gmail.com';
const id='11111111-1111-4111-8111-111111111111';
let actingUser={id,email:OWNER,full_name:'Owner',role:'owner',status:'active'};
const observations=new Map();
const queries=[];
const native=Module._load;
Module._load=function(name){
 if(name==='@neondatabase/serverless')return {neon:()=>({query:async(sql,args=[])=>{
  queries.push({sql,args});
  if(sql.includes('FROM public.finquery_sessions'))return actingUser?[{...actingUser}]:[];
  if(sql.includes('FROM public.finquery_on_manual'))return [...observations].map(([date,value])=>({date,value})).sort((a,b)=>b.date.localeCompare(a.date));
  if(sql.includes('INSERT INTO public.finquery_on_manual')){observations.set(args[0],args[1]);return [];}
  if(sql.includes('INSERT INTO public.finquery_audit'))return [];
  throw new Error('Unexpected SQL: '+sql.slice(0,100));
 }})};
 return native.apply(this,arguments);
};
const handler=require('../api/index.js');
Module._load=native;
function response(){
 const chunks=[];
 const w=new Writable({write(b,_e,done){chunks.push(Buffer.from(b));done();}});
 w.headersSent=false;
 w.writeHead=function(status,headers){this.statusCode=status;this.headers=headers;this.headersSent=true;return this;};
 w.payload=()=>JSON.parse(Buffer.concat(chunks).toString('utf8'));
 return w;
}
async function call(method,{body={},loggedIn=true,origin='https://finquery.info.vn'}={}){
 const req={method,url:'/api/market/on-observations',query:{route:'api/market/on-observations'},
  headers:{host:'finquery.info.vn',origin,...(loggedIn?{cookie:'finquery_session='+'a'.repeat(43)}:{})},body};
 const res=response();
 await handler(req,res);
 return {status:res.statusCode,body:res.payload()};
}
test('owner can insert the real dated ON rate and update same-day value without duplicates',async()=>{
 actingUser={id,email:OWNER,role:'owner',status:'active'};
 const a=await call('POST',{body:{date:'2026-10-23',value:4.31}});
 assert.equal(a.status,200);
 const b=await call('POST',{body:{date:'2026-10-23',value:4.3333}});
 assert.equal(b.status,200);
 const read=await call('GET');
 assert.equal(read.status,200);
 assert.equal(read.body.canEdit,true);
 assert.deepEqual(read.body.observations,[{date:'2026-10-23',value:4.3333}]);
 assert.equal([...queries].filter(q=>q.sql.includes('INSERT INTO public.finquery_on_manual')).length,2);
});
test('ordinary authenticated accounts may read ON but cannot post or gain entry permissions',async()=>{
 actingUser={id:'22222222-2222-4222-8222-222222222222',email:'viewer@example.com',role:'user',status:'active'};
 assert.equal((await call('GET')).body.canEdit,false);
 assert.equal((await call('POST',{body:{date:'2026-10-22',value:3.8}})).status,403);
 actingUser={id:'33333333-3333-4333-8333-333333333333',email:OWNER,role:'admin',status:'active'};
 assert.equal((await call('POST',{body:{date:'2026-10-22',value:3.8}})).status,403);
});
test('anonymous and cross-origin writes are rejected',async()=>{
 actingUser={id,email:OWNER,role:'owner',status:'active'};
 assert.equal((await call('GET',{loggedIn:false})).status,401);
 assert.equal((await call('POST',{origin:'https://evil.example',body:{date:'2026-10-22',value:3.8}})).status,403);
});
test('invalid date, future date and out-of-range rate are rejected',async()=>{
 actingUser={id,email:OWNER,role:'owner',status:'active'};
 for(const body of [
  {date:'2099-01-01',value:4},
  {date:'2026-02-31',value:4},
  {date:'2026-10-21',value:25.0001},
  {date:'2026-10-21',value:-1},
  {date:'2026-10-21',value:3.12345},
 ]){
  assert.equal((await call('POST',{body})).status,400);
 }
});
