const fs=require('fs');const vm=require('vm');const assert=require('assert');
const code=fs.readFileSync(require('path').join(__dirname,'../frontend/research-agent.js'),'utf8');
const store=new Map(),now=new Date().toISOString(),old=new Date(Date.now()-60*60000).toISOString();let scannerTime=now;
const ctx={console,Date,JSON,Math,Number,String,Object,Array,Set,Promise,performance:{now:()=>1},sessionStorage:{setItem:(k,v)=>store.set(k,v),getItem:k=>store.get(k)||null},FinancialMarket:{context:()=>({symbol:'FPT',quote:{symbol:'FPT',price:100000,reference:98000,changePct:2.04,sourceTime:now},driver:{relativeStrengthPct:1.1},technical:{snapshot:{title:'Trend'},sourceTime:now},newsCheckedAt:now,news:[{title:'FPT news',publishedAt:now,url:'https://example.com'}],marketNews:[{title:'Market news',publishedAt:now,url:'https://example.com/m'}]})},FinTechnicalScanner:{context:()=>({sourceTime:scannerTime,checkedAt:scannerTime,aligned:scannerTime===now,current:{symbol:'FPT',rsi14:55,volumeRatio20:1.2,signals:[]}})},FinStrategyBuilder:{context:()=>({strategy:{name:'x',conditions:[]},snapshot:{coverage:100},matches:[]})},FinInsights:{context:()=>({updatedAt:now,brokerResearch:[],corporateEvents:[],consensus:null})},FinMacro:{context:()=>({checkedAt:now,datasets:{pmi:{name:'PMI',rows:[{date:'2026-09',value:51}],numericColumns:['value']}}})}};
ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(code,ctx);
test('research agent plans tools and excludes stale scanner evidence',async()=>{
 assert.equal(ctx.FinResearchAgent.version,'FINQUERY_RESEARCH_AGENT_V1');
 assert.equal(ctx.FinResearchAgent.classify('ROE là gì?'),'concept');
 assert.equal(ctx.FinResearchAgent.classify('Phân tích sâu toàn diện mã này'),'memo');
 const p=ctx.FinResearchAgent.plan('Tìm mã MACD cắt lên, RSI trên 50 nhưng cơ bản không xấu');
 assert.equal(p.intent,'technical');assert(p.tools.includes('scanner')&&p.tools.includes('strategy')&&p.tools.includes('financial'));
 const first=await ctx.FinResearchAgent.run('Vì sao mã này tăng trong phiên hôm nay?',{baseContext:{technicalScanner:{current:{symbol:'FPT'}},localFinancialData:{annualSummary:{period:'2025'}}}});
 assert.equal(first.audit.iterations,2);assert.equal(first.audit.validation.status,'ok');assert.equal(first.context.agent.evidence.market.quote.symbol,'FPT');assert(store.has('finquery_research_agent_last'));
 scannerTime=old;
 const second=await ctx.FinResearchAgent.run('Vì sao mã này tăng trong phiên hôm nay?',{baseContext:{technicalScanner:{current:{symbol:'FPT'}},localFinancialData:{annualSummary:{period:'2025'}}}});
 assert.equal(second.audit.validation.status,'warn');assert.equal(second.context.agent.evidence.scanner.current,null);assert.equal(second.context.technicalScanner,null);
});
