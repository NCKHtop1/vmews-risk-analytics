(()=>{
  const isCdnHost=location.hostname==='cdn.githubraw.com';
  if(!isCdnHost){
    window.__VMEWS_BACKEND__=location.origin;
    return;
  }
  const backend='https://vmews-risk-analytics-sojd.vercel.app';
  const nativeFetch=window.fetch.bind(window);
  window.fetch=(input,init)=>{
    const raw=typeof input==='string'?input:(input&&input.url?input.url:String(input));
    const u=new URL(raw,location.href);
    if(u.pathname==='/api/stocks2') return nativeFetch(backend+'/api/radar'+u.search,init);
    if(u.pathname==='/api/validate') return nativeFetch(backend+'/api/validate2'+u.search,init);
    return nativeFetch(input,init);
  };
  window.__VMEWS_BACKEND__=backend;
})();
