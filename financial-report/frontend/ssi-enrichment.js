(function(root){'use strict';
// Optional SSI MCP enrichment. Never receives or stores an SSI OAuth token.
const api='/api/ssi-auth', researchApi='/api/ssi-mcp';
const state={enabled:false,connected:false,checkedAt:0,pending:null,mounted:false};
const qs=(sel)=>document.querySelector(sel);
function availableHost(){
 try{return location.protocol==='https:'&&!/(^|\.)github\.io$/i.test(location.hostname);}catch{return false;}
}
async function init(force=false){
 if(!availableHost())return state;
 if(!force&&state.checkedAt&&Date.now()-state.checkedAt<60000)return state;
 if(state.pending)return state.pending;
 state.pending=(async()=>{
  try{
   const r=await fetch(api+'?op=status',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(3500)});
   if(!r.ok)return state;
   const answer=await r.json();
   state.enabled=answer?.enabled===true;state.connected=state.enabled&&answer?.connected===true;
  }catch{state.enabled=false;state.connected=false;}
  finally{state.checkedAt=Date.now();state.pending=null;}
  paint();return state;
 })();
 return state.pending;
}
function ready(){return state.enabled&&state.connected;}
function kindFor(question){
 const s=String(question||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').toLowerCase();
 if(/tin tuc|tin moi|cong bo|thong bao/.test(s))return'news';
 if(/co tuc|su kien|dai hoi|gdkhq/.test(s))return'events';
 if(/cung nganh|so sanh nganh|doi thu/.test(s))return'peers';
 if(/gioi thieu|ho so cong ty|nganh nghe/.test(s))return'profile';
 return'indicators';
}
async function query(question,symbol){
 if(!ready())return null;
 const ticker=String(symbol||'').trim().toUpperCase();
 if(!/^[A-Z]{3}$/.test(ticker))return null;
 const kind=kindFor(question);
 try{
  const url=researchApi+'?symbol='+encodeURIComponent(ticker)+'&kind='+encodeURIComponent(kind);
  const r=await fetch(url,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(22000)});
  if(r.status===401){state.connected=false;paint();return null;}
  if(!r.ok)return null;
  const data=await r.json();
  if(data.status!=='ok'||data.symbol!==ticker||!Array.isArray(data.rows)||!data.rows.length)return null;
  return{source:'SSI MCP',symbol:ticker,kind,retrievedAt:data.retrievedAt||null,periodWarning:'Financial indicators relate to the stated year and quarter; retrievedAt is not the report publication date.',rows:data.rows.slice(0,12)};
 }catch{return null;}
}
function paint(){
 const host=qs('#finquery-ssi-connect'),status=qs('#finquery-ssi-status'),connect=qs('#finquery-ssi-login'),logout=qs('#finquery-ssi-logout');
 if(!host)return;
 host.hidden=!state.enabled;
 if(status)status.textContent=ready()?'Đã kết nối SSI · dữ liệu chỉ đọc':'Chưa kết nối SSI trên FinQuery';
 if(connect)connect.hidden=ready();
 if(logout)logout.hidden=!ready();
}
function mount(drawer,prompts){
 if(!availableHost()||!drawer)return;
 if(!qs('#finquery-ssi-connect')){
  const el=document.createElement('section');
  el.id='finquery-ssi-connect';el.className='dolphin-connect-card';el.hidden=true;
  el.innerHTML='<div class="dolphin-connect-head"><div><strong>SSI MCP · Bằng chứng doanh nghiệp</strong><small id="finquery-ssi-status">Đang kiểm tra kết nối…</small></div><div><button id="finquery-ssi-login" type="button">Kết nối SSI</button><button id="finquery-ssi-logout" type="button" hidden>Ngắt SSI</button></div></div>';
  drawer.insertBefore(el,prompts||drawer.firstChild);
  qs('#finquery-ssi-login')?.addEventListener('click',()=>{location.assign(api+'?op=start');});
  qs('#finquery-ssi-logout')?.addEventListener('click',async()=>{
   try{await fetch(api+'?op=logout',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'}});}catch{}
   state.checkedAt=0;await init(true);
  });
 }
 paint();void init(true);
}
root.FinSSI={init,ready,query,mount,kindFor,status:()=>({enabled:state.enabled,connected:state.connected})};
})(typeof window==='undefined'?globalThis:window);
