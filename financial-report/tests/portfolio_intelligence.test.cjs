'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),repo=path.resolve(root,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const html=read('frontend/index.html'),client=read('frontend/portfolio-intelligence.js');
const styles=read('frontend/portfolio-intelligence.css'),router=read('frontend/risk-monitor.js'),app=read('frontend/app.js');
const bundle=read('scripts/build_cdn.py'),redirect=read('portfolio.html');
const server=fs.readFileSync(path.join(repo,'finquery-access/api/index.js'),'utf8');
const schema=fs.readFileSync(path.join(repo,'finquery-access/migrations/003_portfolio_ledger.sql'),'utf8');
test('Portfolio is a real platform tab, not a standalone dark navbar link',()=>{
 assert.match(html,/href="#portfolio" data-platform-view="portfolio"/);
 assert.match(html,/<section id="portfolio" class="portfolio-page"/);
 assert.doesNotMatch(html,/href="portfolio.html" class="finquery-portfolio-nav"/);
 for(const id of ['portfolio-nav','portfolio-pnl','portfolio-cash','portfolio-concentration','portfolio-holdings-body','portfolio-rotation-chart','portfolio-history-body','portfolio-entry-form'])
  assert.ok(html.includes('id="'+id+'"'),'Missing '+id);
});
test('shared navigation toggles Portfolio, Risk, Strategy and Analysis without reload',()=>{
 assert.match(router,/portfolio.hidden=view!=='portfolio'/);
 assert.match(router,/view==='portfolio'\?'#portfolio'/);
 assert.match(router,/openPortfolio/);
 assert.match(router,/if\(location.hash==='#portfolio'\)/);
 assert.match(app,/openPortfolio/);
});
test('native FinQuery layout is shared by source and production CDN build',()=>{
 assert.match(html,/href="portfolio-intelligence.css"/);
 assert.match(html,/src="portfolio-intelligence.js"/);
 assert.match(bundle,/portfolio-intelligence\.css/);
 assert.match(bundle,/portfolio-intelligence\.js/);
 assert.match(styles,/#e1e7ef/);
 assert.match(styles,/#portfolio/);
 assert.match(styles,/portfolio-page/);
});
test('old portfolio entry now redirects into the native workspace',()=>{
 assert.match(redirect,/index\.html#portfolio/);
 assert.match(redirect,/location\.replace/);
 assert.doesNotMatch(redirect,/không liên kết tài khoản môi giới/);
});
test('boilerplate banners are removed from the active Portfolio workspace',()=>{
 for(const s of [html,client,styles]){
  assert.doesNotMatch(s,/không phải khuyến nghị đầu tư|không liên kết tài khoản môi giới|chỉ là sổ giao dịch theo khai báo|giá cuối phiên có thể trễ/i);
 }
});
test('5-minute market portfolio scan with independent session-stamped sector data',()=>{
 assert.match(client,/FIVE_MIN=300000/);
 assert.match(client,/finquery:market-bundle/);
 assert.match(client,/FinMarketData\.get\('quotes\.json'/);
 assert.match(client,/FinMarketData\.get\('sector-rotation\.json'/);
 assert.match(client,/sourceTime/);
 assert.match(client,/SECTOR_RECHECK=3600000/);
});
test('quant numbers derive from actual ledger and no static demo portfolio',()=>{
 assert.match(client,/nav=missing\.length\?null:cash\+equity/);
 assert.match(client,/nav-external/);
 assert.match(client,/const concentration=Math\.max/);
 assert.match(client,/sectorAllocations/);
 assert.doesNotMatch(client,/35\/100|3000.*GMD|mockData|Math\.random\(/);
});
test('holdings connect to live Market, Scanner, Risk and Strategy views',()=>{
 assert.match(html,/data-portfolio-go="scanner"/);
 assert.match(html,/data-portfolio-go="risk"/);
 assert.match(html,/data-portfolio-go="strategy"/);
 assert.match(client,/window\.FinPlatformViews\?\.openAnalysis/);
 assert.match(client,/window\.FinancialMarket\?\.openChart/);
});
test('private API uses verified server-side session and request-origin protection',()=>{
 assert.match(server,/if \(route === 'api\/user\/portfolio'\) return userPortfolio\(req,res,user\)/);
 assert.match(server,/const user = await session\(req\)/);
 assert.match(server,/user\.id,key,kind,symbol,q,p,f,amount,date/);
 assert.match(server,/if\(!originAllowed\(req\)\)return json\(res,403/);
 assert.doesNotMatch(server,/data\.userId/);
});
test('ledger remains append-only and idempotent',()=>{
 assert.match(schema,/UNIQUE\(user_id,request_key\)/);
 assert.match(schema,/pg_advisory_xact_lock/);
 assert.match(schema,/FINQUERY_INSUFFICIENT_SHARES/);
 assert.doesNotMatch(schema,/DROP TABLE/);
});
test('frontend, router and app are valid JavaScript',()=>{
 new vm.Script(client);new vm.Script(router);new vm.Script(app);
});
