const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market-data.js'),'utf8');
function setup(fetch){const ctx={window:{},document:{documentElement:{dataset:{hosting:'pages'}}},location:{href:'https://example.test/financial-report/'},fetch,URL,Date,AbortSignal,DOMException};vm.runInNewContext(code,ctx);return ctx.window.FinMarketData;}
const bundle=(minutes,price=100)=>({checkedAt:new Date(Date.now()-minutes*60000).toISOString(),quotes:{ACB:{price}}});
test('publisher update wins over successful stale Pages response',async()=>{const api=setup(async url=>({ok:true,json:async()=>bundle(url.includes('raw.githubusercontent')?1:90,url.includes('raw.githubusercontent')?110:100)}));assert.equal((await api.get('quotes.json')).quotes.ACB.price,110);});
test('future publisher snapshot cannot displace valid Pages data',async()=>{const api=setup(async url=>({ok:true,json:async()=>bundle(url.includes('raw.githubusercontent')?-600:10)}));assert.ok(Date.parse((await api.get('quotes.json')).checkedAt)<Date.now());});
test('failed publisher uses valid same-origin snapshot',async()=>{const api=setup(async url=>{if(url.includes('raw.githubusercontent'))throw Error('offline');return{ok:true,json:async()=>bundle(20)};});assert.ok((await api.get('quotes.json')).quotes.ACB);});
test('unavailable sources fail explicitly',async()=>{const api=setup(async()=>({ok:false,status:503}));await assert.rejects(api.get('quotes.json'),/No valid/);});
test('future quote cannot poison merges; valid quote repairs prior future value',()=>{const api=setup(()=>{}),now=new Date().toISOString(),future=new Date(Date.now()+86400000).toISOString();const target={ACB:{price:999,sourceTime:future}};api.mergeQuotes(target,{ACB:{price:100,sourceTime:now}});assert.equal(target.ACB.price,100);api.mergeQuotes(target,{ACB:{price:999,sourceTime:future}});assert.equal(target.ACB.price,100);api.mergeQuotes(target,{ACB:{price:90,sourceTime:new Date(Date.now()-86400000).toISOString()}});assert.equal(target.ACB.price,100);});
test('a renderer exception releases refresh lock and the next refresh succeeds',async()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../frontend/market.js'),'utf8');
 const refresh=source.slice(source.indexOf('async function refresh(){'),source.indexOf('window.FinancialMarket='));
 const button={},status={},state={quotes:{},companies:[],coreCompanies:[],symbol:'ACB',refreshing:false};let calls=0,broken=true;
 const ctx={state,$:id=>id==='market-refresh'?button:status,get:async()=>{calls++;return{};},Date,Promise,console:{error(){}},newsStale:()=>false,quoteStale:()=>true,marketSessionActive:()=>false,showQuote:()=>{if(broken)throw Error('render failed');},board(){},news(){},chartController:{loading:true},window:{FinTechnicalScanner:{},FinQueryAI:{sync(){}}}};
 vm.runInNewContext(refresh+';this.run=refresh',ctx);
 await ctx.run();assert.equal(state.refreshing,false);assert.equal(button.disabled,false);
 broken=false;await ctx.run();assert.equal(calls,8);assert.equal(state.initialized,true);assert.equal(state.refreshing,false);
});
