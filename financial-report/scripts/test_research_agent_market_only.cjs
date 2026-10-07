'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

const source=fs.readFileSync(path.resolve(__dirname,'../frontend/research-agent.js'),'utf8');
let active='FPT';
const quotes={
 FPT:{symbol:'FPT',price:100000,reference:99000,changePct:1.01,sourceTime:'2026-10-07T07:30:00Z',status:'ok'},
 AAA:{symbol:'AAA',price:7420,reference:7350,changePct:.95,sourceTime:'2026-10-07T07:30:00Z',status:'ok'}
};
const sandbox={
 console,
 performance:{now:()=>1},
 sessionStorage:{setItem(){}},
 FinancialMarket:{
  select(symbol){active=String(symbol).toUpperCase();return true;},
  context(){return{symbol:active,quote:null,driver:null,technical:null,market:{},news:[],marketNews:[],newsCheckedAt:null};},
  alertContext(){return{symbol:active,companies:[{symbol:'FPT',name:'FPT Corporation',tier:'CORE'},{symbol:'AAA',name:'AAA',tier:'LIQUID'}],quotes,watch:[]};}
 },
 FinancialReportContext:{
  raw(){return{symbol:'FPT',annual:{symbol:'FPT',periods:['2025'],sections:[]}};},
  resolveSymbol(value){return /\bFPT\b/i.test(String(value||''))?'FPT':'';},
  companies(){return[{symbol:'FPT',name:'FPT Corporation',exchange:'HOSE'}];},
  async select(symbol){return String(symbol).toUpperCase()==='FPT'?this.raw():null;}
 },
 FinTechnicalScanner:{context:()=>null},
 FinStrategyBuilder:{context:()=>null},
 FinStrategyIntelligence:{context:()=>null},
 FinInsights:{context:()=>null},
 FinMacro:{context:()=>null}
};
sandbox.globalThis=sandbox;
vm.createContext(sandbox);
vm.runInContext(source,sandbox,{filename:'research-agent.js'});

(async()=>{
 const agent=sandbox.FinResearchAgent;
 assert.ok(agent);
 const technical=await agent.run('Phan tich ky thuat AAA hien tai');
 assert.equal(technical.audit.symbol.activeSymbol,'AAA');
 assert.equal(technical.context.agent.evidence.market.symbol,'AAA');
 assert.equal(technical.context.agent.evidence.market.quote.symbol,'AAA');
 assert.equal(technical.context.agent.evidence.market.quote.price,7420);

 const memo=await agent.run('Phan tich chuyen sau AAA theo ky thuat va rui ro hien tai');
 assert.equal(memo.audit.intent,'memo');
 assert.ok(memo.audit.plan.includes('market'));
 assert.ok(memo.audit.plan.includes('scanner'));
 assert.ok(memo.audit.plan.includes('strategy'));
 assert.equal(memo.audit.symbol.activeSymbol,'AAA');
 assert.equal(memo.context.agent.evidence.market.symbol,'AAA');
 assert.equal(memo.context.agent.evidence.market.quote.price,7420);
 assert.equal(Object.prototype.hasOwnProperty.call(memo.context.agent.evidence,'financial'),false);
 assert.ok(memo.context.agent.validation.warnings.some(x=>/BCTC/i.test(x)));

 console.log(JSON.stringify({status:'ok',intent:memo.audit.intent,plan:memo.audit.plan,active:active,market:memo.context.agent.evidence.market.symbol,price:memo.context.agent.evidence.market.quote.price,financialLeaked:false},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
