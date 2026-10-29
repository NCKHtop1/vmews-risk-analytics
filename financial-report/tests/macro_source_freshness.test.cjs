'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const fs=require('node:fs'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../frontend/macro.js'),'utf8');
function harness(){
 const nodes=new Map(),renders=[];
 const get=id=>{
  if(!nodes.has(id))nodes.set(id,{
   value:'',textContent:'',innerHTML:'',open:false,hidden:false,disabled:false,
   addEventListener(name,fn){this['on'+name]=fn},
   closest(){return null}
  });
  return nodes.get(id);
 };
 const macroStamp='2026-10-29T08:10:00Z',esgStamp='2026-10-29T08:12:00Z';
 const macro=(date)=>({checkedAt:date,status:'ok',datasets:{pmi:{
  title:'PMI',status:'ok',columns:['Cột 1','T7 2026','T8 2026','T9 2026'],
  rows:[{'Cột 1':'PMI','T7 2026':52,'T8 2026':53,'T9 2026':51}]
 }},sources:[]});
 const esg=(date)=>({checkedAt:date,status:'ok',companies:{
  FPT:{symbol:'FPT',canonicalMetrics:[{
   metricId:'women_workforce_pct',label:'Tỷ lệ nữ',year:2025,value:37.7,
   sourceUrl:'https://example.com/fpt.pdf'
  }],documents:[{url:'https://example.com/fpt.pdf'}]},
  HPG:{symbol:'HPG',canonicalMetrics:[],documents:[{url:'https://example.com/hpg.pdf'}]}
 }});
 const fetch=async url=>{
  const raw=String(url).includes('raw.githubusercontent.com');
  const payload=String(url).includes('company-esg.json')?
   esg(raw?'2026-10-29T07:10:00Z':esgStamp):
   macro(raw?macroStamp:'2026-10-29T07:15:00Z');
  return{ok:true,json:async()=>payload};
 };
 const window={
  addEventListener(){},setInterval(){},FinMacroDashboard:{
   corporateRows:(data,symbol)=>data?.companies?.[symbol]?.canonicalMetrics||[],
   render:(data,esg,symbol)=>renders.push({checkedAt:data.checkedAt,
    esgCheckedAt:esg?.checkedAt,symbol})
  }
 };
 const document={documentElement:{dataset:{hosting:'pages'}},hidden:false,
  getElementById:get,addEventListener(){}};
 const location={href:'https://nckhtop1.github.io/vmews-risk-analytics/financial-report/index.html',
  origin:'https://nckhtop1.github.io'};
 const ctx={window,document,location,URL,AbortSignal,Intl,Date,Number,String,
  console,fetch,CustomEvent:class{constructor(type,init){this.type=type;this.detail=init?.detail;}}};
 vm.runInNewContext(code,ctx,{filename:'macro.js'});
 return{window,get,renders};
}
test('freshness arbitration selects newest valid Macro and ESG independently',async()=>{
 const app=harness();
 for(let i=0;i<10;i++)await Promise.resolve();
 const context=app.window.FinMacro.context();
 assert(context,'initial Macro load must populate context');
 assert.equal(context.checkedAt,'2026-10-29T08:10:00Z',
   'newer GitHub Raw macro must outrank stale fast mirror');
 assert.equal(app.renders.at(-1).esgCheckedAt,'2026-10-29T08:12:00Z',
   'newer verified ESG mirror must be accepted if Raw is old');
 assert.equal(context.corporateEsg.symbol,'FPT','default stock should render useful ESG data');
 assert.match(app.get('macro-company-ticker').innerHTML,/HPG/);
 assert.match(app.get('macro-company-ticker').innerHTML,/FPT/);
});
test('ESG picker changes only the company panel, without changing market ticker',async()=>{
 const app=harness();for(let i=0;i<10;i++)await Promise.resolve();
 const picker=app.get('macro-company-ticker');
 assert.equal(typeof picker.onchange,'function');
 picker.onchange({target:{value:'HPG'}});
 assert.equal(app.window.FinMacro.context().corporateEsg.symbol,'HPG');
 assert.equal(app.renders.at(-1).symbol,'HPG');
});
