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
 const context={window:{},document,fetch:async()=>({ok:false}),AbortSignal,Date,Intl,URL,Math,Object,console};
 vm.createContext(context);vm.runInContext(src,context,{timeout:3000});
 return {api:context.window.FinOwnership,host,ticker};
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
 assert.match(host.innerHTML,/Chưa có bản ghi đã xác minh/);
});
