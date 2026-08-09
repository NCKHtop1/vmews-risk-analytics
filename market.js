const allowedRanges = new Set(['1y','5y','10y','max']);

function toRows(result){
  const ts=result.timestamp||[];
  const q=(result.indicators&&result.indicators.quote&&result.indicators.quote[0])||{};
  return ts.map((t,i)=>({
    date:new Date(t*1000).toISOString().slice(0,10),
    open:q.open?.[i], high:q.high?.[i], low:q.low?.[i], close:q.close?.[i], volume:q.volume?.[i]
  })).filter(r=>Number.isFinite(r.close)&&r.close>0);
}

module.exports = async function handler(req,res){
  const range=allowedRanges.has(req.query?.range)?req.query.range:'5y';
  const symbol='^VNINDEX.VN';
  const endpoint=`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=${range}&interval=1d&includePrePost=false&events=div%2Csplits`;
  try{
    const upstream=await fetch(endpoint,{headers:{'user-agent':'Mozilla/5.0 VMEWS/1.0','accept':'application/json'}});
    if(!upstream.ok) throw new Error(`Upstream status ${upstream.status}`);
    const json=await upstream.json();
    const result=json?.chart?.result?.[0];
    if(!result) throw new Error(json?.chart?.error?.description||'No chart result');
    const rows=toRows(result);
    if(rows.length<10) throw new Error('Insufficient data returned');
    res.setHeader('Cache-Control','s-maxage=300, stale-while-revalidate=900');
    res.status(200).json({
      source:'Yahoo Finance public chart endpoint',symbol,range,
      currency:result.meta?.currency||'VND',exchange:result.meta?.exchangeName||'HOSE',
      timezone:result.meta?.exchangeTimezoneName||'Asia/Ho_Chi_Minh',
      fetchedAt:new Date().toISOString(),rows
    });
  }catch(err){
    res.setHeader('Cache-Control','no-store');
    res.status(502).json({error:'LIVE_SOURCE_UNAVAILABLE',message:String(err?.message||err)});
  }
}
