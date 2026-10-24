'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {Writable}=require('node:stream');
const Module=require('node:module');

process.env.DATABASE_URL='postgresql://test:unused@localhost/finquery_qa';
process.env.FINQUERY_SESSION_PEPPER='qa-only-workspace-secret-at-least-32-bytes';
process.env.FINQUERY_GOOGLE_CLIENT_ID='qa-public-client-id';

let currentUser={id:'11111111-1111-4111-8111-111111111111', email:'user.one@example.com',
  full_name:'Example User',avatar_url:'',role:'user',status:'active',
  session_id:'22222222-2222-4222-8222-222222222222'};
const db=new Map();
function selectRows(sql,args) {
  if(sql.includes('FROM public.finquery_sessions'))return [currentUser];
  if(sql.includes('FROM public.finquery_user_workspaces')){
    const row=db.get(args[0]);
    return row?[{...row}]:[];
  }
  if(sql.includes('INSERT INTO public.finquery_user_workspaces')){
    const [id,watch,strategies,settings,expected]=args;
    const prior=db.get(id);
    if(prior && Number(prior.revision)!==Number(expected))return [];
    const item={watchlist:JSON.parse(watch),strategies:JSON.parse(strategies),
      settings:JSON.parse(settings),revision:prior?prior.revision+1:1,
      updated_at:'2026-10-24T06:00:00.000Z'};
    db.set(id,item);return [{...item}];
  }
  throw new Error('SQL not covered by mock: '+sql.slice(0,80));
}
const native=Module._load;
Module._load=function(name){
  if(name==='@neondatabase/serverless')return {neon:()=>({query:async(sql,args=[])=>selectRows(sql,args)})};
  return native.apply(this,arguments);
};
const handler=require('../api/index.js');
Module._load=native;

function response(){
  const chunks=[];
  const w=new Writable({write(chunk,_encoding,done){chunks.push(Buffer.from(chunk));done();}});
  w.statusCode=200;w.headersSent=false;w.headers={};
  w.writeHead=function(code,headers){this.statusCode=code;this.headersSent=true;this.headers=headers||{};return this};
  w.getJson=()=>JSON.parse(Buffer.concat(chunks).toString('utf8'));
  return w;
}
async function call(method,cookie=true,body={},origin='https://finquery.info.vn'){
  const req={method,url:'/api/user/workspace',query:{route:'api/user/workspace'},
    headers:{host:'finquery.info.vn',origin,...(cookie?{cookie:'finquery_session='+'a'.repeat(43)}:{})},
    body};
  const res=response();
  await handler(req,res);
  return res;
}
function payload(revision,watchlist=['MBB']){
  return {revision,watchlist,strategies:[
    {id:'s1',name:'RSI break',scope:'LIVE',join:'AND',alert:true,
    conditions:[{id:'c1',left:'rsi14',op:'cross_up',rightType:'value',rightValue:50}],
    lastMatches:[],createdAt:'2026-10-24T00:00:00+00:00'}],
    settings:{newsMode:'company'}};
}
test('Reject anonymous reads and writes without a valid session',async()=>{
  assert.equal((await call('GET',false)).statusCode,401);
  assert.equal((await call('PUT',false,payload(0))).statusCode,401);
});
test('New user GET yields empty revision zero',async()=>{
  const r=await call('GET');
  assert.equal(r.statusCode,200);
  assert.deepEqual(r.getJson().workspace.watchlist,[]);
  assert.equal(r.getJson().workspace.revision,0);
});
test('Save strategy and watchlist atomically for signed-in user',async()=>{
  const r=await call('PUT',true,payload(0));
  assert.equal(r.statusCode,200);
  assert.equal(r.getJson().workspace.revision,1);
  assert.deepEqual((await call('GET')).getJson().workspace.watchlist,['MBB']);
});
test('One Google user cannot read another account workspace',async()=>{
  const previous=currentUser;
  currentUser={...currentUser,id:'33333333-3333-4333-8333-333333333333',
    email:'user.two@example.com'};
  try{
    const r=await call('GET');
    assert.equal(r.statusCode,200);
    assert.equal(r.getJson().workspace.revision,0);
  }finally{currentUser=previous;}
});
test('Reject stale revision to prevent silent cross-device overwrite',async()=>{
  const r=await call('PUT',true,payload(0,['FPT']));
  assert.equal(r.statusCode,409);
  assert.equal(r.getJson().code,'REVISION_CONFLICT');
  assert.equal(r.getJson().workspace.revision,1);
  assert.deepEqual(r.getJson().workspace.watchlist,['MBB']);
});
test('Reject write from a different origin and missing write controls',async()=>{
  const r=await call('PUT',true,payload(1),'https://wrong.example');
  assert.equal(r.statusCode,403);
  const x=await call('PUT',true,{revision:1,watchlist:['BAD!'],strategies:[]});
  assert.equal(x.statusCode,400);
});
test('Support unary scanner rules and update revision monotonically',async()=>{
  const p=payload(1,['VCB']);
  p.strategies[0].conditions=[{id:'c1',left:'rsi14',op:'rising',rightType:'value'}];
  const r=await call('PUT',true,p);
  assert.equal(r.statusCode,200);
  assert.equal(r.getJson().workspace.revision,2);
  assert.deepEqual(r.getJson().workspace.watchlist,['VCB']);
});
test('Reject unauthorized method and overlong strategy payload',async()=>{
  assert.equal((await call('DELETE')).statusCode,405);
  const p=payload(2);
  p.strategies[0].name='x'.repeat(101);
  assert.equal((await call('PUT',true,p)).statusCode,400);
});
