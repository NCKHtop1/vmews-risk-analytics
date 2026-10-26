const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const src=fs.readFileSync(path.join(root,'frontend/ownership-intelligence.js'),'utf8');
const build=fs.readFileSync(path.join(root,'scripts/build_cdn.py'),'utf8');
const now=new Date().toISOString();
function harness(){
 const host={innerHTML:''};const ticker={value:'MBB',addEventListener(){}};
 const document={getElementById:id=>id==='market-ownership-content'?host:id==='ticker'?ticker:null,addEventListener(){}};
 const window={listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}};
 const context={window,document,fetch:async()=>({ok:false}),AbortSignal,Date,Intl,URL,Math,Object,console};
 vm.createContext(context);vm.runInContext(src,context,{timeout:3000});
 return {api:context.window.FinOwnership,host,ticker,window};
}
const row={symbol:'MBB',person:'Nguyễn A',role:'Thành viên HĐQT',type:'registered_buy',disclosedAt:now,
 quantity:10000,sourceUrl:'https://www.hsx.vn/Modules/Cms/Web/News/123',holdingsAfter:350000};
test('ownership module ships in source and packaged CDN',()=>{
 assert.match(build,/ownership-intelligence\.js/);
 assert.ok(build.includes("(front / 'ownership-intelligence.js').read_text()"));
});
test('verified official disclosure shows registration, not a fake executed order',()=>{
 const {api,host}=harness();assert.equal(api._test.verified(row),true);
 api.setData({schemaVersion:1,status:'verified',events:[row]});
 assert.match(host.innerHTML,/Đăng ký mua/);
 assert.match(host.innerHTML,/350\.000/);
 assert.match(host.innerHTML,/www\.hsx\.vn/);
 assert.doesNotMatch(host.innerHTML,/Đã mua/);
 assert.doesNotMatch(host.innerHTML,/Lợi nhuận thực hiện/);
});
test('unverified or spoofed disclosures are rejected',()=>{
 const {api,host}=harness();
 const malicious={...row,person:'<img src=x onerror=alert(1)>',sourceUrl:'https://www.hsx.vn.evil.test/anything'};
 assert.equal(api._test.verified(malicious),false);
 assert.equal(api._test.safeSource('javascript:alert(1)'),"");
 api.setData({schemaVersion:1,status:'verified',events:[malicious]});
 assert.doesNotMatch(host.innerHTML,/<img/);
 assert.match(host.innerHTML,/Chưa có công bố được đối chiếu/);
});

test('primary issuer disclosure without reported quantity is shown without fabricated zeros',()=>{
 const {api,host}=harness();
 const result={
  symbol:'MBB',person:'Nguyễn Thị Thủy',role:'Người nội bộ',
  type:'reported_result',disclosedAt:'2026-10-07T12:00:00+07:00',
  title:'Báo cáo kết quả giao dịch cổ phiếu',
  quantity:null,holdingsAfter:null,
  sourceUrl:'https://www.mbbank.com.vn/chi-tiet/thong-bao/thong-bao/61/index?page=16'
 };
 assert.equal(api._test.verified(result),true);
 api.setData({schemaVersion:1,status:'verified',events:[result]});
 assert.match(host.innerHTML,/Nguyễn Thị Thủy/);
 assert.match(host.innerHTML,/Báo cáo kết quả/);
 assert.match(host.innerHTML,/www\.mbbank\.com\.vn/);
 assert.doesNotMatch(host.innerHTML,/>0<\/td>/);
 assert.doesNotMatch(host.innerHTML,/Đã bán/);
});
test('only verified MBB issuer domain is accepted; other symbols cannot spoof it',()=>{
 const {api}=harness();
 assert.equal(api._test.safeSource('https://www.mbbank.com.vn/chi-tiet/x','MBB').startsWith('https:'),true);
 assert.equal(api._test.safeSource('https://www.mbbank.com.vn/chi-tiet/x','HPG'),'');
 assert.equal(api._test.safeSource('https://www.mbbank.com.vn.evil.test/x','MBB'),'');
 assert.equal(api._test.safeSource('http://www.mbbank.com.vn/x','MBB'),'');
});
test('verified registration is not presented as an executed trade and numberless executed trade is rejected',()=>{
 const {api,host}=harness();
 const announcement={
  symbol:'MBB',person:'Nguyễn Thị Thủy',role:'Người nội bộ',
  type:'reported_registration',disclosedAt:now,quantity:null,
  sourceUrl:'https://www.mbbank.com.vn/chi-tiet/thong-bao/thong-bao/61/index?page=16'
 };
 assert.equal(api._test.verified(announcement),true);
 assert.equal(api._test.verified({...announcement,type:'executed_sell'}),false);
 api.setData({schemaVersion:1,status:'verified',events:[announcement]});
 assert.match(host.innerHTML,/Thông báo giao dịch/);
 assert.doesNotMatch(host.innerHTML,/Đã bán/);
});

test('VN100 ownership profile, shareholders, leadership and price reaction render together',()=>{
 const {api,host,ticker}=harness();
 ticker.value='FPT';
 const event={
  id:'VCI-test',symbol:'FPT',person:'Nguyễn Văn Khoa',role:'Người nội bộ / cổ đông lớn',
  title:'Nguyễn Văn Khoa - Đăng kí Mua 428,368 FPT',type:'registered_buy',
  disclosedAt:now,quantity:428368,sourceUrl:'https://iq.vietcap.com.vn/api/iq-insight-service/v1/events?ticker=FPT',
  sourcePublisher:'Vietcap',reaction:{status:'observed',returnPct:{'1':1.2,'3':3.4,'5':2.1,'10':null},signal:'TANG_KEM_THANH_KHOAN',volumeRatio3:1.4}
 };
 api.setData({schemaVersion:2,status:'ok',checkedAt:now,universe:{expected:100,processed:100},
  symbols:{FPT:{profile:{asOf:'2025-12-31',
   source:'https://kbbuddywts.kbsec.com.vn/iis-server/investment/stockinfo/profile/FPT?l=1',sourceName:'KBS',
   ownership:[{name:'CĐ nội bộ',percentage:16.05,asOf:'2025-12-31'}],
   shareholders:[{name:'SCIC',percentage:5.67,asOf:'2025-12-31'}],
   leaders:[{name:'Trương Gia Bình',role:'Chủ tịch HĐQT'}]},
   events:[event],sourceStatus:{profile:'ok',events:'ok',market:'ok'}}}
 });
 assert.match(host.innerHTML,/Cơ cấu sở hữu/);
 assert.match(host.innerHTML,/Cổ đông lớn/);
 assert.match(host.innerHTML,/Ban lãnh đạo/);
 assert.match(host.innerHTML,/16,05%/);
 assert.match(host.innerHTML,/Trương Gia Bình/);
 assert.match(host.innerHTML,/428\.368/);
 assert.match(host.innerHTML,/\+3,4%/);
 assert.match(host.innerHTML,/T\+10/);
 assert.match(host.innerHTML,/Đã đăng ký/);
 assert.match(host.innerHTML,/Tăng · KL cao/);
 assert.doesNotMatch(host.innerHTML,/Đã mua/);
});

test('changing ticker through application event switches ownership view without reopening the tab',async()=>{
 const {api,host,ticker,window}=harness();
 const mk=(symbol,person)=>({
  symbol,person,role:'Người nội bộ',type:'registered_buy',
  disclosedAt:now,quantity:500,sourceUrl:'https://www.hsx.vn/Modules/Cms/Web/News/123'
 });
 api.setData({schemaVersion:2,checkedAt:now,symbols:{
  MBB:{profile:null,events:[mk('MBB','Nguyễn A')],sourceStatus:{events:'ok'}},
  FPT:{profile:null,events:[mk('FPT','Trương B')],sourceStatus:{events:'ok'}}
 }});
 assert.match(host.innerHTML,/Nguyễn A/);
 window.listeners['finquery:symbol-change']({detail:{symbol:'FPT'}});
 ticker.value='FPT';
 await new Promise(resolve=>setImmediate(resolve));
 assert.match(host.innerHTML,/FPT · Sở hữu/);
 assert.match(host.innerHTML,/Trương B/);
 assert.doesNotMatch(host.innerHTML,/Nguyễn A/);
});
