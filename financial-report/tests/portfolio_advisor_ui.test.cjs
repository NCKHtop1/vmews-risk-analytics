'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
const html=read('frontend/index.html'),ui=read('frontend/portfolio-advisor-ui.js'),
 css=read('frontend/portfolio-advisor.css'),portfolio=read('frontend/portfolio-intelligence.js'),
 bundle=read('scripts/build_cdn.py'),flow=fs.readFileSync(path.resolve(root,'../.github/workflows/portfolio-advisor-eod.yml'),'utf8');
test('Advisor is a genuine integrated and keyboard-reachable Portfolio tab',()=>{
 assert.match(html,/data-portfolio-tab="advisor"/);
 assert.match(html,/id="portfolio-tab-advisor"/);
 assert.match(portfolio,/\'overview\',\'plan\',\'advisor\',\'rotation\',\'history\'/);
 assert.match(portfolio,/finquery:portfolio-advisor-open/);
 assert.match(html,/src="portfolio-advisor-ui.js"/);
 assert.match(html,/href="portfolio-advisor.css"/);
});
test('Native and bundled pages have script and responsive stylesheet',()=>{
 assert.match(bundle,/portfolio-advisor-ui\.js/);
 assert.match(bundle,/portfolio-advisor\.css/);
 assert.match(css,/@media\(max-width:720px\)/);
 assert.match(html,/id="advisor-profile"/);
 assert.match(html,/id="advisor-frequency"/);
 assert.match(html,/id="advisor-results"/);
});
test('Research UI never contains an order path or changes the ledger',()=>{
 assert.match(ui,/orderExecutionEnabled!==false/);
 assert.match(ui,/personalizedRecommendation!==false/);
 assert.match(ui,/RESEARCH_ONLY/);
 assert.match(ui,/portfolio-advisor-'\+state\.frequency\+'\.json/);
 assert.match(ui,/state\.data=null;void load\(true\)/);
 assert.match(flow,/portfolio-advisor-\$\{cadence\}\.json/);
 assert.match(ui,/Chưa đủ điều kiện/);
 assert.doesNotMatch(ui,/fetch\(['"]\/api\/user\/portfolio/);
 assert.doesNotMatch(ui,/\/api\/order|\/api\/trade|\/api\/broker/);
 assert.match(ui,/window\.FinPortfolio\?\.context/);
 assert.match(ui,/textContent/);
});
test('Publisher is server scheduled, fail-closed, public only',()=>{
 assert.match(flow,/45 10 \* \* 1-5/);
 assert.match(flow,/portfolio-advisor\.json/);
 assert.match(flow,/RESEARCH_ONLY/);
 assert.match(flow,/orderExecutionEnabled/);
 assert.doesNotMatch(flow,/finquery_users|finquery_portfolio_transactions|DATABASE_URL|NEON_DATABASE_URL/);
});
