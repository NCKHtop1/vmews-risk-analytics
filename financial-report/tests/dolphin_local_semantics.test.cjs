'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const frontend=path.join(__dirname,'../frontend');
const now=new Date().toISOString();
let subject='FPT';
let bctc={
 symbol:'FPT',
 annual:{periods:['2024','2025'],sections:[{id:'income',rows:[
  {label:'Doanh thu thuần',unit:'million VND',values:{'2024':980000,'2025':1120000}},
  {label:'Lợi nhuận sau thuế',unit:'million VND',values:{'2024':175000,'2025':210000}},
  {label:'ROE',unit:'%',values:{'2024':16.1,'2025':18.2}}
 ]},{id:'balance',rows:[
  {label:'Tài sản ngắn hạn',unit:'million VND',values:{'2024':480000,'2025':null}},
  {label:'Tài sản dài hạn',unit:'million VND',values:{'2024':530000,'2025':670000}},
  {label:'Tổng tài sản',unit:'million VND',values:{'2024':1010000,'2025':1170000}},
  {label:'Nợ ngắn hạn',unit:'million VND',values:{'2024':300000,'2025':null}}
 ]}]},
 quarterly:{periods:['2025-Q1','2025-Q2'],sections:[{id:'income',rows:[
  {label:'Doanh thu thuần',unit:'million VND',values:{'2025-Q1':250000,'2025-Q2':300000}},
  {label:'Lợi nhuận sau thuế',unit:'million VND',values:{'2025-Q1':50000,'2025-Q2':60000}}
 ]}]}
};
let quote={symbol:'FPT',price:57900,reference:59700,changePct:-3.015,sourceTime:now};
let news=[
 {title:'FPT công bố chia cổ tức',symbols:['FPT'],publishedAt:now,url:'https://example.com/fpt'},
 {title:'FRT công bố chia cổ tức',symbols:['FRT'],publishedAt:now,url:'https://example.com/frt'},
 {title:'FPT ký hợp đồng công nghệ',symbols:['FPT'],publishedAt:now,url:'https://example.com/fpt-tech'}
];
const document={getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener:()=>{},body:{append(){},classList:{add(){},remove(){}}}};
const ctx={document,console,Date,URL,URLSearchParams,location:{search:'?symbol=FPT',href:'https://finquery.info.vn/financial-report/index.html?symbol=FPT'},localStorage:{getItem:()=>null,setItem(){}},sessionStorage:{getItem:()=>null,setItem(){}},setTimeout,clearTimeout,performance:{now:()=>1},AbortController};
ctx.window=ctx;ctx.globalThis=ctx;
ctx.FinancialMarket={context:()=>({symbol:subject,quote,technical:{timeframe:'day',sourceTime:now,indicators:{rsi:44,macd:-0.2},snapshot:{title:'Điều chỉnh',detail:'Biến động theo dữ liệu mẫu'}},news,marketNews:[{title:'Thị trường giao dịch ổn định',symbols:[],publishedAt:now,url:'https://example.com/m'}]}),alertContext:()=>({companies:[{symbol:'FPT',name:'FPT Corporation'},{symbol:'MBB',name:'Ngân hàng MB'},{symbol:'FRT',name:'FPT Retail'}]})};
ctx.FinancialReportContext={raw:()=>bctc,resolveSymbol:()=>subject};
ctx.FinResearchAgent={resolveTargetSymbols:q=>['FPT','MBB','FRT'].filter(sym=>new RegExp('(?:^|\\W)'+sym+'(?:\\W|$)').test(q))};
ctx.FinRiskMonitor={context:()=>({status:'ok',sourceTime:now,overall:{score:45,level:{label:'Bình thường'}}})};
ctx.FinMacro={context:()=>({datasets:{}})};
vm.createContext(ctx);
for(const file of ['knowledge-base.js','question-policy.js','research-ai.js'])vm.runInContext(fs.readFileSync(path.join(frontend,file),'utf8'),ctx,{filename:file});
const answer=q=>ctx.FinQueryAI.analyze(q);
const plain=a=>String(a?.html||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
test('all glossary definitions return their own grounded text',()=>{
 for(const item of ctx.FinQueryKnowledge.concepts){
  const result=answer(item.title+' là gì?');
  assert.equal(result.type,'concept',item.title);
  assert.ok(plain(result).includes(item.definition.slice(0,25)),'Wrong definition: '+item.title+' '+plain(result).slice(0,200));
 }
});
test('general BCTC requests use the exact metric and period, never fabricate zero',()=>{
 const total=answer('Tổng tài sản FPT năm 2025 là bao nhiêu?');
 assert.equal(total.type,'metric');
 assert.match(plain(total),/Tổng tài sản.*2025/);
 assert.doesNotMatch(plain(total),/Tài sản ngắn hạn/);
 const unavailable=answer('Tài sản ngắn hạn FPT năm 2025 là bao nhiêu?');
 assert.equal(unavailable.type,'metric');
 assert.match(plain(unavailable),/chưa có số liệu hợp lệ/);
 assert.doesNotMatch(plain(unavailable),/0 tỷ/);
 const revenue=answer('Doanh thu FPT quý 2\/2025 là bao nhiêu?');
 assert.equal(revenue.type,'metric');
 assert.match(plain(revenue),/2025-Q2/);
 assert.doesNotMatch(plain(revenue),/2025-Q1/);
 const compare=answer('So sánh lợi nhuận FPT năm 2024 và 2025');
 assert.ok(['compare','metric','multiMetric'].includes(compare.type));
 assert.match(plain(compare),/2024/);
 assert.match(plain(compare),/2025/);
});
test('compound user questions return all named concepts, not unrelated glossary terms',()=>{
 const two=answer('ROE và ROA là gì?');
 assert.equal(two.type,'multiConcept');
 assert.match(plain(two),/ROE/);
 assert.match(plain(two),/ROA/);
 const concept=answer('Tài sản ngắn hạn là gì?');
 assert.equal(concept.type,'concept');
 assert.match(plain(concept),/Tài sản ngắn hạn là/);
 assert.doesNotMatch(plain(concept),/TOI là tổng thu nhập/);
});
test('company news is restricted to matching company and topic',()=>{
 const fpt=answer('Tin cổ tức của FPT');
 assert.equal(fpt.type,'news');
 assert.match(plain(fpt),/FPT công bố chia cổ tức/);
 assert.doesNotMatch(plain(fpt),/FRT công bố chia cổ tức/);
 assert.doesNotMatch(plain(fpt),/hợp đồng công nghệ/);
 const frt=answer('Tin cổ tức của FRT');
 assert.doesNotMatch(plain(frt),/FPT công bố chia cổ tức/);
});
test('wrong ticker and multi-company questions cannot leak single-company financial context',()=>{
 const multi=answer('So sánh tổng tài sản FPT và MBB năm 2025');
 assert.equal(multi.type,'multiSymbol');
 assert.match(plain(multi),/không thể so sánh chính xác/);
 const wrong=answer('Doanh thu MBB năm 2025 bao nhiêu');
 assert.match(plain(wrong),/không dùng số liệu của mã khác/);
});
test('technical and current-session price evidence fails closed when stale',()=>{
 const t=answer('Chỉ báo RSI và MACD hiện tại');
 assert.equal(t.type,'technical');
 assert.match(plain(t),/RSI/);
 assert.match(plain(t),/MACD/);
 const old=quote;
 try{
  quote={...quote,sourceTime:'2026-10-07T07:45:00+00:00'};
  const result=answer('Giá FPT hôm nay?');
  assert.equal(result.type,'movement');
  assert.match(plain(result),/không dùng giá sai mã hoặc phiên cũ/);
 }finally{quote=old;}
});
test('unknown subjects and unverified forecasts do not invent evidence',()=>{
 const outside=answer('Thời tiết Hà Nội ngày mai');
 assert.equal(outside.type,'unknown');
 assert.match(plain(outside),/chưa xác định được đủ dữ liệu/);
 const forecast=answer('Dự báo T+3 FPT');
 assert.equal(forecast.type,'forecast');
 assert.match(plain(forecast),/Không có dự báo được xác minh/);
});

test('unrecognized explicit stock cannot borrow the active FPT quote',()=>{
 const x=answer('Gia ma ZZZ hom nay bao nhieu?');
 assert.match(plain(x),/Không tìm thấy mã ZZZ/);
 assert.doesNotMatch(plain(x),/FPT đang (tăng|giảm)/);
});
test('buy-or-sell question returns a bounded risk analysis rather than generic refusal',()=>{
 const x=answer('FPT hôm nay nên mua hay bán?');
 assert.equal(x.type,'advice');
 assert.match(plain(x),/MUA|BÁN/);
 assert.match(plain(x),/rủi ro/);
});
test('retailer company full name is not simultaneously identified as parent FPT ticker',()=>{
 const sandbox={FinancialMarket:{alertContext:()=>({companies:[{symbol:'FPT',name:'FPT Corporation'},{symbol:'FRT',name:'FPT Retail'},{symbol:'MBB',name:'Ngân hàng MB'}]})},FinancialReportContext:{companies:()=>[{symbol:'FPT'},{symbol:'FRT'},{symbol:'MBB'}]}};
 sandbox.window=sandbox;sandbox.globalThis=sandbox;vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync(path.join(frontend,'research-agent.js'),'utf8'),sandbox);
 assert.deepEqual(Array.from(sandbox.FinResearchAgent.resolveTargetSymbols('Tin về FPT Retail / FRT hôm nay?')),['FRT']);
 assert.deepEqual(Array.from(sandbox.FinResearchAgent.resolveTargetSymbols('So sánh FPT Retail với FPT')),['FRT','FPT']);
});
test('Dolphin must hide launcher and bound Gemini wait time',()=>{
 const css=fs.readFileSync(path.join(frontend,'market.css'),'utf8');
 const js=fs.readFileSync(path.join(frontend,'research-ai.js'),'utf8');
 assert.match(css,/body\.dolphin-modal-open \.ai-fab\{display:none!important/);
 assert.match(js,/maxWaitMs=state\.mode==='deep'\?90000:45000/);
 assert.match(js,/Promise\.race\(\[callLLM\(q,state\.currentController\),deadline\]\)/);
});
