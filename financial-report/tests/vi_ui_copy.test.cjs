const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const read=n=>fs.readFileSync(path.join(root,'frontend',n),'utf8');
const html=read('index.html');
const visible=content=>String(content).replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'')
 .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi,'')
 .replace(/<!--[\s\S]*?-->/g,'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();
const rejected=/\bVBMA\b|FIXED INCOME|ALPHA INTELLIGENCE|Tài khoản thông thường chỉ xem|khi backend có dữ liệu|không đồng nghĩa cập nhật năm hiện tại|các kỳ không có số liệu được để trống|Tiệm cận điều kiện không đồng nghĩa|Strategy Builder & Screener|INDICATOR LIBRARY/i;
function liquid(){
 const nodes={};
 const get=id=>nodes[id]||(nodes[id]={id,clientWidth:640,innerHTML:'',textContent:'',disabled:false,addEventListener(){}});
 const context={window:{innerWidth:1280},document:{getElementById:get},AbortSignal,fetch:async()=>({ok:false}),Date,URL,Intl,Number,String,Math,console};
 vm.createContext(context);vm.runInContext(read('liquidity-derivatives.js'),context,{timeout:5000});
 return {api:context.window.FinLiquidityDerivatives,get};
}
test('user-facing HTML is Vietnamese-first; no named provider or developer commentary',()=>{
 const body=visible(html);
 assert.doesNotMatch(body,rejected);
 assert.match(body,/Trái phiếu/);
 assert.match(body,/Hoán đổi ngoại tệ/);
 assert.match(body,/Tín hiệu Alpha/);
 assert.match(body,/Trợ lý chiến lược/);
 assert.match(body,/Nhóm chính · Thanh khoản · Mở rộng/);
 assert.doesNotMatch(body,/Investment Ideas|Core · Liquid · Discovery/);
 assert.doesNotMatch(body,/Bollinger Rebound|Momentum hồi phục|Top Strategy|World Bank/);
});
test('fixed-income charts read verified values from the published curves schema',()=>{
 const {api,get}=liquid();
 const p={schemaVersion:1,asOf:'2026-10-23',interbank:{status:'unavailable',observations:[]},derivatives:{months:[]},
  vbmaSwap:{status:'unavailable',points:[],source:'https://vbma.org.vn/csv/markets/charts/vi/fx_swap_curve.csv'},
  curves:{gov_bond:{status:'verified',source:'https://vbma.org.vn/csv/markets/charts/vi/government_bond_yield.csv',
      licenseStatus:'source_attributed',unit:'%/năm',asOf:'2026-10-23',
      points:[{tenor:'1Y',value:3.538},{tenor:'2Y',value:3.642},{tenor:'5Y',value:4.282}]},
   fi_bond:{status:'unavailable',points:[]},short_benchmark:{status:'unavailable',points:[]}}};
 api.setData(p);
 const cards=get('money-vbma-curves').innerHTML;
 assert.match(cards,/3,538/);
 assert.match(cards,/23\/10\/2026/);
 assert.match(cards,/data-tenor-point="1Y"/);
 assert.equal((cards.match(/class="money-tenor-curve"/g)||[]).length,1);
 assert.doesNotMatch(visible(cards),rejected);
 assert.doesNotMatch(visible(get('money-swap').innerHTML),rejected);
 assert.doesNotMatch(visible(cards),/Nguồn chưa cung cấp đường cong|Nguồn đang theo dõi/);
 assert.equal((cards.match(/data-download-curve=/g)||[]).length,1);
 assert.match(cards,/data-download-curve="gov_bond"/,'Download the verified values displayed in the chart');
});
test('macro and Alpha copy no longer expose internal operations or lengthy explanations',()=>{
 for(const name of ['macro-dashboard.js','alpha-radar.js','ownership-intelligence.js','derivatives-market.js']){
  const src=read(name);
  assert.doesNotMatch(src,/Tài khoản thông thường chỉ xem|không đồng nghĩa cập nhật năm hiện tại|các kỳ không có số liệu được để trống|khi backend có dữ liệu|chưa có chuỗi kỳ hạn đã xác minh/i,name);
 }
 assert.doesNotMatch(read('macro.js'),/'VBMA · World Bank · '/);
 assert.doesNotMatch(read('liquidity-derivatives.js'),/'VBMA','Đường cong kỳ hạn'/);
});
