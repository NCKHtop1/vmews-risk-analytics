const fs=require('fs');const vm=require('vm');const assert=require('assert');const {test}=require('node:test');
const code=fs.readFileSync(require('path').join(__dirname,'../frontend/research-agent.js'),'utf8');
const store=new Map(),now=new Date().toISOString(),old=new Date(Date.now()-60*60000).toISOString();let scannerTime=now,activeSymbol='FPT';
const ctx={console,Date,JSON,Math,Number,String,Object,Array,Set,Promise,performance:{now:()=>1},sessionStorage:{setItem:(k,v)=>store.set(k,v),getItem:k=>store.get(k)||null},FinancialReportContext:{raw:()=>({symbol:activeSymbol}),resolveSymbol:q=>/\bMBB\b/i.test(String(q||''))?'MBB':/\bFPT\b/i.test(String(q||''))?'FPT':'',select:async symbol=>{activeSymbol=String(symbol).toUpperCase();return{symbol:activeSymbol};}},FinancialMarket:{context:()=>({symbol:activeSymbol,quote:{symbol:activeSymbol,price:100000,reference:98000,changePct:2.04,sourceTime:now},driver:{relativeStrengthPct:1.1},technical:{snapshot:{title:'Trend'},sourceTime:now},newsCheckedAt:now,news:[{title:'FPT news',publishedAt:now,url:'https://example.com'}],marketNews:[{title:'Market news',publishedAt:now,url:'https://example.com/m'}]})},FinTechnicalScanner:{context:()=>({sourceTime:scannerTime,checkedAt:scannerTime,aligned:scannerTime===now,current:{symbol:activeSymbol,rsi14:55,volumeRatio20:1.2,signals:[]}})},FinStrategyBuilder:{context:()=>({strategy:{name:'x',conditions:[]},snapshot:{coverage:100},matches:[]})},FinInsights:{context:()=>({updatedAt:now,brokerResearch:[],corporateEvents:[],consensus:null})},FinMacro:{context:()=>({checkedAt:now,datasets:{pmi:{name:'PMI',rows:[{date:'2026-09',value:51}],numericColumns:['value']}}})}};
ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(code,ctx);
test('research agent plans tools and excludes stale scanner evidence',async()=>{
 assert.equal(ctx.FinResearchAgent.version,'FINQUERY_RESEARCH_AGENT_V1');
 assert.equal(ctx.FinResearchAgent.classify('ROE là gì?'),'concept');
 assert.equal(ctx.FinResearchAgent.classify('Phân tích sâu toàn diện mã này'),'memo');
 assert.equal(ctx.FinResearchAgent.resolveTargetSymbol('phân tích sâu MBB'),'MBB');
 const prepared=await ctx.FinResearchAgent.prepare('phân tích sâu MBB');
 assert.equal(prepared.beforeSymbol,'FPT');assert.equal(prepared.activeSymbol,'MBB');assert.equal(prepared.switched,true);
 activeSymbol='FPT';
 const p=ctx.FinResearchAgent.plan('Tìm mã MACD cắt lên, RSI trên 50 nhưng cơ bản không xấu');
 assert.equal(p.intent,'technical');assert(p.tools.includes('scanner')&&p.tools.includes('strategy')&&p.tools.includes('financial'));
 const first=await ctx.FinResearchAgent.run('Vì sao mã này tăng trong phiên hôm nay?',{baseContext:{technicalScanner:{current:{symbol:'FPT'}},localFinancialData:{annualSummary:{period:'2025'}}}});
 assert.equal(first.audit.iterations,2);assert.equal(first.audit.validation.status,'ok');assert.equal(first.context.agent.evidence.market.quote.symbol,'FPT');assert(store.has('finquery_research_agent_last'));
 scannerTime=old;
 const second=await ctx.FinResearchAgent.run('Vì sao mã này tăng trong phiên hôm nay?',{baseContext:{technicalScanner:{current:{symbol:'FPT'}},localFinancialData:{annualSummary:{period:'2025'}}}});
 assert.equal(second.audit.validation.status,'warn');assert.equal(second.context.agent.evidence.scanner.current,null);assert.equal(second.context.technicalScanner,null);
});

test('macro research prefers canonical series and carries quality warnings',async()=>{
 ctx.FinMacro.context=()=>({checkedAt:now,datasets:{
  macro_overview:{name:'Tổng quan kinh tế vĩ mô',qualityStatus:'warning',qualityWarnings:[{code:'GDP_GROWTH_PLAUSIBILITY'}],rows:[{metric:'GDP',value:32.7}],numericColumns:['value']},
  fdi:{name:'Tình hình FDI',qualityStatus:'ok',rows:[{date:'2026-09',value:1}],numericColumns:['value']},
  gdp_growth:{name:'Tăng trưởng GDP thực tế',qualityStatus:'ok',rows:[{date:'Q3 2026',value:8.39}],numericColumns:['value']},
  pmi:{name:'PMI theo tháng',qualityStatus:'ok',rows:[{date:'2026-09',value:51}],numericColumns:['value']},
  money_supply:{name:'Tổng cung tiền theo tháng',qualityStatus:'ok',rows:[{date:'2026-09',value:10}],numericColumns:['value']}
 }});
 const general=await ctx.FinResearchAgent.run('Phân tích bối cảnh vĩ mô hiện tại.');
 const ids=general.context.agent.evidence.macro.datasets.map(x=>x.id);
 assert.deepEqual(ids,['gdp_growth','pmi','money_supply','fdi']);
 assert(!ids.includes('macro_overview'));
 const gdp=await ctx.FinResearchAgent.run('Phân tích tăng trưởng GDP hiện tại.');
 assert.equal(gdp.context.agent.evidence.macro.datasets[0].id,'gdp_growth');
 assert.equal(gdp.context.agent.evidence.macro.datasets[0].qualityStatus,'ok');
});
