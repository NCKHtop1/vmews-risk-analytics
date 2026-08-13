(()=>{
'use strict';
const U={};
U.clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
U.mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:0;
U.sd=a=>{if(a.length<2)return 0;const m=U.mean(a);return Math.sqrt(a.reduce((s,x)=>s+(x-m)*(x-m),0)/(a.length-1))};
U.quantile=(a,p)=>{const z=a.filter(Number.isFinite).slice().sort((x,y)=>x-y);if(!z.length)return 0;const q=U.clamp(p,0,1)*(z.length-1),i=Math.floor(q),j=Math.ceil(q);return i===j?z[i]:z[i]*(j-q)+z[j]*(q-i)};
U.fmt=(x,d=2)=>Number.isFinite(+x)?new Intl.NumberFormat('en-US',{maximumFractionDigits:d}).format(+x):'—';
U.pct=(x,d=1)=>Number.isFinite(+x)?`${(+x*100).toFixed(d)}%`:'—';
U.signAcc=(y,p)=>y.length?y.reduce((s,v,i)=>s+((v>=0)===(p[i]>=0)?1:0),0)/y.length:0;
U.metrics=(y,p)=>{const e=y.map((v,i)=>v-p[i]),mae=U.mean(e.map(Math.abs)),mse=U.mean(e.map(x=>x*x)),sse=e.reduce((q,x)=>q+x*x,0),sse0=y.reduce((q,x)=>q+x*x,0);return{n:y.length,mae,rmse:Math.sqrt(mse),r2:sse0>0?1-sse/sse0:null,direction:U.signAcc(y,p)}};
window.VMEWSForecastUtils=U;
})();
