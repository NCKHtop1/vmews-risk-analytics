const assert=require('node:assert/strict');
global.window=globalThis;
require('../frontend/knowledge-base.js');
const K=globalThis.FinQueryKnowledge;
assert.ok(K,'knowledge base should load');
assert.equal(K.find('ROA là gì?').id,'roa');
assert.equal(K.find('asset turnover là gì?').id,'assetTurnover');
assert.equal(K.find('vong quay hang ton kho').id,'inventoryTurnover');
assert.equal(K.find('interst coverage').id,'interestCoverage');
assert.equal(K.find('willams r').id,'willr');
assert.equal(K.find('beta co phieu').id,'beta');
assert.equal(K.find('NIM ngân hàng').id,'nim');
assert.equal(K.find('nợ xấu NPL').id,'npl');
assert.equal(K.find('CIR ngân hàng').id,'cir');
assert.equal(K.find('loan to deposit LDR').id,'ldr');
assert.equal(K.find('bao phủ nợ xấu LLR').id,'llr');
assert.equal(K.find('CAR an toàn vốn').id,'car');
assert.equal(K.find('credit cost dự phòng').id,'creditCost');
assert.equal(K.find('cost of funds').id,'costOfFunds');
assert.ok(K.search('gia tri doanh nghiep ev ebitda',3).some(x=>x.c.id==='evEbitda'));
assert.match(K.explainLabel('Thuế thu nhập hoãn lại'),/khác với thời điểm tính thuế/i);
assert.match(K.explainLabel('Khấu hao lũy kế'),/khấu hao/i);
assert.match(K.explainLabel('Cho vay khách hàng'),/dư nợ tín dụng/i);

for(const [question,expected] of [
 ['tài sản ngắn hạn là gì','currentAssets'],
 ['Tai san ngan han la gi?','currentAssets'],
 ['current assets là gì','currentAssets'],
 ['tài sản dài hạn là gì','nonCurrentAssets'],
 ['nợ ngắn hạn là gì','currentLiabilities'],
 ['TOI là gì','toiBank'],
 ['tổng thu nhập hoạt động là gì','toiBank'],
 ['ROE là gì','roe'],
 ['NIM ngân hàng','nim'],
 ['tôi muốn biết ROE là gì','roe'],
]) assert.equal(K.find(question)?.id,expected,question);
for(const question of [
 'tôi đang hỏi về tài sản',
 'tài sản lạ không có trong từ điển là gì',
 'chào bạn hôm nay thế nào',
 'abcxyz là gì',
]) assert.equal(K.find(question),null,'must not invent a concept for: '+question);
const answerSource=require('node:fs').readFileSync(require('node:path').join(__dirname,'../frontend/research-ai.js'),'utf8');
assert.ok(!answerSource.includes('concept=K.find?.(question)||ranked[0]?.c||null'),'nearby results must not become definitions');
assert.ok(!answerSource.includes('const first=nearest[0].c'),'search fallback must not invent definitions');
const policySource=require('node:fs').readFileSync(require('node:path').join(__dirname,'../frontend/question-policy.js'),'utf8');
assert.match(policySource,/function selectNews\(/,'news selection must be topic and symbol aware');
assert.match(answerSource,/QP\?\.selectNews/,'research AI must use shared verified news ranking');

console.log('knowledge-base tests passed');