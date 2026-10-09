'use strict';
const t=require('node:test');
const assert=require('node:assert/strict');
const security=require('../lib/ssi-session');
const oauth=require('../lib/ssi-oauth');
const transport=require('../lib/ssi-transport');
const handler=require('./ssi-mcp.js');
const ENV={FINQUERY_SSI_ENABLED:'1',FINQUERY_SSI_COOKIE_KEY:'a'.repeat(64),FINQUERY_SSI_SITE_ORIGIN:'https://finquery-example.vercel.app'};
t('SSI disabled unless all server-only gates are configured',()=>{
 assert.equal(security.enabled({}),false);
 assert.equal(security.enabled({...ENV,FINQUERY_SSI_ENABLED:'0'}),false);
 assert.equal(security.enabled({...ENV,FINQUERY_SSI_COOKIE_KEY:'unsafe'}),false);
 assert.equal(security.enabled(ENV),true);
 assert.equal(security.strictOrigin(ENV),'https://finquery-example.vercel.app');
 assert.equal(security.incomingMatches({headers:{host:'evil.example'}},ENV),false);
});
t('AES-GCM cookies roundtrip and fail closed when tampered',()=>{
 const value={token:'test',clientId:'client',issuedAt:Date.now()};
 const sealed=security.encode(value,ENV);
 assert.deepEqual(security.decode(sealed,ENV),value);
 assert.equal(security.decode(sealed.slice(0,-4)+'ABCD',ENV),null);
 assert.equal(security.decode('',ENV),null);
});
t('client PKCE uses valid verifier challenge',()=>{
 const verifier=oauth.verifier(),digest=oauth.challenge(verifier);
 assert.match(verifier,/^[A-Za-z0-9_-]{43}$/);
 assert.match(digest,/^[A-Za-z0-9_-]{43}$/);
});
t('SSI only permits approved tools and strict Vietnamese symbols',()=>{
 assert.equal(transport.normTicker(' fpt '),'FPT');
 assert.throws(()=>transport.normTicker('FPT;'));
 assert.throws(()=>transport.normTicker('^VNINDEX'));
 assert.deepEqual(Object.keys(transport.TOOLS).sort(),['events','indicators','news','peers','profile']);
});
t('SSI rows normalize ratios without inventing percent units',()=>{
 const raw={status:'ok',data:{indicators:[{year_report:2025,length_report:5,roe:'0.14',revenue:'1200000000000'},{year_report:2026,length_report:2,roe:'0.134',pe:'11.2',revenue:'3200000000000'}]}};
 const out=transport.compact('indicators',raw,'SSI');
 assert.equal(out[0].year,2026);
 assert.equal(out[0].period,2);
 assert.equal(out[0].roe,0.134);
 assert.equal(out[0].revenue,3200000000000);
});
t('FPT news never mixes FRT or copies full embedded HTML',()=>{
 const raw={status:'ok',data:{news:[{news_id:'1',symbol:'FPT',title:'FPT',short_content:'<p>Thật</p>',public_date:'01/10/2026'},{news_id:'2',symbol:'FRT',title:'FPT Retail'},{news_id:'1',symbol:'FPT',title:'trùng'}]}};
 const out=transport.compact('news',raw,'FPT');
 assert.equal(out.length,1);assert.equal(out[0].summary,'Thật');
});
t('tool result parses structured content and SSE events',()=>{
 const d={status:'ok',data:{indicators:[]}};
 assert.deepEqual(transport.unwrap({content:[{type:'text',text:JSON.stringify(d)}]}),d);
 assert.deepEqual(transport.parseSseEvent('event: message\ndata: {"jsonrpc":"2.0","id":9,"result":{}}',9),{jsonrpc:'2.0',id:9,result:{}});
});
t('MCP flow initializes before listing/calling exact discovered tool',async()=>{
 const before=global.fetch,called=[];
 let index=0;
 const replies=[
  {jsonrpc:'2.0',id:1,result:{protocolVersion:'2025-03-26',capabilities:{}}},
  {jsonrpc:'2.0',id:2,result:{tools:[{name:transport.TOOLS.indicators.name,inputSchema:{required:['symbol'],properties:{symbol:{},orderBy:{},order:{},pageSize:{}}}}]}},
  {jsonrpc:'2.0',id:3,result:{content:[{type:'text',text:JSON.stringify({status:'ok',data:{indicators:[{year_report:2026,length_report:2,roe:'0.13'}]}})}]}}
 ];
 global.fetch=async(url,options)=>{
  const req=JSON.parse(options.body);called.push(req.method);
  if(req.method==='notifications/initialized')return{ok:true,headers:{get:()=>null}};
  const result=replies[index++];
  assert.equal(req.id,result.id);
  return{ok:true,headers:{get:x=>x==='content-type'?'application/json':null},text:async()=>JSON.stringify(result)};
 };
 try{
  const result=await transport.research('SSI','indicators','fake_token');
  assert.equal(result.status,'ok');assert.equal(result.rows[0].roe,0.13);
  assert.deepEqual(called,['initialize','notifications/initialized','tools/list','tools/call']);
 }finally{global.fetch=before;}
});
t('tool call refuses schema with unrecognized required fields',async()=>{
 const before=global.fetch,called=[];
 let index=0;const replies=[
  {jsonrpc:'2.0',id:1,result:{protocolVersion:'2025-03-26'}},
  {jsonrpc:'2.0',id:2,result:{tools:[{name:transport.TOOLS.news.name,inputSchema:{required:['symbol','mystery'],properties:{symbol:{},mystery:{}}}}]}}
 ];
 global.fetch=async(_url,options)=>{
  const req=JSON.parse(options.body);called.push(req.method);
  if(req.method==='notifications/initialized')return{ok:true,headers:{get:()=>null}};
  return{ok:true,headers:{get:x=>x==='content-type'?'application/json':null},text:async()=>JSON.stringify(replies[index++])};
 };
 try{const v=await transport.research('FPT','news','fake_token');assert.equal(v.status,'schema_unverified');assert.equal(called.includes('tools/call'),false);}finally{global.fetch=before;}
});
t('unauthenticated/disabled endpoint never attempts SSI network calls',async()=>{
 const old={...process.env};delete process.env.FINQUERY_SSI_ENABLED;
 const req={method:'GET',headers:{host:'finquery-example.vercel.app'},query:{symbol:'FPT',kind:'indicators'}};
 const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(x){this.result=x;}};
 try{await handler(req,res);assert.equal(res.code,503);assert.equal(res.result.status,'disabled');}finally{process.env=old;}
});

t('SSI OAuth reports disallowed callback domain explicitly',async()=>{
 const oauth=require('../lib/ssi-oauth.js'),before=global.fetch;
 global.fetch=async()=>({
  ok:false,status:400,
  text:async()=>JSON.stringify({error:'invalid_redirect_uri',error_description:'redirect_uri domain is not allowed'})
 });
 try{
  await assert.rejects(oauth.clientId('https://finquery-ssi-stage-ngochailuong.vercel.app/api/ssi-callback',{registration_endpoint:'https://mcp.ssi.com.vn/oauth/register'}),{code:'ssi_redirect_domain_not_allowed'});
 }finally{global.fetch=before;}
});
t('SSI login sends blocked-domain users to readable staging page',async()=>{
 const auth=require('./ssi-auth.js'),oauth=require('../lib/ssi-oauth.js'),oldDiscovery=oauth.discovery,oldClient=oauth.clientId;
 const names=['FINQUERY_SSI_ENABLED','FINQUERY_SSI_COOKIE_KEY','FINQUERY_SSI_SITE_ORIGIN'],env=Object.fromEntries(names.map(k=>[k,process.env[k]]));
 Object.assign(process.env,{FINQUERY_SSI_ENABLED:'1',FINQUERY_SSI_COOKIE_KEY:'b'.repeat(64),FINQUERY_SSI_SITE_ORIGIN:'https://finquery-ssi-stage-ngochailuong.vercel.app'});
 oauth.discovery=async()=>({issuer:'https://mcp.ssi.com.vn'});
 oauth.clientId=async()=>{const err=new Error('blocked');err.code='ssi_redirect_domain_not_allowed';throw err;};
 const result={};const res={setHeader(){},redirect(status,url){result.status=status;result.url=url;}};
 try{
  await auth({method:'GET',headers:{host:'finquery-ssi-stage-ngochailuong.vercel.app'},query:{op:'start'}},res);
  assert.equal(result.status,302);
  assert.equal(result.url,'https://finquery-ssi-stage-ngochailuong.vercel.app/?ssi=domain_not_allowed');
 }finally{
  oauth.discovery=oldDiscovery;oauth.clientId=oldClient;
  for(const k of names){if(env[k]===undefined)delete process.env[k];else process.env[k]=env[k];}
 }
});
