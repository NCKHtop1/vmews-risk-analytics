const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market-data.js'),'utf8');
function setup(fetch){const ctx={window:{},document:{documentElement:{dataset:{hosting:'pages'}},dispatchEvent(){}},location:{href:'https://example.test/financial-report/'},fetch,URL,Date,AbortController,AbortSignal,DOMException,CustomEvent:function(type,init){this.type=type;this.detail=init?.detail;},setTimeout,clearTimeout,Promise};vm.runInNewContext(code,ctx);return ctx.window.FinMarketData;}
const bundle=(minutes,price=100)=>({checkedAt:new Date(Date.now()-minutes*60000).toISOString(),quotes:{ACB:{price}}});
test('publisher update wins over successful stale Pages response',async()=>{const api=setup(async url=>({ok:true,json:async()=>bundle(url.includes('raw.githubusercontent')?1:90,url.includes('raw.githubusercontent')?110:100)}));assert.equal((await api.get('quotes.json')).quotes.ACB.price,110);});
test('future publisher snapshot cannot displace valid Pages data',async()=>{const api=setup(async url=>({ok:true,json:async()=>bundle(url.includes('raw.githubusercontent')?-600:10)}));assert.ok(Date.parse((await api.get('quotes.json')).checkedAt)<Date.now());});
test('failed publisher uses valid same-origin snapshot',async()=>{const api=setup(async url=>{if(url.includes('raw.githubusercontent'))throw Error('offline');return{ok:true,json:async()=>bundle(20)};});assert.ok((await api.get('quotes.json')).quotes.ACB);});
test('unavailable sources fail explicitly',async()=>{const api=setup(async()=>({ok:false,status:503}));await assert.rejects(api.get('quotes.json'),/No valid/);});
test('slow mirror cannot block a valid publisher snapshot',async()=>{
 const api=setup(async url=>{
  if(url.includes('raw.githubusercontent'))return{ok:true,json:async()=>bundle(1,111)};
  await new Promise(resolve=>setTimeout(resolve,1500));
  return{ok:true,json:async()=>bundle(2,109)};
 });
 const started=Date.now(),result=await api.get('quotes.json',{timeout:5000,hedgeMs:50});
 assert.equal(result.quotes.ACB.price,111);
 assert.ok(Date.now()-started<1000,'valid publisher response was blocked by the slow mirror');
});
test('fast primary avoids duplicate mirror download',async()=>{
 let calls=0;
 const api=setup(async url=>{calls++;return{ok:true,json:async()=>bundle(url.includes('raw.githubusercontent')?1:2,url.includes('raw.githubusercontent')?105:115)};});
 assert.equal((await api.get('quotes.json',{hedgeMs:100})).quotes.ACB.price,105);
 await new Promise(resolve=>setTimeout(resolve,130));
 assert.equal(calls,1);
});
test('slow primary launches mirror hedge and returns the first valid snapshot',async()=>{
 const api=setup(async url=>{
  if(url.includes('raw.githubusercontent')){await new Promise(resolve=>setTimeout(resolve,250));return{ok:true,json:async()=>bundle(1,105)};}
  await new Promise(resolve=>setTimeout(resolve,10));return{ok:true,json:async()=>bundle(2,115)};
 });
 assert.equal((await api.get('quotes.json',{hedgeMs:30})).quotes.ACB.price,115);
});
test('future quote cannot poison merges; valid quote repairs prior future value',()=>{const api=setup(()=>{}),now=new Date().toISOString(),future=new Date(Date.now()+86400000).toISOString();const target={ACB:{price:999,sourceTime:future}};api.mergeQuotes(target,{ACB:{price:100,sourceTime:now}});assert.equal(target.ACB.price,100);api.mergeQuotes(target,{ACB:{price:999,sourceTime:future}});assert.equal(target.ACB.price,100);api.mergeQuotes(target,{ACB:{price:90,sourceTime:new Date(Date.now()-86400000).toISOString()}});assert.equal(target.ACB.price,100);});
test('atomic market bundle only commits one aligned source generation',async()=>{
 const t=new Date(Date.now()-60000).toISOString();
 const payload=file=>file==='quotes.json'?{checkedAt:t,latestSourceTime:t,quotes:{ACB:{price:100,sourceTime:t}}}:{checkedAt:t,sourceTime:t,status:'ok',symbols:{ACB:{}} ,items:[]};
 const api=setup(async url=>{const file=String(url).split('/').pop().split('?')[0];return{ok:true,json:async()=>payload(file)};});
 const bundle=await api.getAlignedBundle({hedgeMs:0});
 assert.equal(bundle.sourceTime,t);
 api.commitBundle(bundle);
 assert.equal(api.currentBundle().sourceTime,t);
});
test('atomic market bundle rejects mixed source generations and keeps prior commit',async()=>{
 const old=new Date(Date.now()-120000).toISOString(),fresh=new Date(Date.now()-60000).toISOString();
 let mixed=false;
 const api=setup(async url=>{const file=String(url).split('/').pop().split('?')[0],t=mixed&&file==='strategy-indicators.json'?old:fresh;const data=file==='quotes.json'?{checkedAt:t,latestSourceTime:t,quotes:{ACB:{price:100,sourceTime:t}}}:{checkedAt:t,sourceTime:t,status:'ok',symbols:{ACB:{}},items:[]};return{ok:true,json:async()=>data};});
 const first=await api.getAlignedBundle({hedgeMs:0});api.commitBundle(first);mixed=true;
 await assert.rejects(api.getAlignedBundle({hedgeMs:0}),/not aligned/);
 assert.equal(api.currentBundle().sourceTime,fresh);
});
test('a renderer exception releases refresh lock and the next refresh succeeds',async()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 const refresh=source.slice(source.indexOf('async function refresh(){'),source.indexOf('window.FinancialMarket='));
 const button={},status={},state={quotes:{},companies:[],coreCompanies:[],symbol:'ACB',refreshing:false};let calls=0,broken=true;
 const atomic={sourceTime:'2026-10-06T07:45:00Z',quotes:{checkedAt:'2026-10-06T07:45:01Z',quotes:{}}};
 const marketData={getAlignedBundle:async()=>{calls++;return atomic;},commitBundle:x=>x,currentBundle:()=>atomic,mergeQuotes(){}};
 const ctx={state,LIVE_FALLBACK_API:'',$:id=>id==='market-refresh'?button:status,get:async()=>{calls++;return{};},Date,Promise,console:{error(){}},newsStale:()=>false,quoteStale:()=>true,quoteAgeMinutes:()=>5,quoteNeedsFallback:()=>false,quoteNeedsCloseCatch:()=>false,marketSessionActive:()=>false,manageQuoteRetry:()=>{},showQuote:()=>{if(broken)throw Error('render failed');},board(){},news(){},CustomEvent:function(type,init){this.type=type;this.detail=init?.detail;},document:{dispatchEvent(){}},chartController:{loading:true},window:{FinMarketData:marketData,FinTechnicalScanner:{},FinStrategyBuilder:{},FinQueryAI:{sync(){}}}};
 vm.runInNewContext(refresh+';this.run=refresh',ctx);
 await ctx.run();assert.equal(state.refreshing,false);assert.equal(button.disabled,false);
 broken=false;await ctx.run();assert.equal(calls,8);assert.equal(state.initialized,true);assert.equal(state.refreshing,false);
});

test('intraday freshness policy fails over before a quote is declared stale',()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 assert.match(source,/quoteNeedsFallback[\s\S]*18\*60\*1000/);
 assert.match(source,/quoteStale[\s\S]*25\*60\*1000/);
 assert.match(source,/finquery:market-refresh/);
});
test('published snapshot mode disables burst quote retries when live fallback is unavailable',()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 assert.match(source,/quoteRetryTimer:null,quoteRetryAttempt:0/);
 assert.match(source,/if\(hasLive\|\|!state\.symbol\|\|!marketSessionActive\(\)\|\|!LIVE_FALLBACK_API\)/);
 assert.doesNotMatch(source,/const delays=\[1200,3000,7000\]/);
 assert.match(source,/manageQuoteRetry\(Boolean\(currentQuoteLive\)\)/);
 assert.match(source,/manageQuoteRetry\(false\)/);
});
test('live risk publisher loads market calibration before enforcing V2 validation',()=>{
 const live=fs.readFileSync(require('node:path').join(__dirname,'../scripts/live_session_publisher.sh'),'utf8');
 assert.match(live,/market_cal=load\('market-risk-calibration\.json'\)/);
 assert.match(live,/market_cal\.get\('status'\)/);
 assert.match(live,/FINQUERY-RISK-RULES-2\.0/);
});

test('close catch keeps strict intraday freshness but accepts official 14:45 close',()=>{
 const live=fs.readFileSync(require('node:path').join(__dirname,'../scripts/live_session_publisher.sh'),'utf8');
 const workflow=fs.readFileSync(require('node:path').join(__dirname,'../../.github/workflows/market-price-live.yml'),'utf8');
 assert.match(live,/MAX_AGE_MINUTES="\$\{MARKET_MAX_QUOTE_AGE_MINUTES:-18\}"/);
 assert.match(live,/CLOSE_CATCH_MAX_AGE_MINUTES="\$\{MARKET_CLOSE_CATCH_MAX_AGE_MINUTES:-30\}"/);
 assert.match(live,/local_min.*vn_minutes/);
 assert.match(live,/local_min" -ge 885.*local_min" -le 905/);
 assert.match(live,/MARKET_MAX_QUOTE_AGE_MINUTES="\$current_max_age"/);
 assert.match(live,/validate_snapshot "\$current_max_age"/);
 assert.match(workflow,/MARKET_MAX_QUOTE_AGE_MINUTES: '18'/);
 assert.match(workflow,/MARKET_CLOSE_CATCH_MAX_AGE_MINUTES: '30'/);
});
test('after-hours code pushes persist repaired derived market snapshots',()=>{
 const workflow=fs.readFileSync(require('node:path').join(__dirname,'../../.github/workflows/market-price-live.yml'),'utf8');
 assert.match(workflow,/Persist repaired derived snapshots after code push/);
 assert.match(workflow,/github\.event_name == 'push' && steps\.session\.outputs\.run != 'true'/);
 assert.match(workflow,/refresh_market\.py --output "\$OUT\/market" --mode scanner/);
 assert.match(workflow,/scannerComparators/);
 assert.match(workflow,/strategyComparators/);
 assert.match(workflow,/git -C "\$OUT" push origin HEAD:refs\/heads\/financial-market-data/);
});

test('technical scanner rules remain unchanged and evidence is additive',()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../scripts/refresh_market.py'),'utf8');
 assert.match(source,/'macd_cross_up': 60/);
 assert.match(source,/'rsi_oversold': 28/);
 assert.match(source,/'volume_spike': 22/);
 const ui=fs.readFileSync(require('node:path').join(__dirname,'../frontend/technical-scanner.js'),'utf8');
 assert.match(ui,/Rule priority/);
 assert.match(ui,/EOD proxy T\+3/);
});
test('live technical UI does not mislabel evolving daily indicators as 15-minute bars',()=>{
 const html=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
 const scanner=fs.readFileSync(require('node:path').join(__dirname,'../frontend/technical-scanner.js'),'utf8');
 const source=fs.readFileSync(require('node:path').join(__dirname,'../scripts/refresh_market.py'),'utf8');
 assert.match(html,/Core \+ Liquid · Trong phiên/);
 assert.match(html,/Scanner cập nhật theo dữ liệu trong phiên/);
 assert.doesNotMatch(html,/Core \+ Liquid · 15P|snapshot live 15 phút|snapshot giá 15 phút/i);
 assert.doesNotMatch(app,/Cập nhật 15 phút\/lần|textContent='15P'|:'15P'/);
 assert.match(scanner,/Trong phiên/);
 assert.doesNotMatch(scanner,/· Live /);
 assert.match(source,/evolving current-session daily candle/);
});

test('Strategy Lab replaces visible Data Health and simple rule form',()=>{
 const build=fs.readFileSync(require('node:path').join(__dirname,'../scripts/build_cdn.py'),'utf8');
 const html=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 assert.match(build,/strategy-engine\.js/);assert.match(build,/alert-center\.js/);assert.doesNotMatch(build,/front \/ 'data-health\.js'/);
 assert.match(html,/id="strategy-builder"/);assert.doesNotMatch(html,/id="data-health"/);assert.doesNotMatch(html,/Cảnh báo chạy khi trang đang mở/);
});


test('stale intraday chart fails closed before technical signals are rendered',()=>{
 const chart=fs.readFileSync(require('node:path').join(__dirname,'../frontend/chart-engine.js'),'utf8');
 assert.match(chart,/staleIntraday=M\.intraday\(this\.tf\)/);
 assert.match(chart,/this\.dataConsistent=!staleIntraday/);
 assert.match(chart,/Nến phút chưa cập nhật phiên hôm nay/);
 assert.match(chart,/if\(!ctx\)\{this\.signalSnapshot=null;this\.signalEvents=\[\];this\.renderSignals\(\);return;\}/);
 assert.match(chart,/this\.consistency\(this\.lastMarketQuote\);this\.evaluateSignals\(false\)/);
});
test('retained quote cannot trigger burst refreshes when live fallback is disabled',()=>{
 const market=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 assert.match(market,/if\(hasLive\|\|!state\.symbol\|\|!marketSessionActive\(\)\|\|!LIVE_FALLBACK_API\)/);
 assert.doesNotMatch(market,/const delays=\[1200,3000,7000\]/);
});
test('retained quotes are visibly marked instead of presented as live',()=>{
 const market=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 assert.match(market,/q\.status==='retained'\|\|src\.day!==now\.day/);
 assert.match(market,/Bản gần nhất/);
 assert.match(market,/renderQuoteFreshness\(q\)/);
});
test('scanner watch states do not create directional bias and volume is contextual',()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../scripts/refresh_market.py'),'utf8');
 assert.match(source,/bullish = sum\(x\['direction'\] == 'bullish'/);
 assert.match(source,/bearish = sum\(x\['direction'\] == 'bearish'/);
 assert.match(source,/volume_direction = 'bullish'.*'bearish'.*'confirmation'/s);
 assert.doesNotMatch(source,/sum\(x\['direction'\] in \{'bullish', 'bullish_watch'\}/);
});
test('strategy lab reuses the committed aligned bundle and does not poll every minute',()=>{
 const alerts=fs.readFileSync(require('node:path').join(__dirname,'../frontend/alert-center.js'),'utf8');
 assert.match(alerts,/currentBundle\?\.\(\)\?\.strategy/);
 assert.match(alerts,/setInterval\(\(\)=>\{if\(!document\.hidden\)refreshSnapshot\(\);\},300000\)/);
 assert.doesNotMatch(alerts,/setInterval\(\(\)=>\{if\(!document\.hidden\)refreshSnapshot\(\);\},60000\)/);
 assert.doesNotMatch(alerts,/setTimeout\(\(\)=>\{if\(Date\.parse\(actual\|\|0\)>Date\.parse\(expected\|\|0\)\)window\.FinancialMarket\?\.refresh\?\.\(\);refreshSnapshot\(\);\},1200\)/);
});
test('scanner and risk reuse the committed aligned bundle instead of refetching it',()=>{
 const scanner=fs.readFileSync(require('node:path').join(__dirname,'../frontend/technical-scanner.js'),'utf8');
 const risk=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 assert.match(scanner,/currentBundle\?\.\(\),bundled=bundle\?\.scanner/);
 assert.match(scanner,/evidenceLoadedAt<3600000/);
 assert.match(risk,/currentBundle\?\.\(\)\?\.risk/);
 assert.match(risk,/bundled&&\(!expected\|\|String\(bundled\.sourceTime/);
});

test('large market universe is cached for one hour instead of refetched every market tick',()=>{
 const market=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 assert.match(market,/universeLoadedAt:0/);
 assert.match(market,/Date\.now\(\)-state\.universeLoadedAt>=3600000/);
 assert.match(market,/universeNeedsRefresh\?get\('universe\.json'\):Promise\.resolve\(state\.universe\)/);
});
test('heavy market modules poll on the five-minute publisher cadence',()=>{
 const market=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 const scanner=fs.readFileSync(require('node:path').join(__dirname,'../frontend/technical-scanner.js'),'utf8');
 const risk=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 assert.match(market,/setInterval\(\(\)=>\{if\(!document\.hidden\)refresh\(\);\},300000\)/);
 assert.match(scanner,/setInterval\(\(\)=>\{if\(state\.unlocked&&!document\.hidden\)load\(\);\},300000\)/);
 assert.match(risk,/setInterval\(\(\)=>\{if\(!\$\('risk-monitor'\)\?\.hidden&&!document\.hidden\)refresh\(\);\},300000\)/);
});

test('market quote subtitle is timestamp-only and legacy nearest-session title is removed',()=>{
 const market=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
 assert.match(market,/function quoteTime\(q\)\{if\(!q\)return'Chưa có';return date\(q\.sourceTime\|\|q\.collectedAt\);\}/);
 assert.doesNotMatch(market,/Vietcap.*quoteTime|Giá chốt phiên gần nhất|Cập nhật trong phiên khoảng 15 phút\/lần/);
 assert.doesNotMatch(app,/ĐÁNG XEM PHIÊN GẦN NHẤT/);
 assert.match(app,/label\.hidden=!invalidFuture&&priorSession/);
});


test('site access gate and contextual info controls are wired without changing feature modules',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
 const style=fs.readFileSync(require('node:path').join(__dirname,'../frontend/style.css'),'utf8');
 assert.match(index,/<body class="site-locked">/);
 assert.match(index,/id="site-unlock-form"/);
 assert.match(index,/id="site-access-code"[^>]+inputmode="numeric"/);
 assert.match(app,/SITE_ACCESS_HASH='0a0667865bc17f9d624bcf11088057bbab46336e7dae65f3d5366f4f7a18333e'/);
 assert.match(app,/sessionStorage\.setItem\('finquery-site-access','1'\)/);
 assert.match(style,/\.site-locked \.workspace/);
 assert.match(index,/data-info-key="volume-ratio"/);
 assert.match(index,/data-info-key="scanner-bias"/);
 assert.match(index,/data-info-key="technical-signals"/);
 assert.match(app,/≥ 1,5x:/);
 assert.match(app,/1,2–1,5x:/);
 assert.match(app,/1,05–1,2x:/);
 assert.match(app,/0,9–1,05x:/);
 assert.match(app,/&lt; 0,9x:/);
 assert.match(app,/không tự nói tiền đang vào hay ra/i);
 assert.match(app,/không có nghĩa là xác suất thắng cao/i);
});


test('context help is compact, plain-language and Strategy Lab has usage guide',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
 const style=fs.readFileSync(require('node:path').join(__dirname,'../frontend/style.css'),'utf8');
 const marketCss=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.css'),'utf8');
 assert.match(index,/class="signal-title-row"/);
 assert.match(index,/class="technical-scanner-title-row"/);
 assert.match(index,/data-info-key="strategy-builder"/);
 assert.match(index,/class="strategy-title-row"/);
 assert.doesNotMatch(app,/FinQuery không coi một chỉ báo riêng lẻ là đủ/);
 assert.match(app,/Xu hướng:<\/b> giá đang đi lên hay đi xuống/);
 assert.match(app,/Kéo hoặc bấm một chỉ báo/);
 assert.match(app,/Lưu strategy \+ alert/);
 assert.match(style,/width:16px;height:16px/);
 assert.match(marketCss,/technical-scanner-head \.term-info-button/);
});


test('full contextual-help audit covers site-specific terms without oversized info buttons',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
 const style=fs.readFileSync(require('node:path').join(__dirname,'../frontend/style.css'),'utf8');
 for(const key of ['risk-score','technical-signals','scanner-guide','scanner-bias','volume-ratio','strategy-builder','universe-tiers','market-driver','broker-consensus'])assert.match(index,new RegExp('data-info-key="'+key+'"'));
 assert.match(app,/Cách dùng Technical Scanner/);
 assert.match(app,/Core · Liquid · Discovery/);
 assert.match(app,/Động lực \/ hệ số/);
 assert.match(app,/Lấy giá mục tiêu gần nhất của từng CTCK/);
 assert.match(style,/button\.term-info-button\{[^}]*width:16px!important/);
});

test('news freshness relies on scheduler recovery and compact published snapshot without dead browser fallback',()=>{
 const market=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 const guard=fs.readFileSync(require('node:path').join(__dirname,'../../.github/workflows/market-realtime-guard.yml'),'utf8');
 const news=fs.readFileSync(require('node:path').join(__dirname,'../../.github/workflows/market-news-live.yml'),'utf8');
 assert.match(guard,/cron: '\*\/5 \* \* \* \*'/);
 assert.match(guard,/Refresh live HOSE Core \+ Liquid prices/);
 assert.match(guard,/Deploy VMEWS Pages/);
 assert.match(guard,/news-latest\.json/);
 assert.match(news,/market-realtime-guard\.yml/);
 assert.match(news,/cron: '7 \* \* \* \*'/);
 assert.match(news,/Maintain resilient news heartbeat/);
 assert.match(news,/sleep 900/);
 assert.match(news,/market\/news\.json market\/news-latest\.json/);
 assert.match(market,/const LIVE_FALLBACK_API=''/);
 assert.match(market,/get\('news-latest\.json'\)\.catch\(\(\)=>get\('news\.json'\)\)/);
 assert.doesNotMatch(market,/for\(let attempt=0;attempt<2;attempt\+\+\)/);
});


test('risk monitor is a separate Vietnamese production view and is bundled',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const risk=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 const build=fs.readFileSync(require('node:path').join(__dirname,'../scripts/build_cdn.py'),'utf8');
 assert.match(index,/data-platform-view="risk">Giám sát rủi ro/);
 assert.match(index,/id="risk-monitor"[^>]+hidden/);
 assert.doesNotMatch(index,/Năm thước đo chính/);
 assert.match(index,/id="risk-contributions"/);
 assert.match(index,/id="risk-coverage-inline"/);
 for(const jargon of ['Risk Monitor','Market Stress','Alert Engine','Contagion','Liquidity Stress','Volatility Stress'])assert.doesNotMatch(index,new RegExp(jargon,'i'));
 assert.doesNotMatch(risk,/🚨|⚠|🟢|🟡|🔴/);
 assert.match(build,/risk-monitor\.css/);
 assert.match(build,/risk-monitor\.js/);
});

test('risk monitor keeps universe scope in data without verbose header copy',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const risk=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 const engine=fs.readFileSync(require('node:path').join(__dirname,'../scripts/build_risk_monitor.cjs'),'utf8');
 assert.doesNotMatch(index,/Theo dõi mức căng thẳng hiện tại trên nhóm cổ phiếu HOSE Core \+ Liquid/);
 assert.doesNotMatch(risk,/Phạm vi trực tiếp: HOSE Core \+ Liquid/);
 assert.match(engine,/scope:'HOSE Core \+ Liquid có dữ liệu trực tiếp'/);
});


test('risk monitor v3 exposes fund chart and calibrated sector heatmap',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const risk=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 const css=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.css'),'utf8');
 const refresh=fs.readFileSync(require('node:path').join(__dirname,'../../.github/workflows/financial-market-refresh.yml'),'utf8');
 const live=fs.readFileSync(require('node:path').join(__dirname,'../scripts/live_session_publisher.sh'),'utf8');
 assert.match(index,/SO VỚI MỐC GẦN NHẤT/);
 assert.match(index,/id="risk-contributions"/);
 assert.match(index,/id="risk-breadth-strip"/);
 assert.match(index,/id="risk-alert-history"/);
 assert.match(index,/Heatmap nhóm ngành/);
 assert.doesNotMatch(index,/Heatmap nhóm ngành giảm/);
 assert.match(index,/id="risk-sector-detail"/);
 assert.match(index,/id="risk-sector-updated"/);
 assert.match(index,/id="risk-breadth-detail"/);
 assert.match(index,/id="risk-fund-chart"/);
 assert.match(index,/id="risk-fund-detail"/);
 assert.doesNotMatch(index,/id="risk-fund-rows"|risk-fund-table/);
 assert.match(index,/MỨC RỦI RO HIỆN TẠI · THANG 0–100/);
 assert.match(index,/data-info-key="risk-score"/);
 assert.doesNotMatch(index,/không nhấp nháy|nhấn nhẹ một lần|Heatmap cảnh báo trạng thái căng thẳng hiện tại|Màu của cột chỉ phản ánh|Điểm càng cao, dấu hiệu căng thẳng|Biểu đồ xếp theo số quỹ|Cách đọc điểm rủi ro|Kiểm tra bản mới mỗi phút/i);
 assert.doesNotMatch(index,/class="risk-page-kicker"/);
 assert.doesNotMatch(index,/Vietnam Equity Intelligence|Charts by TradingView Lightweight Charts/);
 assert.match(risk,/renderSectorDetail/);
 assert.match(risk,/risk-sector-heat-cell/);
 assert.match(risk,/const direction=change>0\.01\?'up':change<-0\.01\?'down':'flat'/);
 assert.match(risk,/risk-heat-'\+direction/);
 assert.match(index,/risk-heat-up/);
 assert.match(index,/risk-heat-down/);
 assert.match(risk,/renderBreadthDetail/);
 assert.match(risk,/renderFundDetail/);
 assert.match(risk,/risk-fund-bar/);
 assert.match(risk,/sectorCalibration/);
 assert.match(css,/risk-sector-heatmap/);
 assert.match(css,/risk-fund-chart/);
 assert.doesNotMatch(css,/riskAlertPulse|animation:riskAlertPulse/);
 assert.match(refresh,/build_sector_risk_calibration\.cjs/);
 assert.match(live,/build_sector_risk_calibration\.cjs/);
 assert.match(refresh,/Persist aligned market risk history/);
});


test('risk navigation badge and compact dashboard copy stay focused',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const risk=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 assert.match(index,/Số cảnh báo cần chú ý/);
 assert.match(index,/Giám sát thị trường chứng khoán Việt Nam/);
 assert.match(index,/data-platform-view="analysis">Giám sát thị trường/);
 assert.match(index,/data-platform-view="strategy">Strategy Lab/);
 assert.match(risk,/function updateNavBadge/);
 assert.match(risk,/filter\(x=>x\.alertActive===true\)/);
 assert.match(risk,/badge\.title=sectorCount\+' cảnh báo rủi ro ngành đang hoạt động'/);
 assert.doesNotMatch(risk,/const count=sectorCount\+fundCount/);
 assert.match(risk,/Mã thay đổi đáng chú ý/);
 assert.doesNotMatch(risk,/Mã vượt ngưỡng|Lượt thay đổi vượt ngưỡng/);
 assert.match(risk,/return'Bình thường\.'/);
 assert.doesNotMatch(risk,/Chưa thấy căng thẳng lan rộng trên toàn thị trường/);
 assert.doesNotMatch(risk,/Các thước đo chính đang ở vùng bình thường/);
 assert.match(risk,/aboveThreshold/);
 assert.match(risk,/Cập nhật gần nhất:/);
 assert.doesNotMatch(index,/snapshot phiên khoảng 5 phút|snapshot thị trường khoảng 5 phút|dữ liệu trong phiên khoảng 5 phút/i);
});


test('Pages rebuilds scanner offline and rejects collapsed live comparators',()=>{
 const pages=fs.readFileSync(require('node:path').join(__dirname,'../../.github/workflows/pages.yml'),'utf8');
 const source=fs.readFileSync(require('node:path').join(__dirname,'../scripts/refresh_market.py'),'utf8');
 assert.match(pages,/refresh_market\.py --output _market-data\/market --mode scanner/);
 assert.match(pages,/scanner_comparators/);
 assert.match(pages,/strategy_comparators/);
 assert.match(source,/def scanner\(out, companies\):/);
 assert.match(source,/'refreshEveryMinutes': 5/);
});

test('risk monitor cadence is enforced in code without UI narration',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const risk=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 const live=fs.readFileSync(require('node:path').join(__dirname,'../scripts/live_session_publisher.sh'),'utf8');
 assert.doesNotMatch(index,/Kiểm tra bản mới mỗi phút|5 phút\/lần/);
 assert.match(risk,/setInterval\(\(\)=>\{if\(!\$\('risk-monitor'\)\?\.hidden&&!document\.hidden\)refresh\(\);\},300000\)/);
 assert.match(live,/INTERVAL_SECONDS="\$\{MARKET_LOOP_SECONDS:-300\}"/);
});


test('Strategy Lab is a dedicated platform view instead of an accordion inside market analysis',()=>{
 const index=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
 const views=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 const collapse=fs.readFileSync(require('node:path').join(__dirname,'../frontend/section-collapse.js'),'utf8');
 assert.match(index,/id="strategy-builder" class="strategy-builder-section strategy-page"[^>]+hidden/);
 assert.match(index,/id="strategy-body" class="strategy-builder-body">/);
 assert.doesNotMatch(index,/id="strategy-toggle"|id="strategy-chevron"/);
 assert.match(views,/function showStrategy/);
 assert.match(views,/FinPlatformViews/);
 assert.doesNotMatch(collapse,/section:'strategy-builder'/);
});


test('direct Risk and Strategy Lab hashes reopen their dedicated views after unlock',()=>{
 const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
 const views=fs.readFileSync(require('node:path').join(__dirname,'../frontend/risk-monitor.js'),'utf8');
 assert.match(app,/location\.hash==='\#risk-monitor'.*openRisk/s);
 assert.match(app,/location\.hash==='\#strategy-builder'.*openStrategy/s);
 assert.match(views,/location\.hash==='\#strategy-builder'\)showStrategy\(false\)/);
});
