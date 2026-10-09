'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function createHarness(){
 const now=new Date(Date.now()-60000).toISOString();
 const annual={periods:['2024','2025'],sections:[{id:'balance',rows:[
  {label:'Tổng tài sản',unit:'triệu đồng',values:{'2024':200000,'2025':300000}},
  {label:'Tài sản ngắn hạn',unit:'triệu đồng',values:{'2024':100000,'2025':150000}},
  {label:'Hàng tồn kho',unit:'triệu đồng',values:{'2024':30000,'2025':null}},
  {label:'Doanh thu thuần',unit:'triệu đồng',values:{'2024':90000,'2025':120000}},
  {label:'Nợ phải trả',unit:'triệu đồng',values:{'2024':80000,'2025':100000}},
  {label:'Vốn chủ sở hữu',unit:'triệu đồng',values:{'2024':120000,'2025':200000}},
  {label:'Tỷ suất lợi nhuận trên vốn chủ sở hữu bình quân',unit:'%',values:{'2024':12,'2025':15}},
  {label:'Tỷ suất sinh lời trên tổng tài sản bình quân',unit:'%',values:{'2024':9,'2025':10}}
 ]}]};
 const quarterly={periods:['2025-Q1','2025-Q2'],sections:[{id:'balance',rows:[
  {label:'Tài sản ngắn hạn',unit:'triệu đồng',values:{'2025-Q1':100000,'2025-Q2':110000}},
  {label:'Doanh thu thuần',unit:'triệu đồng',values:{'2025-Q1':20000,'2025-Q2':30000}}
 ]}]};
 const mock={report:{symbol:'FPT',annual,quarterly}, market:{
  symbol:'FPT',quote:{symbol:'FPT',price:100000,reference:99000,changePct:1.01,sourceTime:now},
  technical:{sourceTime:now,snapshot:{title:'Xu hướng tăng',detail:'Tham chiếu chart'}},
  newsCheckedAt:now,news:[
   {title:'FPT thông báo chia cổ tức',symbols:['FPT'],publishedAt:now,url:'https://example.com/fpt1'},
   {title:'FRT thông báo chia cổ tức',symbols:['FRT'],publishedAt:now,url:'https://example.com/frt1'}],
  marketNews:[],scanner:null
 }, macro:{datasets:{pmi:{name:'PMI Việt Nam',qualityStatus:'ok',numericColumns:['value'],metricLabels:{value:'PMI'},source:'Nguồn PMI',rows:[{date:'2026-08',value:49.5},{date:'2026-09',value:51.2}]}}}};
 const document={getElementById(){return null},querySelector(){return null},querySelectorAll(){return[]},addEventListener(){},body:{append(){} }};
 const ctx={console,Date,Math,JSON,Number,String,Intl,URL,URLSearchParams,Set,Map,Promise,document,location:{href:'https://example.com/vmews-risk-analytics/financial-report/index.html',search:''},performance:{now:()=>1},localStorage:{getItem(){return null},setItem(){}},sessionStorage:{getItem(){return null},setItem(){}},
  FinancialReportContext:{raw:()=>mock.report,companies:()=>[{symbol:'FPT',name:'FPT'},{symbol:'MBB',name:'MB Bank'},{symbol:'FRT',name:'FRT Retail'}],resolveSymbol:(q)=>/\bMBB\b/.test(q)?'MBB':/\bFRT\b/.test(q)?'FRT':/\bFPT\b/.test(q)?'FPT':'',select:async symbol=>({symbol})},
  FinancialMarket:{context:()=>mock.market,alertContext:()=>({companies:[{symbol:'FPT',name:'FPT'},{symbol:'FRT',name:'FRT Retail'},{symbol:'MBB',name:'MB Bank'}]})},
  FinInsights:{context:()=>({})},FinMacro:{context:()=>mock.macro},FinRiskMonitor:{context:()=>null}};
 ctx.window=ctx;ctx.globalThis=ctx;
 vm.createContext(ctx);
 for(const name of ['knowledge-base.js','question-policy.js','research-agent.js','research-ai.js']){
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend',name),'utf8'),ctx,{filename:name});
 }
 return{ask:q=>ctx.FinQueryAI.analyze(q),ctx,mock,now};
}
test('end to end: latest prices do not borrow a stale or wrong session',()=>{
 const h=createHarness();
 let r=h.ask('Giá FPT hiện tại bao nhiêu?');
 assert.equal(r.type,'movement');assert.match(r.html,/FPT/);
 h.mock.market.quote.sourceTime='2026-10-07T07:45:00Z';
 r=h.ask('Giá FPT hiện tại bao nhiêu?');assert.match(r.html,/snapshot hợp lệ|cũ quá 10 phút/);
 assert.doesNotMatch(r.html,/100\.000/);
 h.mock.market.quote.sourceTime=h.now;
 r=h.ask('Giá FPT hôm qua bao nhiêu?');assert.match(r.html,/phiên hoặc ngày lịch sử/);
});
test('end to end: total assets annual, requested quarter and missing inventory stay separate',()=>{
 const h=createHarness();
 let r=h.ask('Quy mô tổng tài sản FPT năm 2025 bao nhiêu?');
 assert.equal(r.type,'metric');assert.match(r.html,/kỳ 2025/);assert.doesNotMatch(r.html,/BCTC quý/);
 r=h.ask('Tài sản ngắn hạn FPT quý 2/2025 bao nhiêu?');
 assert.equal(r.type,'metric');assert.match(r.html,/2025-Q2/);assert.doesNotMatch(r.html,/2025-Q1.*110/);
 r=h.ask('Hàng tồn kho FPT năm 2025 bao nhiêu?');
 assert.match(r.html,/chưa có số liệu hợp lệ/);assert.doesNotMatch(r.html,/>0</);
});
test('end to end: named company news excludes adjacent ticker',()=>{
 const h=createHarness();
 const r=h.ask('Tin cổ tức FPT mới nhất');
 assert.equal(r.type,'news');assert.match(r.html,/FPT thông báo/);assert.doesNotMatch(r.html,/FRT thông báo/);
 h.mock.market.newsCheckedAt='2026-10-01T07:45:00Z';
 const stale=h.ask('Tin cổ tức FPT mới nhất');
 assert.match(stale.html,/KHÔNG khẳng định là tin mới nhất/);
});
test('end to end: explicit macro historical month must not silently use the latest month',()=>{
 const h=createHarness();
 const older=h.ask('PMI tháng 8/2026 bao nhiêu?');
 assert.equal(older.type,'macro');assert.match(older.html,/49,5/);assert.doesNotMatch(older.html,/51,2/);
 const missing=h.ask('PMI tháng 7/2026 bao nhiêu?');
 assert.match(missing.html,/Không tìm thấy kỳ 2026-07/);assert.doesNotMatch(missing.html,/51,2/);
});
test('end to end: active symbol conflicts and multi-ticker prompts fail closed',()=>{
 const h=createHarness();
 h.mock.report.symbol='MBB';
 const wrong=h.ask('Doanh thu FPT năm 2025 bao nhiêu');
 assert.match(wrong.html,/BCTC đang tải thuộc mã MBB/);
 h.mock.report.symbol='FPT';
 const multi=h.ask('So sánh FPT và MBB năm 2025');
 assert.equal(multi.type,'multiSymbol');assert.match(multi.html,/không thể so sánh chính xác/);
});
test('end to end: arbitrary non-financial prompts must not receive unrelated stock facts',()=>{
 const h=createHarness();
 for(const q of ['Công thức nấu phở Hà Nội','Trái đất có bao nhiêu vệ tinh?','Tôi không hỏi về TOI']){
  const r=h.ask(q);assert.doesNotMatch(r.html,/TOI là tổng thu nhập hoạt động/);
 }
});
