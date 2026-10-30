'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=(p)=>fs.readFileSync(path.join(root,p),'utf8');
const html=read('frontend/index.html');
const css=read('frontend/responsive-system.css');
const nav=read('frontend/responsive-navigation.js');
const build=read('scripts/build_cdn.py');

test('one navigable mobile menu uses the original seven platform links',()=>{
 assert.equal((html.match(/id="finquery-nav-toggle"/g)||[]).length,1);
 assert.equal((html.match(/id="finquery-primary-navigation"/g)||[]).length,1);
 assert.match(html,/aria-controls="finquery-primary-navigation"/);
 assert.match(html,/aria-label="Điều hướng nền tảng"/);
 assert.equal((html.match(/data-platform-view=/g)||[]).length,3);
 for(const hash of ['#market','#risk-monitor','#strategy-builder','#research-ai','#macro','#overview','#report-detail'])
  assert.match(html,new RegExp('href="'+hash+'"'));
 assert.match(nav,/aria-expanded/);
 assert.match(nav,/Escape/);
 assert.match(nav,/pointerdown/);
 assert.match(nav,/nav\.addEventListener\('click'/);
 assert.match(css,/\.header\.finquery-nav-open nav/);
 assert.match(css,/\.site-locked #finquery-nav-toggle/);
});

test('advanced chart controls keep original IDs and are accessible without occupying two full rows',()=>{
 for(const id of ['chart-interval','chart-type','chart-period','chart-focus-latest','chart-fit',
                    'chart-zoom-in','chart-zoom-out','chart-marker-toggle','chart-fullscreen'])
  assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
 assert.match(html,/id="chart-advanced-tools" class="chart-advanced-controls"/);
 assert.match(html,/aria-label="Tùy chọn biểu đồ"/);
 assert.match(html,/aria-hidden="true">⋯/);
 assert.equal(html.includes('<summary>Công cụ khác</summary>'),false);
 assert.match(css,/position:absolute/);
 assert.match(nav,/chartTools\.open=false/);
 assert.match(css,/#chart-advanced-tools:not\(\[open\]\)/);
 assert.match(css,/\.chart-advanced-actions/);
});

test('responsive system covers all major FinQuery workspaces without hiding document overflow',()=>{
 for(const key of ['.workspace','.market-grid','.strategy-builder-grid','.risk-main-grid',
                   '.table-container','#market-primary-tabs','.chart-advanced-controls',
                   '.research-ai.ai-drawer','.finquery-nav-open'])
  assert.ok(css.includes(key),key);
 assert.match(css,/@media\(max-width:390px\)/);
 assert.match(css,/@media\(max-width:850px\)/);
 assert.match(css,/@media\(max-width:1050px\)/);
 assert.match(css,/@media\(min-width:851px\) and \(max-width:1430px\)/);
 assert.doesNotMatch(css,/(?:html|body)\s*\{[^{}]*overflow-x\s*:\s*(?:hidden|clip)/i);
 assert.match(css,/\.risk-stock-table-wrap/);
 assert.match(css,/overscroll-behavior-x:contain/);
});

test('single-file production build inlines responsive style and its JS exactly once',()=>{
 assert.match(html,/href="responsive-system\.css"/);
 assert.match(html,/src="responsive-navigation\.js"/);
 assert.match(build,/responsive-system\.css'\)\.read_text\(\)/);
 assert.match(build,/responsive-navigation\.js'\)\.read_text\(\)/);
 assert.match(build,/'google-signin\.js','responsive-navigation\.js'/);
});
