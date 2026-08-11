(()=>{
  const DEFAULT_SYMBOLS='FPT,PNJ,VCB,HPG';
  let patched=false;
  const patchInput=()=>{
    if(patched)return;
    const el=document.getElementById('scanSymbols');
    if(el){el.value=DEFAULT_SYMBOLS;patched=true;}
  };
  const mo=new MutationObserver(()=>patchInput());
  mo.observe(document.documentElement,{childList:true,subtree:true});

  const loadRadar=()=>{
    if(document.querySelector('script[data-vmews-radar-loader]'))return;
    const s=document.createElement('script');
    s.src='./stock-radar-loader.js?v=20260811-bilingual-stable';
    s.dataset.vmewsRadarLoader='1';
    document.head.appendChild(s);
  };

  const warm=async()=>{
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(),30000);
    try{
      await fetch(`/api/stocks2?mode=scan&symbols=${encodeURIComponent(DEFAULT_SYMBOLS)}&t=${Date.now()}`,{cache:'no-store',signal:ctrl.signal});
    }catch(_){
      // The visible radar still loads even if prewarm fails.
    }finally{
      clearTimeout(timer);
      loadRadar();
    }
  };
  warm();
})();