const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const script=fs.readFileSync(path.join(root,'frontend/alpha-radar.js'),'utf8');
const page=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
const build=fs.readFileSync(path.join(root,'scripts/build_cdn.py'),'utf8');
function harness(){
 const nodes={};
 const get=id=>nodes[id]||(nodes[id]={innerHTML:'',textContent:'',addEventListener(){}});
 const context={document:{getElementById:get,hidden:false,addEventListener(){}},
  window:{},localStorage:{getItem:()=>null,setItem(){}},Intl,Date,Number,String,URL,Math,Set,
  fetch:async()=>({ok:false}),AbortSignal,setInterval:()=>1,console};
 vm.createContext(context);vm.runInContext(script,context,{timeout:3000});
 return {api:context.window.FinAlphaRadar,get};
}
test('Alpha UI is formula-free and optional source is bundled',()=>{
 assert.match(page,/id="alpha-radar-panel"/);
 assert.match(page,/src="alpha-radar.js"/);
 assert.ok(build.includes("(front / 'alpha-radar.js').read_text()"));
 assert.doesNotMatch(script,/FINQUERY_ALPHA_RULES_JSON|conditions\]|macdSignal|nearPct|rule\.conditions/);
});
test('masked validated source renders statuses only',()=>{
 const {api,get}=harness();
 const d={schemaVersion:1,status:'verified',privateRulesIncluded:false,scope:'HOSE_CORE_LIQUID',
  sourceTime:new Date().toISOString(),alerts:[{id:'evt1',alphaId:'ALPHA_01',symbol:'MBB',stage:'confirmed',sourceTime:new Date().toISOString()}]};
 assert.equal(api._test.valid(d),true);
 api.setData(d);
 const html=get('alpha-radar-list').innerHTML;
 assert.match(html,/ALPHA_01/);
 assert.match(html,/MBB/);
 assert.match(html,/Đạt điều kiện/);
 assert.doesNotMatch(html,/formula|rsi14|MACD\s*Signal/);
 assert.equal(api._test.valid({...d,privateRulesIncluded:true}),false);
});
test('unauthorized or invalid Alpha identifiers are not rendered',()=>{
 const {api,get}=harness();
 const d={schemaVersion:1,status:'verified',privateRulesIncluded:false,scope:'HOSE_CORE_LIQUID',sourceTime:new Date().toISOString(),
  alerts:[{id:'bad',alphaId:'<script>alert(1)</script>',symbol:'MBB',stage:'confirmed',sourceTime:new Date().toISOString()}]};
 api.setData(d);
 assert.doesNotMatch(get('alpha-radar-list').innerHTML,/<script/);
});
