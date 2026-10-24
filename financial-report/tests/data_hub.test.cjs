const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'data-hub.html'),'utf8');
const home=fs.readFileSync(path.join(root,'frontend','index.html'),'utf8');
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);

function fakeElement(tag='div'){
  return {
    tagName:tag.toUpperCase(),textContent:'',className:'',children:[],disabled:false,attrs:{},
    appendChild(item){this.children.push(item);return item;},
    replaceChildren(...items){this.children=items;},
    addEventListener(name,fn){this['on_'+name]=fn;},
    setAttribute(k,v){this.attrs[k]=v;},
  };
}
async function boot(data,failed=false){
  const elements=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,fakeElement());return elements.get(id);};
  const document={
    getElementById:get,
    createElement:fakeElement,
  };
  let fetches=0;
  const fetch=async url=>{
    fetches++;
    if(failed)throw new Error('network timeout');
    assert.ok(String(url).startsWith('https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/macro.json?hub='));
    return {ok:true,json:async()=>data};
  };
  const ctx={document,fetch,AbortSignal,Date,Intl,Number,Object,Array,String,Math,RegExp,console};
  vm.createContext(ctx);for(const script of scripts)vm.runInContext(script,ctx,{timeout:3000});
  for(let i=0;i<16;i++)await Promise.resolve();
  return {get,fetches};
}
const fixture={
 checkedAt:'2026-10-23T01:58:17.251096+00:00',
 sources:[
  {id:'pmi',provider:'VBMA',status:'ok',url:'https://vbma.org.vn/source.csv'},
  {id:'money_supply',provider:'VBMA',status:'ok',url:'https://vbma.org.vn/source.csv'},
  {id:'credit_sector',provider:'VBMA',status:'ok',url:'https://vbma.org.vn/source.csv'},
  {id:'gdp_growth',provider:'VBMA',status:'ok',qualityStatus:'warning',url:'https://vbma.org.vn/source.csv'},
 ],
 datasets:{
   pmi:{source:'VBMA',status:'ok',columns:['Cột 1','T8 2026','T9 2026'],rows:[{'Cột 1':'PMI','T8 2026':49.8,'T9 2026':51.9}]},
   money_supply:{source:'VBMA',status:'ok',columns:['Cột 1','M2 (tỷ VND)'],rows:[{'Cột 1':'T6 2026','M2 (tỷ VND)':20400000},{'Cột 1':'T7 2026','M2 (tỷ VND)':20455644}]},
   credit_sector:{source:'VBMA',status:'ok',columns:['Cột 1','Tổng dư nợ'],rows:[{'Cột 1':'T7 2026','Tổng dư nợ':20262110}]},
   gdp_growth:{source:'VBMA',status:'ok',qualityStatus:'warning',columns:['Cột 1','Q3 2026'],rows:[{'Cột 1':'GDP','Q3 2026':9.95}]},
 }
};
test('entrypoint and page are linked, accessible and responsive',()=>{
 assert.match(home,/finquery\.info\.vn\/financial-report\/data-hub\.html/);
 assert.match(html,/<html lang="vi">/);
 assert.match(html,/name="viewport"/);
 assert.match(html,/aria-live="polite"/);
 assert.match(html,/@media\(max-width:620px\)/);
 assert.match(html,/\/financial-report\/index\.html/);
});
test('official derivatives data show publication period, not a live signal',()=>{
 assert.match(html,/39\.543 hợp đồng/);
 assert.match(html,/203 hợp đồng/);
 assert.match(html,/09\/2026/);
 assert.match(html,/07\/10\/2026/);
 assert.match(html,/www\.gov\.hnx\.vn\/vi-vn\/chi-tiet-tin-60023563-0\.html/);
 assert.match(html,/không sử dụng như OI theo hợp đồng/i);
});
test('official NHNN ON never conflated with VBMA repo, no fake data',()=>{
 assert.match(html,/Liên ngân hàng ON/);
 assert.match(html,/không thay bằng benchmark repo/i);
 assert.match(html,/Chưa chứng nhận/);
 assert.doesNotMatch(html,/ON[^]*?3[.,]9\s*%/);
});
test('script parses and source URLs are fixed, not user-provided endpoints',()=>{
 assert.equal(scripts.length,1);
 assert.doesNotThrow(()=>new vm.Script(scripts[0]));
 assert.match(scripts[0],/financial-market-data\/market\//);
 assert.match(scripts[0],/AbortSignal\.timeout\(12000\)/);
 assert.doesNotMatch(scripts[0],/\.innerHTML\s*=/);
 assert.doesNotMatch(scripts[0],/localStorage|sessionStorage|DATABASE_URL|FINQUERY_SESSION_PEPPER/);
});
test('macro manifest populates latest periods and flags source warnings',async()=>{
 const {get,fetches}=await boot(fixture);
 assert.equal(fetches,1);
 assert.equal(get('metric-pmi').textContent,'51,9');
 assert.match(get('period-pmi').textContent,/T9 2026/);
 assert.equal(get('metric-m2').textContent,'20.455.644');
 assert.match(get('period-m2').textContent,/T7 2026/);
 assert.equal(get('metric-credit').textContent,'20.262.110');
 assert.equal(get('metric-count').textContent,'4/4');
 assert.match(get('macro-status').textContent,/1 nguồn cảnh báo/);
 assert.equal(get('quality-rows').children.length,4);
});
test('fetch failure fails closed with explicit empty data',async()=>{
 const {get,fetches}=await boot({},true);
 assert.equal(fetches,1);
 assert.equal(get('metric-pmi').textContent,'');
 assert.match(get('macro-status').textContent,/Không lấy được manifest mới/);
 assert.equal(get('refresh').disabled,false);
 assert.equal(get('quality-rows').children.length,1);
});

test('stock catalog is HOSE-only while derivative reports remain sourced from HNX',()=>{
 const companies=JSON.parse(fs.readFileSync(path.join(root,'data','companies.json'),'utf8'));
 assert.equal(companies.length,100);
 assert.ok(companies.every(x=>x.exchange==='HOSE'));
 assert.match(html,/không bổ sung cổ phiếu niêm yết HNX/);
 assert.match(html,/HNX chỉ là nguồn công bố chính thức của dữ liệu phái sinh/);
 assert.match(html,/VN30/);
 assert.match(html,/VN100/);
});
