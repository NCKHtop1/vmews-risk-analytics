(()=>{
'use strict';
const U=()=>window.VMEWSForecastUtils;
function stats(samples){const p=samples[0].x.length,mu=new Array(p).fill(0),ss=new Array(p).fill(0);for(const s of samples)for(let j=0;j<p;j++)mu[j]+=s.x[j];for(let j=0;j<p;j++)mu[j]/=samples.length;for(const s of samples)for(let j=0;j<p;j++){const d=s.x[j]-mu[j];ss[j]+=d*d}return{mu,sig:ss.map(v=>Math.sqrt(v/Math.max(1,samples.length-1))||1)}}
const zrow=(x,st)=>x.map((v,j)=>(v-st.mu[j])/st.sig[j]);
function solve(A,b){const n=A.length,M=A.map((r,i)=>r.slice().concat([b[i]]));for(let c=0;c<n;c++){let piv=c;for(let r=c+1;r<n;r++)if(Math.abs(M[r][c])>Math.abs(M[piv][c]))piv=r;if(Math.abs(M[piv][c])<1e-10)M[piv][c]+=1e-8;[M[c],M[piv]]=[M[piv],M[c]];const d=M[c][c]||1e-8;for(let j=c;j<=n;j++)M[c][j]/=d;for(let r=0;r<n;r++)if(r!==c){const q=M[r][c];if(Math.abs(q)<1e-14)continue;for(let j=c;j<=n;j++)M[r][j]-=q*M[c][j]}}return M.map(r=>r[n])}
function fit(samples,alpha){const st=stats(samples),p=samples[0].x.length,ym=U().mean(samples.map(s=>s.y)),A=Array.from({length:p},()=>new Array(p).fill(0)),b=new Array(p).fill(0);for(const s of samples){const z=zrow(s.x,st),y=s.y-ym;for(let j=0;j<p;j++){b[j]+=z[j]*y;for(let k=0;k<p;k++)A[j][k]+=z[j]*z[k]}}for(let j=0;j<p;j++)A[j][j]+=alpha;const beta=solve(A,b);return{type:'RIDGE',alpha,predict:x=>ym+zrow(x,st).reduce((q,v,j)=>q+v*beta[j],0)}}
window.VMEWSForecastRidge={fit};
})();
