export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=900, stale-while-revalidate=3600');

  const range = ['1y','5y','max'].includes(String(req.query?.range)) ? String(req.query.range) : '5y';
  const rangeMap = { '1y':'1y', '5y':'5y', 'max':'max' };
  const symbol = '%5EVNINDEX';
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?range=${rangeMap[range]}&interval=1d&events=history&includeAdjustedClose=true`;

  try {
    const upstream = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 VMEWS/1.0',
        'Accept': 'application/json,text/plain,*/*'
      }
    });
    if (!upstream.ok) throw new Error(`Upstream HTTP ${upstream.status}`);
    const json = await upstream.json();
    const result = json?.chart?.result?.[0];
    const ts = result?.timestamp || [];
    const q = result?.indicators?.quote?.[0] || {};
    const rows = ts.map((t,i)=>({
      date: new Date(t*1000).toISOString().slice(0,10),
      open: q.open?.[i],
      high: q.high?.[i],
      low: q.low?.[i],
      close: q.close?.[i],
      volume: q.volume?.[i] || 0
    })).filter(r=>Number.isFinite(r.close) && r.close>0);
    if (rows.length < 10) throw new Error('Insufficient market rows');
    return res.status(200).json({
      source: 'Yahoo Finance chart adapter · ^VNINDEX',
      symbol: '^VNINDEX',
      range,
      fetchedAt: new Date().toISOString(),
      rows
    });
  } catch (error) {
    return res.status(502).json({
      error: 'LIVE_FEED_UNAVAILABLE',
      message: error?.message || 'Unable to fetch live market data',
      fallback: '/data/fallback-market.json'
    });
  }
}
