'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const fs=require('node:fs'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../forecast-final-v12.js'),'utf8');
const stamp=new Date().toISOString();
function fixture(){
 const symbols={},charts={};
 for(let i=0;i<100;i++){
  const symbol='S'+String(i).padStart(3,'0'),horizons={};
  for(let h=1;h<=5;h++)horizons[String(h)]={
   priceValidated:true,expectedPrice:100+h,q20Price:90+h,q80Price:110+h,
   targetDate:'2026-11-02',validationStatus:'PASS',
  };
  symbols[symbol]={symbol,exchange:'HOSE',close:100,date:'2026-10-28',horizons};
  charts[symbol]=Array.from({length:8},(_,k)=>({date:'2026-10-'+String(20+k).padStart(2,'0'),close:95+k,volume:1000}));
 }
 return{
  status:'PASS',generatedAt:stamp,asOf:'2026-10-28',
  universe:{available:100,expected:100},
  gates:{status:'PASS'},model:{promotion:{status:'PASS',directPriceHorizons:[1,2,3,4,5],preferredRankingHorizon:3}},
  dashboard:{asOf:'2026-10-28',generatedAt:stamp,symbols,charts},backtest:{horizons:{},cases:{}}
 };
}
function runtime(host,respond){
 const urls=[],window={addEventListener(){},dispatchEvent(){}},
  location={hostname:host,pathname:host==='nckhtop1.github.io'?'/vmews-risk-analytics/forecast-final.html':'/forecast-final.html',search:'',origin:'https://'+host,href:'https://'+host+'/forecast-final.html'},
  document={addEventListener(){},querySelector(){return null},hidden:false};
 const fetch=async(url,options)=>{urls.push(String(url));return await respond(String(url),options)};
 const ctx={window,document,location,fetch,URL,URLSearchParams,Date,Intl,
  AbortController,AbortSignal,DOMException,CustomEvent:class{constructor(type,init){this.type=type;this.detail=init?.detail}},
  console,setTimeout,clearTimeout,Promise};
 vm.runInNewContext(code,ctx,{filename:'forecast-final-v12.js'});
 return{window,urls};
}
const ok=data=>({ok:true,status:200,json:async()=>data});
test('FinQuery domain and localhost preview use verified VN100 instead of retired core',async()=>{
 const payload=fixture();
 for(const host of ['localhost','finquery.info.vn']){
  const app=runtime(host,async url=>url.includes('finquery-vn100-product.json')?ok(payload):{ok:false,status:404});
  const B=await app.window.__VMEWS_LOAD_BASE__();
  assert.equal(B.source,'VN100');
  assert.equal(Object.keys(B.dash.symbols).length,100);
  assert(app.urls[0].includes('/finquery-vn100-product.json'));
  assert(!app.urls.some(url=>url.includes('solution-ai-core-data/')));
  assert.equal(Object.values(B.dash.symbols).reduce((n,z)=>n+Object.keys(z.horizons).length,0),500);
  assert.equal((await app.window.__VMEWS_LOAD_LEADER_BASE__()).dash.asOf,'2026-10-28');
 }
});
test('independent public Pages retains its separate full-HOSE validated model',async()=>{
 const app=runtime('nckhtop1.github.io',async url=>{
  if(url.includes('/forecast-dashboard-v12.json'))return ok({asOf:'2026-10-28',promotion:{status:'PASS'}});
  if(url.includes('/phase-gates-v12.json'))return ok({status:'PASS'});
  return {ok:false,status:404};
 });
 const leader=await app.window.__VMEWS_LOAD_LEADER_BASE__();
 assert.equal(leader.gates.status,'PASS');
 assert(leader.dash.promotion.status==='PASS');
 assert(!app.urls.some(url=>url.includes('finquery-vn100-product.json')));
});
test('mirror recovers the VN100 product when GitHub Raw is temporarily unavailable',async()=>{
 const payload=fixture(),app=runtime('finquery.info.vn',async url=>
  url.includes('cdn.jsdelivr.net')?ok(payload):{ok:false,status:503});
 const B=await app.window.__VMEWS_LOAD_BASE__();
 assert.equal(B.source,'VN100');
 assert(app.urls.some(u=>u.includes('cdn.jsdelivr.net')));
});
test('verified full last-good forecast remains a fallback when compact bundle is missing',async()=>{
 const payload=fixture(),app=runtime('localhost',async url=>
  url.includes('/finquery-vn100-forecast.json')?ok(payload):{ok:false,status:404});
 assert.equal((await app.window.__VMEWS_LOAD_BASE__()).source,'VN100');
});
test('invalid product cannot show fabricated price predictions',async()=>{
 const payload=fixture();payload.dashboard.symbols.S001.horizons['4'].expectedPrice=0;
 const app=runtime('finquery.info.vn',async()=>ok(payload));
 await assert.rejects(app.window.__VMEWS_LOAD_BASE__(),/VN100/);
});
test('news refresh is independent from model availability',async()=>{
 const fresh={status:'ok',checkedAt:stamp,items:[{
  title:'Kết quả kinh doanh FPT',symbols:['FPT'],url:'https://example.com/verified',
  source:'Nguồn công khai',publishedAt:stamp
 }]};
 const app=runtime('localhost',async url=>
  url.includes('news-company-latest.json')?ok(fresh):{ok:false,status:404});
 const updated=await app.window.__VMEWS_REFRESH_COMPANY_NEWS__();
 assert.equal(updated,true);
 assert.equal(app.window.__VMEWS_LIVE_COMPANY_NEWS__.items.length,1);
 assert(app.urls.some(u=>u.includes('news-company-latest.json')));
});

test('market movement and financial reporting feeds refresh without blocking model',async()=>{
 const payloads={
  drivers:{generatedAt:stamp,symbols:{FPT:{symbol:'FPT',volumeRatio20:1.3,changePct:0.9}}},
  manifest:{universe:'VN100',updatedAt:stamp,coverage:{members:100},companies:[{symbol:'FPT',quarters:['2026-Q3']}]}
 };
 const app=runtime('finquery.info.vn',async url=>
  url.includes('drivers.json')?ok(payloads.drivers):
  url.includes('manifest.json')?ok(payloads.manifest):{ok:false,status:404});
 const complete=await app.window.__VMEWS_REFRESH_DATA_CONTEXT__();
 assert.equal(complete,true);
 assert(app.urls.some(u=>u.includes('drivers.json')));
 assert(app.urls.some(u=>u.includes('manifest.json')));
});

test('forecast view uses separate five-minute market and 30-minute model clocks',()=>{
 assert(code.includes('FORECAST_POLL_MS=120000,MARKET_QUOTE_POLL_MS=300000'));
 assert(code.includes('window.setInterval(()=>void refreshCore(),FORECAST_POLL_MS)'));
 assert(code.includes('window.setInterval(()=>{if(!document.hidden)void refreshLiveQuotes()},MARKET_QUOTE_POLL_MS)'));
 assert(code.includes('rerender(last.B,last.sym,last.B.dash.symbols[last.sym])'),
   'market refresh must update the visible price and chart, not only its cache');
 assert(code.includes('forecastAnchorBasis'));
 assert(code.includes('renderVN100Status('));
 assert(code.includes('VN100_STATUS_URL'));
});
test('lightweight forecast heartbeat detects updated thirty-minute publications',async()=>{
 const old=fixture();
 const status={status:'PASS',generatedAt:new Date(Date.now()+1000).toISOString(),symbols:100,horizons:500};
 const app=runtime('finquery.info.vn',async url=>
   url.includes('finquery-vn100-status.json')?ok(status):
   url.includes('finquery-vn100-product.json')?ok(old):
   {ok:false,status:404});
 const first=await app.window.__VMEWS_LOAD_BASE__();
 assert.equal(first.source,'VN100');
 const heartbeat=await app.window.__VMEWS_REFRESH_VN100_HEARTBEAT__();
 assert.equal(heartbeat.status,'PASS');
 assert.equal(heartbeat.horizons,500);
 const changed=await app.window.__VMEWS_REFRESH_CORE__();
 assert.equal(changed,false,'never swap a stale model when only the heartbeat moved');
 assert.equal((await app.window.__VMEWS_LOAD_BASE__()).dash.generatedAt,old.dashboard.generatedAt);
 assert(app.urls.some(url=>url.includes('finquery-vn100-status.json')));
});
test('five-minute price view rejects a stale source timestamp, accepts a new print',async()=>{
 const app=runtime('finquery.info.vn',async url=>{
   if(!url.includes('/market/quotes.json'))return{ok:false,status:404};
   return ok(app.snapshot);
 });
 app.window.__VMEWS_FRESHNESS__={
   quoteMode:()=> 'LIVE',
   expectedQuoteSession:()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',
     year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
 };
 const now=new Date();
 const iso=new Date(now.getTime()-13*60000).toISOString();
 app.snapshot={status:'ok',latestSourceTime:iso,coverage:100,expected:100,quotes:{
   FPT:{price:55000,status:'ok',sourceTime:iso}
 }};
 assert.equal(await app.window.__VMEWS_REFRESH_LIVE_QUOTES__(true),false);
 assert.equal(app.window.__VMEWS_LIVE_QUOTES__,undefined);
 const fresh=now.toISOString();
 app.snapshot={status:'ok',latestSourceTime:fresh,coverage:100,expected:100,quotes:{
   FPT:{price:56000,status:'ok',sourceTime:fresh}
 }};
 assert.equal(await app.window.__VMEWS_REFRESH_LIVE_QUOTES__(true),true);
 assert.equal(app.window.__VMEWS_LIVE_QUOTES__.quotes.FPT.price,56000);
 assert.equal(await app.window.__VMEWS_REFRESH_LIVE_QUOTES__(true),false,
   'duplicate publisher snapshot must not pretend to be a newly traded quote');
});
test('five-minute market publisher dispatches forecast from a verified publish',()=>{
 const publisher=fs.readFileSync(path.join(__dirname,'../financial-report/scripts/live_session_publisher.sh'),'utf8');
 assert(publisher.includes('maybe_dispatch_vn100_forecast'));
 assert(publisher.includes('gh workflow run finquery-vn100-forecast.yml'));
 assert(publisher.includes('remaining=$((INTERVAL_SECONDS - elapsed))'),
   'market cadence must be start-to-start five minutes, not five minutes plus processing time');
});
