(function(){
 'use strict';
 // Progressive enhancement for the existing platform navigation.
 // The links retain their original href/data-platform-view handlers.
 const header=document.querySelector('.header');
 const nav=header?.querySelector('nav[aria-label="Điều hướng nền tảng"]');
 const toggle=document.getElementById('finquery-nav-toggle');
 if(!header||!nav||!toggle)return;
 const media=window.matchMedia('(max-width:850px)');
 const close=(focus=false)=>{
  header.classList.remove('finquery-nav-open');
  toggle.setAttribute('aria-expanded','false');
  toggle.setAttribute('aria-label','Mở danh mục FinQuery');
  if(focus&&media.matches)toggle.focus({preventScroll:true});
 };
 const open=()=>{
  if(!media.matches)return;
  header.classList.add('finquery-nav-open');
  toggle.setAttribute('aria-expanded','true');
  toggle.setAttribute('aria-label','Đóng danh mục FinQuery');
 };
 toggle.addEventListener('click',()=>{
  if(header.classList.contains('finquery-nav-open'))close();
  else open();
 });
 nav.addEventListener('click',event=>{
  if(event.target.closest('a'))close();
 });
 document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&header.classList.contains('finquery-nav-open'))close(true);
 });
 document.addEventListener('pointerdown',event=>{
  if(media.matches&&header.classList.contains('finquery-nav-open')&&!header.contains(event.target))close();
 });
 if(media.addEventListener)media.addEventListener('change',()=>close());
 else if(media.addListener)media.addListener(()=>close());
 close();
 // The chart's native details menu remains keyboard/touch accessible and
 // closes after a command, outside pointer interaction, or Escape.
 const chartTools=document.getElementById('chart-advanced-tools');
 if(chartTools){
  const summary=chartTools.querySelector('summary');
  chartTools.addEventListener('click',event=>{
   if(event.target.closest('button'))chartTools.open=false;
  });
  document.addEventListener('pointerdown',event=>{
   if(chartTools.open&&!chartTools.contains(event.target))chartTools.open=false;
  });
  document.addEventListener('keydown',event=>{
   if(event.key==='Escape'&&chartTools.open){
    chartTools.open=false;
    summary?.focus({preventScroll:true});
   }
  });
 }
})();
