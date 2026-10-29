"use strict";
// Reproduces stopped downloads, abort, complete source outage, recovery and
// coherent cache against the actual compact FinQuery VN100 product contract.
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const ROOT=path.resolve(__dirname,"..");
const src=fs.readFileSync(path.join(ROOT,"forecast-final-v12.js"),"utf8");
const leader=fs.readFileSync(path.join(ROOT,"forecast-live-leaders-v14.js"),"utf8");

function makeContext(host="finquery.info.vn"){
  const state={calls:[],handler:null};
  const origin="https://"+host;
  const window={__FINQUERY_FORECAST_TIMEOUT_MS:35,addEventListener(){}};
  const location={hostname:host,origin,pathname:"/forecast-final.html",search:"",
    href:origin+"/forecast-final.html",reload(){}};
  const document={hidden:false,addEventListener(){},querySelector(){return null;}};
  const ctx={window,location,document,Date,Intl,URL,URLSearchParams,AbortController,AbortSignal,
    setTimeout,clearTimeout,console,CustomEvent:class{}};
  ctx.fetch=async(url,opts)=>{state.calls.push(String(url));return state.handler(String(url),opts);};
  vm.runInNewContext(src,ctx,{filename:"forecast-final-v12.js"});
  return{ctx,state};
}
function product(){
  const symbols={},charts={};
  for(let n=0;n<100;n++){
    const sym="S"+String(n).padStart(3,"0"),horizons={};
    for(let h=1;h<=5;h++)horizons[String(h)]={
      priceValidated:true,expectedPrice:20000+h*100,q20Price:19000+h*100,q80Price:21000+h*100};
    symbols[sym]={symbol:sym,close:20000,date:"2026-10-28",horizons};
    charts[sym]=Array.from({length:8},(_,i)=>({date:"2026-10-"+String(20+i).padStart(2,"0"),close:20000+i*50}));
  }
  return{
    status:"PASS",generatedAt:new Date().toISOString(),asOf:"2026-10-28",universe:{expected:100,available:100},
    gates:{status:"PASS"},dashboard:{asOf:"2026-10-28",generatedAt:new Date().toISOString(),symbols,charts},
    model:{promotion:{status:"PASS",directPriceHorizons:[1,2,3,4,5]}},
    backtest:{horizons:{},cases:{}}
  };
}
function abortingFetch(_url,options){
  return new Promise((_resolve,reject)=>options.signal.addEventListener("abort",()=>reject(Error("AbortError")),{once:true}));
}
function ok(payload){return{ok:true,status:200,json:async()=>payload};}
(async()=>{
  assert(src.includes("hist.map(CHART_EXECUTABLE_CLOSE)"),"historical chart must use executable closes");
  assert(src.includes("y:y(CHART_EXECUTABLE_CLOSE(item))"),"chart must use recorded close values");
  assert(src.includes("Thử tải lại"),"outage must offer retry");
  assert(src.includes("void priceFetch.then("),"live quote must not block numeric forecast render");
  assert(leader.includes("controller.abort()"),"optional market session requests must remain bounded");

  const{ctx,state}=makeContext();
  state.handler=abortingFetch;
  const start=Date.now();
  await assert.rejects(ctx.window.__VMEWS_LOAD_BASE__(),/quá thời hạn|chưa sẵn sàng/);
  assert(Date.now()-start<1000,"complete CDN outage must fail in bounded time");
  assert(state.calls.length>=3,"compact, mirror and full fallback must all be attempted");
  assert(state.calls.some(u=>u.includes("finquery-vn100-product.json")),"compact product route required");

  state.calls.length=0;
  const verified=product();
  state.handler=async url=>url.includes("/finquery-vn100-forecast.json")?ok(verified):{ok:false,status:503};
  const base=await ctx.window.__VMEWS_LOAD_BASE__();
  assert.equal(base.source,"VN100");
  assert.equal(Object.keys(base.dash.symbols).length,100);
  assert(Object.values(base.dash.symbols).every(z=>Object.keys(z.horizons).length===5));
  assert.equal(base.model.promotion.status,"PASS");
  assert(state.calls.some(u=>u.includes("/finquery-vn100-forecast.json")),"full last-good source required");
  assert(!state.calls.some(u=>u.includes("/solution-ai-core-data/")),"FinQuery must not silently switch to different HOSE model");

  const calls=state.calls.length;
  assert.strictEqual(await ctx.window.__VMEWS_LOAD_BASE__(),base);
  assert.equal(state.calls.length,calls,"successful verified model must stay cached");
  console.log("FORECAST LOADER PASS: 3-source bounded outage; 100/500 replay; verified recovery; source isolation; coherent cache");
})().catch(error=>{console.error(error);process.exitCode=1;});
