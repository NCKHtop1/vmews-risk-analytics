(function(root){'use strict';
const steps={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600};
const intraday=t=>Object.hasOwn(steps,t);
function validBar(b){return b&&['open','high','low','close','volume'].every(k=>Number.isFinite(b[k]))&&Math.min(b.open,b.high,b.low,b.close)>0&&b.volume>=0&&b.low<=Math.min(b.open,b.close)&&b.high>=Math.max(b.open,b.close);}
function cleanBars(rows,minute){const out=new Map();for(const b of rows||[]){if(!validBar(b))continue;const time=minute?(typeof b.time==='number'?b.time:Date.parse(b.time)/1000):b.time;if(minute?!Number.isFinite(time):!/^\d{4}-\d{2}-\d{2}$/.test(time))continue;out.set(time,{time,open:b.open,high:b.high,low:b.low,close:b.close,volume:b.volume});}return [...out.values()].sort((a,b)=>a.time<b.time?-1:a.time>b.time?1:0);}
function bucket(time,tf){if(intraday(tf))return Math.floor((Number(time)+7*3600)/steps[tf])*steps[tf]-7*3600;if(tf==='1d')return time;const d=new Date(time+'T12:00:00Z');if(tf==='1w'){d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);return d.toISOString().slice(0,10);}return time.slice(0,7)+'-01';}
function aggregate(bars,tf){const out=[];for(const b of bars){const t=bucket(b.time,tf),last=out.at(-1);if(last?.time===t){last.high=Math.max(last.high,b.high);last.low=Math.min(last.low,b.low);last.close=b.close;last.volume+=b.volume;}else out.push({...b,time:t});}return out;}
function average(bars,i,n,key='close'){if(i<n-1)return null;let s=0;for(let j=i-n+1;j<=i;j++)s+=bars[j][key];return s/n;}
function point(bars,i,p,prev){const b=bars[i],c=b.close,ema=(n,key)=>prev?prev[key]+2/(n+1)*(c-prev[key]):c;
 const r={time:b.time,sma:average(bars,i,p.sma),ema:ema(p.ema,'ema'),fast:ema(p.fast,'fast'),slow:ema(p.slow,'slow'),vma:average(bars,i,p.vma,'volume')};
 const delta=i?c-bars[i-1].close:0,g=Math.max(0,delta),l=Math.max(0,-delta);
 if(i===p.rsi){let gain=0,loss=0;for(let j=1;j<=i;j++){const d=bars[j].close-bars[j-1].close;gain+=Math.max(0,d);loss+=Math.max(0,-d);}r.gain=gain/p.rsi;r.loss=loss/p.rsi;}
 else if(i>p.rsi){r.gain=(prev.gain*(p.rsi-1)+g)/p.rsi;r.loss=(prev.loss*(p.rsi-1)+l)/p.rsi;}
 r.rsi=i<p.rsi?null:r.loss===0?(r.gain===0?50:100):100-100/(1+r.gain/r.loss);
 r.macd=r.fast-r.slow;r.signal=prev?prev.signal+2/(p.signal+1)*(r.macd-prev.signal):r.macd;r.hist=r.macd-r.signal;
 r.middle=average(bars,i,p.bb);if(r.middle!==null){let v=0;for(let j=i-p.bb+1;j<=i;j++)v+=(bars[j].close-r.middle)**2;const sd=Math.sqrt(v/p.bb)*p.deviation;r.upper=r.middle+sd;r.lower=r.middle-sd;}
 return r;
}
function indicators(bars,p){const out=[];for(let i=0;i<bars.length;i++)out.push(point(bars,i,p,out[i-1]));return out;}
const api={intraday,validBar,cleanBars,bucket,aggregate,point,indicators};root.FinChartMath=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
