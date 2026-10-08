'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('forecast-final-v12.js','utf8');
const start=source.indexOf('function renderForecastCards(B,z)');
const end=source.indexOf('\nfunction ',start+4);
assert.ok(start>=0&&end>start,'renderForecastCards function extractable');
const actual=source.slice(start,end);
const valid=q=>Boolean(q?.priceValidated)&&Number.isFinite(q.expectedPrice)&&Number.isFinite(q.q20Price)&&Number.isFinite(q.q80Price);
const format=x=>Number.isFinite(x)?x.toLocaleString('vi-VN'):'—';
function scenario(close) {
 const box={innerHTML:'',rows:[],replaceChildren(){this.rows=[];},append(row){this.rows.push(row);}};
 const document={createElement(){return {className:'',tabIndex:-1,innerHTML:'',setAttribute(){}};},querySelectorAll(){return [];}};
 const horizons=Object.fromEntries([1,2,3,4,5].map(n=>[n,{
   priceValidated:true,expectedPrice:50000+n*100,q20Price:49000,q80Price:52000,
   targetDate:'2026-10-13',probUp:0.6,expectedAbsReturn:0.03
 }]));
 const z={symbol:'FPT',horizons,close,staleForecast:false,date:'2026-10-08'};
 const B={dash:{asOf:'2026-10-08'},model:{horizons:{}}};
 const pointMove=(q,base)=>!valid(q)||base===null||base===undefined||base===''||!Number.isFinite(Number(base))||Number(base)<=0
   ?null:(()=>{const delta=q.expectedPrice-Number(base),rate=delta/Number(base);return {target:q.expectedPrice,delta,rate,direction:delta>=0?'TĂNG':'GIẢM',tone:'good'};})();
 const context={
    B,z,document,$:()=>box,h:(x,n)=>x.horizons[n]||{},
    primaryHorizon:()=>3,forecastAvailable:valid,forecastUsableForDecision:()=>true,forecastTargetState:()=> 'FUTURE',
    finite:x=>x!==null&&x!==undefined&&x!==''&&Number.isFinite(Number(x)),
    price:format,pct:(x,d=1)=>(Number(x)*100).toFixed(d)+'%',esc:String,
    pointMove,pupText:()=>'',last:null,renderDrivers(){},renderEventImpact(){},draw(){},
 };
 vm.runInNewContext(actual+'\nrenderForecastCards(B,z);',context);
 return box.rows;
}
for(const close of [null,undefined,'',0]){
 const rows=scenario(close);
 assert.equal(rows.length,5,'all forecast cards must render without throwing');
 assert.ok(rows.every(r=>r.innerHTML.includes('THIẾU GIÁ THAM CHIẾU')),'must mark missing reference on each horizon');
 assert.ok(rows.every(r=>!r.innerHTML.includes('Infinity')&&!r.innerHTML.includes('NaN')),'no invented percentage');
}
const rows=scenario(59700);
assert.equal(rows.length,5);
assert.ok(rows.every(r=>r.innerHTML.includes('Giá dự báo trung tâm')),'valid close preserves forecast target UI');
assert.ok(rows.every(r=>!r.innerHTML.includes('THIẾU GIÁ THAM CHIẾU')),'valid close not downgraded');
// Also test production pointMove itself (not just a test double).
const moveStart=source.indexOf('function pointMove(q,close)');
const moveEnd=source.indexOf('\nfunction ',moveStart+4);
assert.ok(moveStart>=0&&moveEnd>moveStart,'pointMove function extractable');
const realPointMove=vm.runInNewContext(source.slice(moveStart,moveEnd)+'\npointMove;',{
   forecastAvailable:valid,finite:x=>x!==null&&x!==undefined&&x!==''&&Number.isFinite(Number(x))
});
const horizon={priceValidated:true,expectedPrice:50000,q20Price:49000,q80Price:51000};
assert.equal(realPointMove(horizon,null),null);
assert.equal(realPointMove(horizon,0),null);
assert.equal(realPointMove(horizon,-1),null);
assert.ok(Number.isFinite(realPointMove(horizon,59700).rate));
console.log('FORECAST_MISSING_REFERENCE_PRICE_REGRESSION_PASS 9 cases');
