'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs'),path=require('node:path');
const base=path.join(__dirname,'../frontend');
const now=new Date().toISOString();
const annual={periods:['2024','2025'],sections:[
 {id:'income',rows:[
  {label:'Doanh thu thuần',unit:'triệu đồng',values:{'2024':1000000,'2025':1200000}},
  {label:'Lợi nhuận sau thuế',unit:'triệu đồng',values:{'2024':95000,'2025':125000}},
  {label:'Tỷ suất lợi nhuận trên vốn chủ sở hữu bình quân',unit:'%',values:{'2024':16.5,'2025':18.2}},
  {label:'Tỷ suất sinh lời trên tổng tài sản bình quân',unit:'%',values:{'2024':8.2,'2025':9.1}}
 ]},
 {id:'balance',rows:[
  {label:'Tổng tài sản',unit:'triệu đồng',values:{'2024':2500000,'2025':2800000}},
  {label:'Tài sản ngắn hạn',unit:'triệu đồng',values:{'2024':900000,'2025':1000000}},
  {label:'Nợ ngắn hạn',unit:'triệu đồng',values:{'2024':500000,'2025':600000}},
  {label:'Nợ phải trả',unit:'triệu đồng',values:{'2024':1500000,'2025':1600000}},
  {label:'Vốn chủ sở hữu',unit:'triệu đồng',values:{'2024':1000000,'2025':1200000}},
  {label:'Hàng tồn kho',unit:'triệu đồng',values:{'2024':null,'2025':450000}}
 ]}
]};
const quarterly={periods:['2025-Q1','2025-Q2'],sections:[{id:'income',rows:[
 {label:'Doanh thu thuần',unit:'triệu đồng',values:{'2025-Q1':270000,'2025-Q2':310000}},
 {label:'Lợi nhuận sau thuế',unit:'triệu đồng',values:{'2025-Q1':21000,'2025-Q2':33000}}
]}]};
const allNews=[
 {title:'FPT vừa công bố chia cổ tức năm 2026',summary:'Công bố cổ tức',symbols:['FPT'],source:'Sở giao dịch',url:'https://example.com/fpt-dividend',publishedAt:now},
 {title:'FPT ký hợp đồng công nghệ',summary:'Hợp đồng mới',symbols:['FPT'],source:'Báo chí',url:'https://example.com/fpt-tech',publishedAt:now},
 {title:'FRT chia cổ tức',summary:'Cổ tức FRT',symbols:['FRT'],source:'Báo chí',url:'https://example.com/frt-dividend',publishedAt:now}
];
const market={symbol:'FPT',quote:{symbol:'FPT',price:57900,reference:59700,changePct:-3.015,volume:1000000,sourceTime:now},technical:{indicators:{rsi:42,macd:-30},timeframe:'1d',sourceTime:now,snapshot:{title:'Động lượng yếu',detail:'RSI dưới 50'}},news:allNews,marketNews:[],scanner:{current:{symbol:'FPT',signals:[]}},driver:null};
const noop=()=>{};
const ctx={
 console,Math,Number,String,Date,JSON,Set,Map,Promise,Intl,URL,URLSearchParams,AbortController,
 location:{search:'?symbol=FPT',href:'https://finquery.info.vn/financial-report/index.html?symbol=FPT'},
 document:{body:null,getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener:noop},
 localStorage:{getItem:()=>null,setItem:noop},sessionStorage:{getItem:()=>null,setItem:noop,removeItem:noop},
 FinancialReportContext:{raw:()=>({symbol:'FPT',annual,quarterly}),companies:()=>[{symbol:'FPT'},{symbol:'MBB'}]},
 FinancialMarket:{context:()=>market,alertContext:()=>({companies:[{symbol:'FPT'},{symbol:'MBB'}]})},
 FinMacro:{context:()=>({datasets:{
    macro_overview:{numericColumns:['value'],rows:[{value:999}],source:'unrelated'},
    gdp_growth:{numericColumns:['value'],rows:[{value:8.3}],source:'GDP only'}
 }})},
 FinRiskMonitor:{context:()=>null},
 FinForecast:{context:()=>null},
 FinResearchAgent:{resolveTargetSymbols:q=>['FPT','MBB'].filter(symbol=>new RegExp('\\b'+symbol+'\\b').test(String(q)))}
};
ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);
for(const file of ['knowledge-base.js','question-policy.js','research-ai.js'])
 vm.runInContext(fs.readFileSync(path.join(base,file),'utf8'),ctx,{filename:file,timeout:5000});
function ask(q){return ctx.FinQueryAI.analyze(q);}
test('all canonical glossary concepts give their actual own definition, not merely HTML',()=>{
 const failures=[];
 for(const c of ctx.FinQueryKnowledge.concepts){
  const x=ask(c.title+' là gì?');
  if(x.type!=='concept'||!x.html.includes(c.definition.slice(0,28)))failures.push({id:c.id,type:x.type,preview:x.html.slice(0,100)});
 }
 assert.deepEqual(failures,[]);
});
test('specific BCTC values preserve issuer, year, quarter and missing records',()=>{
 let x=ask('Doanh thu FPT năm 2025 bao nhiêu?');
 assert.equal(x.type,'metric');assert.match(x.html,/1\.200|1,200|1 200|1200/);assert.match(x.html,/2025/);
 x=ask('Lợi nhuận sau thuế quý 2 2025 của FPT bao nhiêu?');
 assert.equal(x.type,'metric');assert.match(x.html,/2025-Q2/);assert.match(x.html,/33/);
 x=ask('ROE của FPT năm 2023 bao nhiêu?');
 assert.equal(x.type,'metric');assert.match(x.html,/2023/);assert.match(x.html,/chưa có số liệu/i);
 assert.doesNotMatch(x.html,/18,2%|18\.2%/);
 x=ask('Hàng tồn kho FPT năm 2024 bao nhiêu?');
 assert.match(x.html,/chưa có số liệu/i);assert.doesNotMatch(x.html,/0 tỷ/);
});
test('topic and symbol binding prevent unrelated news and false price explanations',()=>{
 let x=ask('Tin cổ tức của FPT');
 assert.equal(x.type,'news');assert.match(x.html,/FPT vừa công bố chia cổ tức/);
 assert.doesNotMatch(x.html,/FPT ký hợp đồng công nghệ|FRT chia cổ tức/);
 x=ask('Giá MBB hôm nay');
 assert.match(x.html,/MBB/);assert.doesNotMatch(x.html,/57\.900|57,900/);
 x=ask('FPT và MBB khác nhau như thế nào');
 assert.equal(x.type,'multiSymbol');assert.match(x.html,/không thể so sánh chính xác/i);
});
test('multiple concepts, unsupported forecasts and absent macro field fail safely',()=>{
 let x=ask('ROE và ROA là gì?');
 assert.equal(x.type,'multiConcept');assert.match(x.html,/ROE/);assert.match(x.html,/ROA/);
 x=ask('Dự báo T+3 cho FPT');
 assert.equal(x.type,'forecast');assert.match(x.html,/không có dự báo|không xuất ra con số/i);
 x=ask('CPI tháng này');
 assert.equal(x.type,'macro');assert.match(x.html,/chưa có chuỗi/i);assert.doesNotMatch(x.html,/999|8,3/);
 x=ask('Thời tiết Hà Nội ngày mai');
 assert.equal(x.type,'unknown');assert.doesNotMatch(x.html,/57\.900|57,900|ROE/);
});
