'use strict';const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
const html=read('frontend/index.html'),chart=read('frontend/portfolio-intelligence.js'),policy=read('frontend/portfolio-policy-ui.js'),help=read('frontend/portfolio-help.js'),css=read('frontend/portfolio-intelligence.css'),build=read('scripts/build_cdn.py');
test('help icons have working, accessible controller in both entrypoints',()=>{
 for(const key of ['templates','cash','drift','rebalance','rotation'])assert.match(html,new RegExp('data-portfolio-help="'+key+'"'));
 assert.match(html,/src="portfolio-help.js"/);assert.match(build, /front \/ 'portfolio-help.js'/);
 assert.match(help,/aria-expanded/);assert.match(help,/Escape/);assert.match(help,/textContent=data\[1\]/);
});
test('sector chart shows only dots by default and one trail on hover or selection',()=>{
 assert.match(chart,/trailVisible:false/);assert.match(chart,/state.hoverSector\|\|state.trailVisible/);
 assert.match(chart,/state.trailVisible=true/);assert.match(chart,/pointerover/);
 assert.match(chart,/pointerleave/);assert.match(chart,/data-portfolio-sector/);
 assert.match(chart,/fill="none"/);assert.match(chart,/opacity="\.67"/);
});
test('plan keeps actionable empty state and actual controls',()=>{
 assert.match(policy,/data-portfolio-empty-add/);assert.match(policy,/Chưa có dữ liệu danh mục/);
 assert.match(html,/for="portfolio-cash-target"/);assert.match(html,/for="portfolio-drift"/);
 assert.match(css,/portfolio-plan-empty/);assert.match(css,/@media\(max-width:720px\)/);
});
