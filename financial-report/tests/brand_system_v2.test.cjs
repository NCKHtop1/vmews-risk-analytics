'use strict';
/* Visual-only release guard for FinQuery Q-Data V2. Does not mock or change business logic. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const read=(name)=>fs.readFileSync(path.join(root,name),'utf8');
const main=read('financial-report/frontend/index.html');
const mainCss=read('financial-report/frontend/responsive-system.css');
const forecast=read('forecast-final.html');
const forecastCss=read('forecast-portfolio-v14.css');
const login=read('finquery-access/login.html');
const admin=read('finquery-access/admin.html');
const dataHub=read('financial-report/data-hub.html');
const mainBrand=mainCss.split('FinQuery Q-Data Design System V2 | 2026-11-02')[1];
const forecastBrand=forecastCss.split('FinQuery Forecast Q-Data V2 visual layer.')[1];
test('all five active FinQuery surfaces use Q-Data identity and icon',()=>{
 assert.ok(mainBrand&&forecastBrand,'missing shared brand layers');
 for(const [name,html,marker] of [
  ['main',main,'fq-rebrand-mark'],
  ['Forecast',forecast,'fq-forecast-mark'],
  ['Login',login,'fq-auth-mark'],
  ['Admin',admin,'fq-admin-symbol'],
  ['Data Hub',dataHub,'fq-data-mark']
 ])assert.ok(html.includes(marker),name+' missing branded Q mark');
 for(const [name,html] of [['main',main],['Forecast',forecast],['Login',login],['Admin',admin],['Data Hub',dataHub]])
  assert.match(html,/rel="icon"[^>]*favicon.svg/,name+' missing favicon');
 assert.match(main,/name="theme-color" content="#0A1B3D"/);
 assert.match(forecast,/class="fq-forecast-name">FinQuery/);
});
test('shared Q-Data tokens and per-module selectors are present',()=>{
 for(const hex of ['#0A1B3D','#245BFF','#22C7EB','#F3F6FA'])assert.ok(mainBrand.includes(hex)||mainCss.includes(hex),hex);
 for(const token of ['--fq-v2-navy','--fq-v2-blue','--fq-v2-cyan','--fq-v2-paper','--fq-v2-line'])assert.ok(mainBrand.includes(token),token);
 for(const selector of ['#market .finquery-workspace-tabs button.active','.strategy-builder-section','.portfolio-tabs button.active','.risk-summary-card','.macro-section','.research-ai.ai-drawer','#chart-terminal'])assert.ok(mainBrand.includes(selector),selector);
 assert.match(forecastBrand,/\.marketCommand/);
 assert.match(forecastBrand,/\.sectionNav a\.active/);
 assert.match(forecastBrand,/\.forecastCard\.active/);
 assert.match(forecastBrand,/\.filterChip\.active/);
});
test('positive/negative and risk semantic classes are not restyled by brand layer',()=>{
 assert.doesNotMatch(mainBrand,/(?:^|\n)\s*\.(?:price-up|price-down|risk-level|positive|negative|good|bad)\s*[,{]/);
 assert.doesNotMatch(forecastBrand,/(?:^|\n)\s*\.(?:positive|negative|good|bad|price-up|price-down)\s*[,{]/);
 assert.ok(forecastCss.includes('--green: #a8eb65;'),'original forecast positive color retained');
 assert.ok(forecastCss.includes('--red: #e17875;'),'original forecast negative color retained');
});
test('application routes, authentication, navigation, and existing scripts stay available',()=>{
 for(const id of ['finquery-primary-navigation','finquery-google-account','site-unlock-form','market','portfolio','risk-monitor','strategy-builder','macro','research-ai','overview','price-chart'])
  assert.ok(main.includes('id="'+id+'"'),id);
 for(const script of ['app.js','google-signin.js','market.js','chart-engine.js','risk-monitor.js','portfolio-intelligence.js','research-ai.js','responsive-navigation.js'])
  assert.ok(main.includes('src="'+script+'"'),script);
 for(const id of ['forecast','leaders','validation','events','backtest','modelBadge'])
  assert.ok(forecast.includes('id="'+id+'"'),id);
 for(const js of ['forecast-final-v12.js','forecast-polish-v12.js','forecast-portfolio-v14.js','solution-ai-v17.js'])
  assert.ok(forecast.includes(js),js);
 for(const id of ['signin','status','switch-account'])assert.ok(login.includes('id="'+id+'"'),id);
 for(const id of ['users','events','message'])assert.ok(admin.includes('id="'+id+'"'),id);
 assert.match(login,/<script src="\/login\.js" defer><\/script>/);
 assert.match(admin,/function signOut/);
 assert.match(dataHub,/http-equiv="refresh" content="0; url=\/financial-report\/index\.html#macro"/);
 assert.match(read('financial-report/scripts/build_cdn.py'),/responsive-system\.css/);
});
test('brand blue/white contrast meets WCAG AA; cyan is for accents only',()=>{
 const lum=(s)=>{
  const a=[0,2,4].map(i=>parseInt(s.substring(1+i,3+i),16)/255)
    .map(v=>v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4));
  return .2126*a[0]+.7152*a[1]+.0722*a[2];
 };
 const contrast=(a,b)=>{const x=lum(a),y=lum(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
 assert.ok(contrast('#245BFF','#FFFFFF')>=4.5);
 assert.ok(contrast('#0A1B3D','#FFFFFF')>=7);
 assert.ok(contrast('#0A1B3D','#22C7EB')>=4.5);
 assert.ok(contrast('#22C7EB','#FFFFFF')<4.5,'cyan should not be default text on white');
});
