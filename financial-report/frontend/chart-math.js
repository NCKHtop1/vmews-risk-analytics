(function(root){'use strict';
const steps={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600};
const intraday=t=>Object.hasOwn(steps,t);
function validBar(b){return b&&['open','high','low','close','volume'].every(k=>Number.isFinite(b[k]))&&Math.min(b.open,b.high,b.low,b.close)>0&&b.volume>=0&&b.low<=Math.min(b.open,b.close)&&b.high>=Math.max(b.open,b.close);}
function cleanBars(rows,minute){const out=new Map();for(const b of rows||[]){if(!validBar(b))continue;const time=minute?(typeof b.time==='number'?b.time:Date.parse(b.time)/1000):b.time;if(minute?!Number.isFinite(time):!/^\d{4}-\d{2}-\d{2}$/.test(time))continue;out.set(time,{time,open:b.open,high:b.high,low:b.low,close:b.close,volume:b.volume});}return [...out.values()].sort((a,b)=>a.time<b.time?-1:a.time>b.time?1:0);}
function bucket(time,tf){if(intraday(tf))return Math.floor((Number(time)+7*3600)/steps[tf])*steps[tf]-7*3600;if(tf==='1d')return time;const d=new Date(time+'T12:00:00Z');if(tf==='1w'){d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);return d.toISOString().slice(0,10);}return time.slice(0,7)+'-01';}
function aggregate(bars,tf){const out=[];for(const b of bars){const t=bucket(b.time,tf),last=out.at(-1);if(last?.time===t){last.high=Math.max(last.high,b.high);last.low=Math.min(last.low,b.low);last.close=b.close;last.volume+=b.volume;}else out.push({...b,time:t});}return out;}
function period(p,key,fallback){const v=Number(p?.[key]);return Number.isFinite(v)&&v>0?Math.round(v):fallback;}
function average(bars,i,n,key='close'){if(i<n-1)return null;let s=0;for(let j=i-n+1;j<=i;j++)s+=bars[j][key];return s/n;}
function sum(bars,i,n,key){if(i<n-1)return null;let s=0;for(let j=i-n+1;j<=i;j++)s+=typeof key==='function'?key(bars[j],j):bars[j][key];return s;}
function weighted(bars,i,n,key='close'){if(i<n-1)return null;let s=0,w=0;for(let j=0;j<n;j++){const weight=j+1;s+=bars[i-n+1+j][key]*weight;w+=weight;}return s/w;}
function extremes(bars,i,n){if(i<n-1)return null;let high=-Infinity,low=Infinity;for(let j=i-n+1;j<=i;j++){high=Math.max(high,bars[j].high);low=Math.min(low,bars[j].low);}return{high,low};}
function trueRange(bars,i){const b=bars[i];if(!i)return b.high-b.low;const pc=bars[i-1].close;return Math.max(b.high-b.low,Math.abs(b.high-pc),Math.abs(b.low-pc));}
function atrAt(bars,i,n,prev){if(i<n-1)return null;if(i===n-1){let s=0;for(let j=0;j<=i;j++)s+=trueRange(bars,j);return s/n;}return Number.isFinite(prev)?((prev*(n-1)+trueRange(bars,i))/n):null;}
function dxAt(bars,i,n){if(i<n)return null;let tr=0,plus=0,minus=0;for(let j=i-n+1;j<=i;j++){tr+=trueRange(bars,j);const up=bars[j].high-bars[j-1].high,down=bars[j-1].low-bars[j].low;plus+=up>down&&up>0?up:0;minus+=down>up&&down>0?down:0;}if(!tr)return 0;const p=100*plus/tr,m=100*minus/tr;return p+m===0?0:100*Math.abs(p-m)/(p+m);}
function adxAt(bars,i,n){if(i<2*n-1)return null;let s=0,c=0;for(let j=i-n+1;j<=i;j++){const d=dxAt(bars,j,n);if(Number.isFinite(d)){s+=d;c++;}}return c===n?s/n:null;}
function stochasticK(bars,i,n){const e=extremes(bars,i,n);if(!e)return null;const span=e.high-e.low;return span?100*(bars[i].close-e.low)/span:50;}
function cciAt(bars,i,n){if(i<n-1)return null;const vals=[];for(let j=i-n+1;j<=i;j++)vals.push((bars[j].high+bars[j].low+bars[j].close)/3);const ma=vals.reduce((a,b)=>a+b,0)/n,md=vals.reduce((a,b)=>a+Math.abs(b-ma),0)/n;return md?((vals.at(-1)-ma)/(.015*md)):0;}
function mfiAt(bars,i,n){if(i<n)return null;let pos=0,neg=0;for(let j=i-n+1;j<=i;j++){const tp=(bars[j].high+bars[j].low+bars[j].close)/3,prev=(bars[j-1].high+bars[j-1].low+bars[j-1].close)/3,mf=tp*bars[j].volume;if(tp>prev)pos+=mf;else if(tp<prev)neg+=mf;}if(!neg)return pos?100:50;const ratio=pos/neg;return 100-100/(1+ratio);}
function cmfAt(bars,i,n){if(i<n-1)return null;let mfv=0,vol=0;for(let j=i-n+1;j<=i;j++){const b=bars[j],span=b.high-b.low,mult=span?((b.close-b.low)-(b.high-b.close))/span:0;mfv+=mult*b.volume;vol+=b.volume;}return vol?mfv/vol:0;}
function point(bars,i,p,prev){
 const b=bars[i],c=b.close;
 const smaN=period(p,'sma',20),emaN=period(p,'ema',20),wmaN=period(p,'wma',20),vwmaN=period(p,'vwma',20),rsiN=period(p,'rsi',14),fastN=period(p,'fast',12),slowN=period(p,'slow',26),signalN=period(p,'signal',9),bbN=period(p,'bb',20),vmaN=period(p,'vma',20),atrN=period(p,'atr',14),adxN=period(p,'adx',14),stochN=period(p,'stoch',14),stochDN=period(p,'stochSignal',3),cciN=period(p,'cci',20),rocN=period(p,'roc',10),willrN=period(p,'willr',14),mfiN=period(p,'mfi',14),cmfN=period(p,'cmf',20),superN=period(p,'supertrend',10);
 const ema=(n,key)=>prev&&Number.isFinite(prev[key])?prev[key]+2/(n+1)*(c-prev[key]):c;
 const r={time:b.time,sma:average(bars,i,smaN),ema:ema(emaN,'ema'),wma:weighted(bars,i,wmaN),vma:average(bars,i,vmaN,'volume'),fast:ema(fastN,'fast'),slow:ema(slowN,'slow')};
 if(i>=vwmaN-1){let pv=0,v=0;for(let j=i-vwmaN+1;j<=i;j++){pv+=bars[j].close*bars[j].volume;v+=bars[j].volume;}r.vwma=v?pv/v:null;}else r.vwma=null;
 const delta=i?c-bars[i-1].close:0,g=Math.max(0,delta),l=Math.max(0,-delta);
 if(i===rsiN){let gain=0,loss=0;for(let j=1;j<=i;j++){const d=bars[j].close-bars[j-1].close;gain+=Math.max(0,d);loss+=Math.max(0,-d);}r.gain=gain/rsiN;r.loss=loss/rsiN;}
 else if(i>rsiN&&prev){r.gain=(prev.gain*(rsiN-1)+g)/rsiN;r.loss=(prev.loss*(rsiN-1)+l)/rsiN;}
 r.rsi=i<rsiN?null:r.loss===0?(r.gain===0?50:100):100-100/(1+r.gain/r.loss);
 r.macd=r.fast-r.slow;r.signal=prev&&Number.isFinite(prev.signal)?prev.signal+2/(signalN+1)*(r.macd-prev.signal):r.macd;r.hist=r.macd-r.signal;
 r.middle=average(bars,i,bbN);if(r.middle!==null){let v=0;for(let j=i-bbN+1;j<=i;j++)v+=(bars[j].close-r.middle)**2;const sd=Math.sqrt(v/bbN)*Number(p?.deviation||2);r.upper=r.middle+sd;r.lower=r.middle-sd;}else{r.upper=r.lower=null;}
 r.atr=atrAt(bars,i,atrN,prev?.atr);
 r.adx=adxAt(bars,i,adxN);
 r.stoch=stochasticK(bars,i,stochN);if(i>=stochN+stochDN-2){let s=0,ok=true;for(let j=i-stochDN+1;j<=i;j++){const k=stochasticK(bars,j,stochN);if(!Number.isFinite(k)){ok=false;break;}s+=k;}r.stochSignal=ok?s/stochDN:null;}else r.stochSignal=null;
 r.cci=cciAt(bars,i,cciN);
 r.roc=i>=rocN&&bars[i-rocN].close?100*(c/bars[i-rocN].close-1):null;
 const wr=extremes(bars,i,willrN);r.willr=wr&&wr.high!==wr.low?-100*(wr.high-c)/(wr.high-wr.low):wr?0:null;
 r.obv=i===0?0:(prev?.obv||0)+(c>bars[i-1].close?b.volume:c<bars[i-1].close?-b.volume:0);
 r.mfi=mfiAt(bars,i,mfiN);
 r.cmf=cmfAt(bars,i,cmfN);
 const factor=Number.isFinite(Number(p?.supertrendFactor))?Number(p.supertrendFactor):3,atrSuper=atrAt(bars,i,superN,prev?.atrSuper);r.atrSuper=atrSuper;
 if(Number.isFinite(atrSuper)){const mid=(b.high+b.low)/2,basicUpper=mid+factor*atrSuper,basicLower=mid-factor*atrSuper,prevClose=i?bars[i-1].close:c;const finalUpper=!prev||!Number.isFinite(prev.stUpper)||basicUpper<prev.stUpper||prevClose>prev.stUpper?basicUpper:prev.stUpper;const finalLower=!prev||!Number.isFinite(prev.stLower)||basicLower>prev.stLower||prevClose<prev.stLower?basicLower:prev.stLower;r.stUpper=finalUpper;r.stLower=finalLower;if(!prev||!Number.isFinite(prev.supertrend))r.supertrend=c<=finalUpper?finalUpper:finalLower;else if(prev.supertrend===prev.stUpper)r.supertrend=c<=finalUpper?finalUpper:finalLower;else r.supertrend=c>=finalLower?finalLower:finalUpper;r.supertrendDir=c>=r.supertrend?1:-1;}else{r.stUpper=r.stLower=r.supertrend=null;r.supertrendDir=0;}
 return r;
}
function indicators(bars,p){const out=[];for(let i=0;i<bars.length;i++)out.push(point(bars,i,p,out[i-1]));return out;}
const api={intraday,validBar,cleanBars,bucket,aggregate,point,indicators,average,weighted,trueRange,dxAt};root.FinChartMath=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
