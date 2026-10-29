const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const page=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
const script=fs.readFileSync(path.join(root,'frontend/derivatives-market.js'),'utf8');
const build=fs.readFileSync(path.join(root,'scripts/build_cdn.py'),'utf8');
const refTime=new Date().toISOString();
const f={
 schemaVersion:1,status:'ok',exchange:'HNX',type:'FUTURES_ONLY',
 source:'https://kbbuddywts.kbsec.com.vn/',sourceName:'KBS delayed market quotes',
 collectedAt:refTime,latestSourceTime:refTime,
 contracts:[
 {symbol:'VN30F2611',providerSymbol:'41I1GB000',underlying:'VN30',expiry:'2026-11-19',
  price:1842.5,reference:1838,change:4.5,volume:34000,openInterest:35000,
  market:'HNX_FUTURES',unit:'points',sourceTime:refTime,high:1858,low:1826,
  series:[{time:new Date(Date.now()-300000).toISOString(),price:1838},{time:refTime,price:1842.5}]},
 {symbol:'VN100F2611',providerSymbol:'41I2GB000',underlying:'VN100',expiry:'2026-11-19',
  price:1878.7,reference:1874.4,volume:1230,openInterest:220,
  market:'HNX_FUTURES',unit:'points',sourceTime:refTime,high:1900,low:1870}
 ]
};
function harness(){
 const listeners={};const nodes={};
 function get(id){if(!nodes[id])nodes[id]={id,innerHTML:'',addEventListener(type,fn){listeners[id+':'+type]=fn;}};return nodes[id];}
 const document={getElementById:get,hidden:false,addEventListener(type,fn){listeners['document:'+type]=fn;}};
 const ctx={window:{},document,Date,Intl,Math,Number,String,URL,AbortSignal,
  fetch:async()=>({ok:true,json:async()=>f}),setInterval:()=>42,console};
 vm.createContext(ctx);
 vm.runInContext(script,ctx,{timeout:3000});
 return {api:ctx.window.FinDerivativeQuotes,get,listeners};
}
test('Futures dashboard appears before monthly legacy statistics and in CDN build',()=>{
 assert.match(page,/id="money-futures-live"/);
 assert.match(page,/<details class="money-derivative-history">/);
 assert.match(page,/src="derivatives-market.js"/);
 assert.match(build,/derivatives-market\.js/);
 assert.ok(build.includes("(front / 'derivatives-market.js').read_text()"));
});
test('reads VN30F/VN100F price board independently of monthly OI',()=>{
 const {api,get}=harness();api.setData(f);
 const html=get('money-futures-live').innerHTML;
 assert.match(html,/VN30F2611/);
 assert.match(html,/VN100F2611/);
 assert.match(html,/1\.842,5/);
 assert.match(html,/1\.878,7/);
 assert.match(html,/34\.000/);
 assert.match(html,/35\.000/);
 assert.match(html,/Trong giờ giao dịch|Ngoài giờ giao dịch|Giá chậm cập nhật/);
 assert.doesNotMatch(html,/KBS|Nguồn|kbbuddywts|<th>\s*Nguồn\s*<\/th>/i);
 assert.match(html,/derivative-spark/);
 assert.doesNotMatch(html,/KLGD bình quân\/phiên/);
});
test('drops unverified, impossible, expired or unauthorized contract values',()=>{
 const {api,get}=harness();const invalid=JSON.parse(JSON.stringify(f));
 invalid.contracts[1].sourceTime='2039-10-23T00:00:00Z';
 invalid.contracts[0].symbol='<img src=x onerror=alert(1)>';
 api.setData(invalid);
 const html=get('money-futures-live').innerHTML;
 assert.doesNotMatch(html,/<img/);
 assert.doesNotMatch(html,/1\.842,5/);
 assert.doesNotMatch(html,/1\.878,7/);
 assert.match(html,/Chưa có dữ liệu/);
});
test('timestamp freshness and weekend close labels are not falsely live',()=>{
 const {api}=harness();
 const sample=f.contracts[0];
 const weekend=Date.parse('2026-10-24T03:15:00+00:00');
 const session=Date.parse('2026-10-26T03:15:00+00:00');
 assert.equal(api._test.marketOpen(weekend),false);
 assert.equal(api._test.marketOpen(session),true);
 assert.match(api._test.statusFor(sample,weekend),/phiên gần nhất/);
 const stale={...sample,sourceTime:'2026-10-23T03:15:07+00:00'};
 assert.match(api._test.statusFor(stale,session),/chậm cập nhật/);
});
test('data source schema check and XSS encoding',()=>{
 const {api}=harness();
 assert.equal(api._test.healthy({...f,exchange:'HOSE'}),false);
 assert.equal(api._test.healthy({...f,collectedAt:'no date'}),false);
 assert.equal(api._test.healthy(f),true);
 assert.equal(api._test.contracts(f).length,2);
 assert.doesNotMatch(api._test.miniHistory([{time:refTime,price:1},{time:refTime,price:2}]),/<script/);
});

test('futures are rendered as a compact terminal with valid rolling aliases',()=>{
 const {api,get}=harness();api.setData(f);
 const html=get('money-futures-live').innerHTML;
 assert.match(page,/id="market-futures-workspace"/);
 assert.ok(page.indexOf('id="money-futures-live"')<page.indexOf('id="macro-liquidity-overview"'),'futures in Market rather than Macro');
 assert.match(html,/derivative-board-table/);
 assert.match(html,/Chọn hợp đồng/);
 assert.match(html,/VN30F1M/);
 assert.match(html,/VN100F1M/);
 assert.equal(api._test.withAliases(api._test.contracts(f))[0].alias,'VN30F1M');
 assert.doesNotMatch(html,/<canvas[^>]*OHLC/);
});
