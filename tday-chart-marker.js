(()=>{
'use strict';
const MARKET='https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/main/data/market-scan.json';
const baseFetch=window.fetch.bind(window);
let marketPromise=null,timer=null;
const loadMarket=()=>marketPromise||(marketPromise=baseFetch(`${MARKET}?t=${Date.now()}`,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null));
const marketItem=(p,symbol)=>[...(p?.redList||[]),...(p?.yellowList||[]),...(p?.ranking||[])].find(x=>x.symbol===symbol)||null;
const ma=(rows,n)=>{let s=0;return rows.map((r,i)=>{s+=+r.close||0;if(i>=n)s-=+rows[i-n].close||0;return i>=n-1?s/n:null})};
function selectedRows(all,root){const active=root.querySelector('.chartTools button.active')?.dataset?.range||'1Y';const n=active==='6M'?126:active==='1Y'?252:active==='3Y'?756:99999;return all.slice(-Math.min(n,all.length))}
function svgEl(name,attrs={}){const el=document.createElementNS('http://www.w3.org/2000/svg',name);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,String(v));return el}
async function apply(){
  const detail=window.__VMEWS_LAST_DETAIL__,root=document.getElementById('investorChart');
  if(!detail||!root)return;
  const svg=root.querySelector('svg');if(!svg)return;
  const old=svg.querySelector('#tdayRiskMarker');if(old)old.remove();
  root.querySelectorAll('.tdayLegend').forEach(x=>x.remove());
  const p=await loadMarket();if(detail!==window.__VMEWS_LAST_DETAIL__)return;
  const m=marketItem(p,detail.symbol);if(!m||!['RED','YELLOW'].includes(m.status))return;
  const all=(detail.history||[]).filter(x=>Number.isFinite(+x.close)&&+x.close>0);if(all.length<2)return;
  const rows=selectedRows(all,root),offset=all.length-rows.length,s50=ma(all,50).slice(offset),s200=ma(all,200).slice(offset),closes=rows.map(x=>+x.close);
  const valid=[...closes,...s50.filter(Number.isFinite),...s200.filter(Number.isFinite)];let ymin=Math.min(...valid),ymax=Math.max(...valid);const pad=(ymax-ymin||ymax*.08||1)*.08;ymin-=pad;ymax+=pad;
  const W=1060,L=70,R=22,T=20,PRICE_B=328,PW=W-L-R,PH=PRICE_B-T,xx=L+PW,last=closes.at(-1),yy=T+(ymax-last)/(ymax-ymin)*PH;
  const fill=m.status==='RED'?'#dc8f8f':'#d7b06c',g=svgEl('g',{id:'tdayRiskMarker','data-status':m.status});
  g.appendChild(svgEl('line',{x1:xx,y1:T,x2:xx,y2:PRICE_B,stroke:fill,'stroke-width':2,opacity:.8,'stroke-dasharray':'5 4'}));
  g.appendChild(svgEl('circle',{cx:xx,cy:yy,r:7,fill,stroke:'#08141e','stroke-width':3}));
  const label=svgEl('text',{x:xx-8,y:Math.max(T+13,yy-12),'text-anchor':'end',fill,'font-size':11,'font-weight':800});label.textContent=`T ${m.status}`;g.appendChild(label);
  const hover=svg.querySelector('#chartHover');svg.insertBefore(g,hover||null);
  const legend=root.querySelector('.chartLegend');if(legend){const s=document.createElement('span');s.className='tdayLegend';s.innerHTML=`<i style="width:8px;height:8px;border-radius:50%;background:${fill}"></i>T-Day ${m.status} at latest completed EOD`;legend.appendChild(s)}
}
function schedule(){clearTimeout(timer);timer=setTimeout(()=>apply(),120)}
const mo=new MutationObserver(schedule);mo.observe(document.documentElement,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['class']});
window.addEventListener('load',schedule);setTimeout(schedule,500);
window.__VMEWS_TDAY_CHART_MARKER__=true;
})();
