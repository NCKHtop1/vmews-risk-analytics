'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const marketData=fs.readFileSync(path.join(root,'frontend/market-data.js'),'utf8');
const marketUi=fs.readFileSync(path.join(root,'frontend/market.js'),'utf8');
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');

function setup(rawQuotesOk=true){
 const current=new Date(Date.now()-120000).toISOString();
 const older=new Date(Date.now()-600000).toISOString();
 const quote={
  status:'ok',expected:2,coverage:2,latestSourceTime:current,checkedAt:current,
  quotes:{MBB:{symbol:'MBB',price:24500,sourceTime:current,status:'ok'},
          FPT:{symbol:'FPT',price:99000,sourceTime:current,status:'ok'}}
 };
 const observed=[];
 async function fetch(url){
  observed.push(String(url));
  const isRaw=String(url).startsWith('https://raw.githubusercontent.com/');
  const file=String(url).split('?')[0].split('/').pop();
  const okay=file==='quotes.json'&&(!isRaw||rawQuotesOk);
  return {ok:okay,status:okay?200:503,json:async()=>quote};
 }
 const doc={documentElement:{dataset:{hosting:'pages'}},dispatchEvent(){}};
 const ctx={window:{},document:doc,location:{href:'https://finquery.info.vn/financial-report/'},
  URL,Date,AbortController,AbortSignal,Promise,CustomEvent:class{},
  setTimeout,clearTimeout,fetch};
 vm.runInNewContext(marketData,ctx,{filename:'market-data.js'});
 return {api:ctx.window.FinMarketData,quote,observed,older};
}

async function verify(rawQuotesOk){
 const {api,quote,observed,older}=setup(rawQuotesOk);
 await assert.rejects(api.getAlignedBundle({timeout:250,hedgeMs:5}),/No valid market snapshot|Market bundle/);
 const independent=await api.get('quotes.json',{timeout:250,hedgeMs:5});
 assert.equal(independent.expected,2);
 assert.equal(independent.coverage,2);
 const prices={MBB:{symbol:'MBB',price:23000,sourceTime:older}};
 api.mergeQuotes(prices,independent.quotes);
 assert.equal(prices.MBB.price,24500);
 assert.equal(prices.FPT.price,99000);
 api.mergeQuotes(prices,{MBB:{symbol:'MBB',price:30000,sourceTime:older}});
 assert.equal(prices.MBB.price,24500,'older prices must never overwrite newer prices');
 api.mergeQuotes(prices,{MBB:{symbol:'MBB',price:0,sourceTime:quote.latestSourceTime}});
 assert.equal(prices.MBB.price,24500,'invalid nonpositive quote must not overwrite prices');
 if(!rawQuotesOk)assert(observed.some(s=>s.startsWith('https://finquery.info.vn/financial-report/market/quotes.json')),'same-origin mirror must recover when raw is unavailable');
}
(async()=>{
 assert(marketUi.includes("get('quotes.json')"),'standalone quote hydration must remain in refresh');
 assert(marketUi.includes('state.priceOnlyMode'),'price-only analytical guard must remain');
 assert(marketUi.includes("state.priceOnlyMode||quoteStale"),'unsynced quote must be hidden from AI context');
 assert(html.includes('id="news-intelligence-summary"'),'News summary must have actual DOM');
 await verify(true);
 await verify(false);
 console.log('FINQUERY PRICE FAILOVER PASS: analytical files down, raw quote available, same-origin mirror recovery, monotonic quote guard');
})().catch(e=>{console.error(e);process.exitCode=1;});
