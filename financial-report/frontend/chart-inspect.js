/* FinQuery unified SVG inspection: real observations only, independent of chart re-renders. */
(function(root){'use strict';
 if(typeof document==='undefined'||typeof document.addEventListener!=='function')return;
 const SVG='http://www.w3.org/2000/svg',chartSelector='svg[data-fq-inspect]',pointSelector='[data-fq-point]';
 let current=null,tooltip=null,guide=null,focusDot=null,stickyTouch=false,lastPointer=null,frame=0;
 function findSvg(target){return typeof target?.closest==='function'?target.closest(chartSelector):null;}
 function readPoint(el){
  if(!el)return null;
  const x=Number(el.getAttribute('data-fq-x')??el.getAttribute('cx'));
  const y=Number(el.getAttribute('data-fq-y')??el.getAttribute('cy'));
  const value=el.getAttribute('data-fq-value'),label=el.getAttribute('data-fq-label');
  if(!Number.isFinite(x)||!Number.isFinite(y)||!value||!label)return null;
  return{el,x,y,value,label,unit:el.getAttribute('data-fq-unit')||'',series:el.getAttribute('data-fq-series')||''};
 }
 function points(svg){
  return [...svg.querySelectorAll(pointSelector)].map(readPoint).filter(Boolean);
 }
 function screen(svg,p,matrix){
  if(!matrix)return null;
  return{x:matrix.a*p.x+matrix.c*p.y+matrix.e,y:matrix.b*p.x+matrix.d*p.y+matrix.f};
 }
 function elements(){
  if(tooltip)return;
  tooltip=document.createElement('div');tooltip.className='fq-chart-tooltip';tooltip.setAttribute('role','tooltip');tooltip.hidden=true;
  const heading=document.createElement('div');heading.className='fq-chart-tooltip-series';
  const label=document.createElement('div');label.className='fq-chart-tooltip-label';
  const value=document.createElement('strong');value.className='fq-chart-tooltip-value';
  tooltip.append(heading,label,value);document.body.appendChild(tooltip);
 }
 function clear(){
  if(current?.point?.el?.classList)current.point.el.classList.remove('fq-chart-point-active');
  if(guide)guide.setAttribute('visibility','hidden');
  if(focusDot)focusDot.setAttribute('visibility','hidden');
  if(tooltip)tooltip.hidden=true;
  current=null;stickyTouch=false;
 }
 function decorate(svg){
  if(guide?.ownerSVGElement===svg&&focusDot?.ownerSVGElement===svg)return;
  guide=document.createElementNS(SVG,'line');
  guide.setAttribute('class','fq-chart-guide');guide.setAttribute('pointer-events','none');guide.setAttribute('visibility','hidden');
  focusDot=document.createElementNS(SVG,'circle');
  focusDot.setAttribute('class','fq-chart-cursor');focusDot.setAttribute('r','5.5');
  focusDot.setAttribute('pointer-events','none');focusDot.setAttribute('visibility','hidden');
  svg.append(guide,focusDot);
 }
 function select(svg,point,index,sticky=false){
  if(!svg||!point||!svg.isConnected)return;
  elements();
  if(current?.point?.el&&current.point.el!==point.el)current.point.el.classList.remove('fq-chart-point-active');
  if(current?.svg&&current.svg!==svg)clear();
  decorate(svg);
  const matrix=svg.getScreenCTM?.(),pos=screen(svg,point,matrix);
  if(!pos)return;
  const vb=svg.viewBox?.baseVal,h=vb?.height||200,ymin=Number(svg.getAttribute('data-fq-top')),
    ymax=Number(svg.getAttribute('data-fq-bottom'));
  guide.setAttribute('x1',String(point.x));guide.setAttribute('x2',String(point.x));
  guide.setAttribute('y1',String(Number.isFinite(ymin)?ymin:10));
  guide.setAttribute('y2',String(Number.isFinite(ymax)?ymax:h-28));
  guide.setAttribute('visibility','visible');
  focusDot.setAttribute('cx',String(point.x));focusDot.setAttribute('cy',String(point.y));
  focusDot.setAttribute('stroke',point.el.getAttribute('data-fq-color')||svg.getAttribute('data-fq-color')||'#3565c7');
  focusDot.setAttribute('visibility','visible');
  point.el.classList.add('fq-chart-point-active');
  const children=tooltip.children;
  children[0].textContent=point.series||'';
  children[0].hidden=!point.series;
  children[1].textContent=point.label;
  children[2].textContent=point.value+(point.unit?' '+point.unit:'');
  tooltip.hidden=false;
  const r=tooltip.getBoundingClientRect(),w=window.innerWidth||document.documentElement.clientWidth,
    vh=window.innerHeight||document.documentElement.clientHeight;
  const left=Math.min(Math.max(8,pos.x+12),Math.max(8,w-r.width-8));
  const above=pos.y-r.height-14,top=above>=8?above:Math.min(Math.max(8,pos.y+13),Math.max(8,vh-r.height-8));
  tooltip.style.left=left+'px';tooltip.style.top=top+'px';
  current={svg,point,index};stickyTouch=sticky;
 }
 function selectNearest(svg,x,y,sticky=false){
  const list=points(svg),matrix=svg.getScreenCTM?.();
  if(!list.length||!matrix)return;
  let best=null,bestIndex=-1,bestScore=Infinity;
  list.forEach((p,i)=>{
   const v=screen(svg,p,matrix);
   if(!v)return;
   // Prioritize the same date / time, then choose the nearest plotted series.
   const score=Math.abs(v.x-x)+Math.abs(v.y-y)*.48;
   if(score<bestScore){best=p;bestScore=score;bestIndex=i;}
  });
  select(svg,best,bestIndex,sticky);
 }
 document.addEventListener('pointermove',event=>{
  if(event.pointerType==='touch')return;
  const svg=findSvg(event.target);if(!svg){if(!stickyTouch)clear();return;}
  lastPointer={svg,x:event.clientX,y:event.clientY};
  if(frame)return;
  if(typeof requestAnimationFrame==='function'){
   frame=requestAnimationFrame(()=>{frame=0;const p=lastPointer;if(p?.svg?.isConnected)selectNearest(p.svg,p.x,p.y);});
  }else selectNearest(svg,event.clientX,event.clientY);
 },{passive:true});
 document.addEventListener('pointerdown',event=>{
  const svg=findSvg(event.target);
  if(!svg){clear();return;}
  if(event.pointerType==='touch'||event.pointerType==='pen')selectNearest(svg,event.clientX,event.clientY,true);
 },{passive:true});
 document.addEventListener('pointerout',event=>{
  if(stickyTouch)return;
  const svg=findSvg(event.target);
  if(svg&&findSvg(event.relatedTarget)!==svg)clear();
 },{passive:true});
 document.addEventListener('focusin',event=>{
  const svg=findSvg(event.target);if(!svg)return;
  const list=points(svg);if(!list.length)return;
  const selected=event.target.closest?.(pointSelector),idx=selected?list.findIndex(p=>p.el===selected):list.length-1;
  select(svg,list[Math.max(0,idx)],Math.max(0,idx));
 });
 document.addEventListener('focusout',event=>{
  if(current?.svg&&!current.svg.contains(event.relatedTarget))clear();
 });
 document.addEventListener('keydown',event=>{
  const svg=findSvg(event.target);
  if(!svg||!['ArrowRight','ArrowLeft','Home','End','Escape'].includes(event.key))return;
  event.preventDefault();
  if(event.key==='Escape'){clear();return;}
  const list=points(svg);if(!list.length)return;
  const old=current?.svg===svg?current.index:list.length-1;
  const index=event.key==='Home'?0:event.key==='End'?list.length-1:
   Math.max(0,Math.min(list.length-1,old+(event.key==='ArrowRight'?1:-1)));
  select(svg,list[index],index);
 });
 document.addEventListener('scroll',clear,true);
 window.addEventListener?.('resize',clear);
 root.FinChartInspect={points,clear};
})(window);
