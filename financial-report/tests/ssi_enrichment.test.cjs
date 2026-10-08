'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),test=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../frontend/ssi-enrichment.js'),'utf8');
function load(host){
 let requests=0;
 const root={location:{protocol:'https:',hostname:host},fetch:async()=>{requests++;return{ok:false}},document:{querySelector:()=>null}};
 root.window=root;root.globalThis=root;
 vm.createContext(root);vm.runInContext(source,root);
 return {root,requestCount:()=>requests};
}
test('SSI augmentation is disabled on GitHub Pages',async()=>{
 const x=load('nckhtop1.github.io');
 await x.root.FinSSI.init();
 assert.equal(x.root.FinSSI.ready(),false);
 assert.equal(x.requestCount(),0);
 assert.equal(await x.root.FinSSI.query('ROE SSI','SSI'),null);
});
test('SSI chooses the right tool for a question',()=>{
 const x=load('finquery-demo.vercel.app');
 assert.equal(x.root.FinSSI.kindFor('Tin tức mới nhất của FPT'),'news');
 assert.equal(x.root.FinSSI.kindFor('ROE quý gần nhất của MBB'),'indicators');
 assert.equal(x.root.FinSSI.kindFor('So sánh cùng ngành SSI'),'peers');
 assert.equal(x.root.FinSSI.kindFor('Cổ tức VIC'),'events');
});
