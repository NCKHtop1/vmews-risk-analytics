(()=>{
'use strict';
const U=()=>window.VMEWSForecastUtils;
function logReturns(rows){const r=new Array(rows.length).fill(0);for(let i=1;i<rows.length;i++)r[i]=Math.log(rows[i].close/rows[i-1].close);return r}
function avg(a,i,w){return U().mean(a.slice(i-w+1,i+1))}
function vol(a,i,w){return U().sd(a.slice(i-w+1,i+1))}
function rsi(rows,i){let g=0,l=0;for(let k=i-13;k<=i;k++){const d=rows[k].close/rows[k-1].close-1;d>=0?g+=d:l-=d}const ag=g/14,al=l/14;if(al<1e-12)return 1;return 1-1/(1+ag/al)}
function vz(rows,i){const a=[];for(let k=i-20;k<i;k++){const v=+rows[k].volume||0;if(v>0)a.push(Math.log1p(v))}const cur=+rows[i].volume||0,s=U().sd(a);return a.length>=10&&cur>0&&s>1e-12?(Math.log1p(cur)-U().mean(a))/s:0}
function range(rows,i,w){const a=[];for(let k=i-w+1;k<=i;k++){const c=rows[k].close||1;a.push(((rows[k].high||c)-(rows[k].low||c))/c)}return U().mean(a)}
function build(rows,scoreHistory){const scores=new Map((scoreHistory||[]).map(x=>[x.date,+x.score])),rets=logReturns(rows),closes=rows.map(x=>x.close),feats=[];for(let i=60;i<rows.length;i++){const c=rows[i].close,x=[];for(let lag=0;lag<10;lag++)x.push(rets[i-lag]);for(const w of [3,5,10,20])x.push(Math.log(c/rows[i-w].close));for(const w of [5,10,20])x.push(vol(rets,i,w));for(const w of [5,10,20,50])x.push(c/avg(closes,i,w)-1);x.push(c/Math.max(...closes.slice(i-19,i+1))-1,c/Math.max(...closes.slice(i-59,i+1))-1,rsi(rows,i)-.5,vz(rows,i),range(rows,i,5));const s=scores.get(rows[i].date);if(!Number.isFinite(s))continue;x.push(s/100);const s5=scores.get(rows[i-5].date);x.push(Number.isFinite(s5)?(s-s5)/100:0);if(x.every(Number.isFinite))feats.push({i,date:rows[i].date,x,close:c})}return{feats,rets}}
function samples(rows,base,h){return base.feats.filter(f=>f.i+h<rows.length).map(f=>({...f,h,y:Math.log(rows[f.i+h].close/rows[f.i].close)}))}
window.VMEWSForecastFeatures={build,samples};
})();
