'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
global.window=globalThis;
require('../frontend/knowledge-base.js');
const K=globalThis.FinQueryKnowledge;
const P=require('../frontend/question-policy.js');
function type(q){return P.route(q,K.search(q,12));}
test('complete glossary: every canonical concept remains reachable',()=>{
 const errors=[];
 for(const c of K.concepts){
  for(const suffix of ['',' là gì?',' nghĩa là gì?']){
   const q=c.title+suffix,found=K.find(q);
   if(found?.id!==c.id)errors.push(q+' => '+(found?.id||'null')+' expected '+c.id);
  }
 }
 assert.deepEqual(errors,[],errors.join('\n'));
});
test('finance and market: natural language queries route by intent, not answer text length',()=>{
 const examples=[
  ['Tài sản ngắn hạn là gì?','concept'],
  ['Tài sản ngắn hạn và nợ ngắn hạn là gì?','multiConcept'],
  ['ROE và ROA là gì?','multiConcept'],
  ['ROE và ROA của FPT năm 2025 là bao nhiêu?','multiMetric'],
  ['So sánh ROE và ROA năm 2024 và 2025','multiMetric'],
  ['NIM MBB năm 2025 bao nhiêu?','metric'],
  ['Doanh thu FPT năm 2025 bao nhiêu?','metric'],
  ['Tiền và tương đương tiền của FPT quý 2/2025 là bao nhiêu?','metric'],
  ['So sánh kỳ gần nhất với kỳ trước và cùng kỳ','compare'],
  ['Giá FPT hôm nay?','movement'],
  ['Vì sao mã này tăng hoặc giảm trong phiên hôm nay?','movement'],
  ['FPT giảm bao nhiêu % hôm nay?','movement'],
  ['Tín hiệu MACD RSI hiện tại','technical'],
  ['Tin mới nhất về FPT','news'],
  ['Tin cổ tức của FPT','news'],
  ['Sự kiện doanh nghiệp MBB','news'],
  ['Dự báo T+3 cổ phiếu FPT','forecast'],
  ['Lãi suất qua đêm hôm nay bao nhiêu?','macro'],
  ['CPI tháng này','macro'],
  ['Những rủi ro định lượng chính hiện tại là gì?','risk'],
  ['Phân tích sức khỏe tài chính doanh nghiệp này','financial'],
  ['Lập hồ sơ nghiên cứu chuyên sâu FPT','memo'],
  ['Thời tiết Hà Nội ngày mai','unknown'],
  ['Làm thơ về hoa sen','unknown'],
  ['Công thức nấu phở Hà Nội','concept'],
 ];
 const failures=[];
 for(const [q,expected]of examples){const actual=type(q);if(actual!==expected)failures.push(q+': '+actual+' vs '+expected);}
 assert.deepEqual(failures,[],failures.join('\n'));
});
test('unrecognized definitions must never resolve to a bank or unrelated technical term',()=>{
 for(const q of ['abcxyz là gì','những điều khó hiểu trên sao Hỏa','cách làm bún chả','tôi không hỏi về TOI','tin tình yêu','tài sản lạ không có trong từ điển là gì','tôi đang hỏi về tài sản']){
  assert.equal(K.find(q),null,q);
 }
 for(const q of ['TOI là gì','Tổng thu nhập hoạt động là gì','NIM là gì','CAR là gì','CIR là gì','tài sản ngắn hạn là gì']){
  assert.ok(K.find(q),q);
 }
});
test('metric row retrieval requires meaningful coverage, never 1 generic token',()=>{
 const data={sections:[{id:'BS',rows:[
  {label:'Tổng tài sản',values:{'2025':40}},
  {label:'Tài sản ngắn hạn',values:{'2025':20}},
  {label:'Nợ ngắn hạn',values:{'2025':10}},
  {label:'Doanh thu thuần',values:{'2025':30}}
 ]}]};
 assert.equal(P.searchRows('tài sản ngắn hạn năm 2025',data)[0]?.row.label,'Tài sản ngắn hạn');
 assert.equal(P.searchRows('doanh thu năm 2025',data)[0]?.row.label,'Doanh thu thuần');
 assert.equal(P.searchRows('tài sản',data).length,0);
 assert.equal(P.searchRows('abcxyz',data).length,0);
});
test('company news never swaps tickers or unrelated subjects',()=>{
 const items=[
  {title:'FPT thông báo chia cổ tức',symbols:['FPT'],publishedAt:'2026-10-09'},
  {title:'FPT hợp đồng công nghệ mới',symbols:['FPT'],publishedAt:'2026-10-09'},
  {title:'FRT thông báo chia cổ tức',symbols:['FRT'],publishedAt:'2026-10-09'}
 ];
 assert.deepEqual(P.selectNews('tin cổ tức FPT',items,{symbol:'FPT',companyOnly:true}).map(x=>x.title),['FPT thông báo chia cổ tức']);
 assert.equal(P.selectNews('tin FRT',items,{symbol:'FPT',companyOnly:true}).length,0);
 assert.equal(P.selectNews('tin mới nhất FPT',items,{symbol:'FPT',companyOnly:true}).length,2);
});
test('market snapshots are bounded by stock identity, freshness and timestamp',()=>{
 const now=new Date('2026-10-09T12:00:00.000Z');
 const q={symbol:'FPT',price:57900,reference:59700,sourceTime:'2026-10-09T07:45:00.000Z'};
 assert.equal(P.priceQuality(q,'FPT','Giá FPT hôm nay',now).usable,true);
 assert.equal(P.priceQuality(q,'MBB','Giá MBB hôm nay',now).usable,false);
 assert.equal(P.priceQuality({...q,sourceTime:'2026-10-07T07:45:00Z'},'FPT','Giá FPT hôm nay',now).usable,false);
 assert.equal(P.priceQuality({...q,sourceTime:null},'FPT','Giá FPT hôm nay',now).usable,false);
 assert.equal(P.priceQuality({...q,price:0},'FPT','Giá FPT hôm nay',now).usable,false);
});
test('date periods are parsed without rolling an unavailable requested period',()=>{
 assert.deepEqual(P.periodInfo('quý 2/2025').quarters,['2025-Q2']);
 assert.deepEqual(P.periodInfo('Q2 2025').quarters,['2025-Q2']);
 assert.deepEqual(P.periodInfo('2025-Q2').quarters,['2025-Q2']);
 assert.deepEqual(P.periodInfo('2024 và 2025').years,['2024','2025']);
});
test('implementation contracts prevent silent keyword fallback and missing-to-zero conversion',()=>{
 const fs=require('node:fs'),path=require('node:path');
 const src=fs.readFileSync(path.join(__dirname,'../frontend/research-ai.js'),'utf8');
 assert.match(src,/const QP=window.FinQueryQuestionPolicy/);
 assert.match(src,/function metricHTML\(/);
 assert.match(src,/function multiConceptHTML\(/);
 assert.match(src,/function newsHTML\(/);
 assert.match(src,/function forecastHTML\(/);
 assert.match(src,/v===null\|\|v===undefined\|\|String\(v\)\.trim\(\)===''/);
 assert.ok(!src.includes('concept=K.find?.(question)||ranked[0]?.c||null'));
});
