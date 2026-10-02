const TV_URL = 'https://scanner.tradingview.com/vietnam/scan';

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store, max-age=0');
}

function symbolList(req) {
  const raw = String(req.query?.symbols || req.query?.symbol || 'FPT').toUpperCase();
  return [...new Set(raw.split(',').map(x => x.trim()).filter(x => /^[A-Z0-9]{2,5}$/.test(x)))].slice(0, 12);
}

async function fetchBounded(url, options = {}, timeoutMs = 5500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function tradingView(symbols) {
  const tickers = symbols.flatMap(symbol => ['HOSE', 'HNX', 'UPCOM'].map(exchange => `${exchange}:${symbol}`));
  const response = await fetchBounded(TV_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'User-Agent': 'Mozilla/5.0 SoluTION.AI/1.0',
    },
    body: JSON.stringify({
      symbols: { tickers, query: { types: [] } },
      columns: ['close', 'change', 'volume', 'open', 'high', 'low'],
    }),
  }, 6000);
  if (!response.ok) throw new Error(`TradingView HTTP ${response.status}`);
  const payload = await response.json();
  const fetchedAt = new Date().toISOString();
  const out = {};
  for (const row of payload?.data || []) {
    const full = String(row?.s || '');
    const [exchange, symbol] = full.split(':');
    const d = row?.d || [];
    const price = Number(d[0]);
    if (!symbols.includes(symbol) || !Number.isFinite(price) || price <= 0 || out[symbol]) continue;
    out[symbol] = {
      symbol,
      exchange,
      price,
      changePct: Number.isFinite(Number(d[1])) ? Number(d[1]) : null,
      volume: Number.isFinite(Number(d[2])) ? Number(d[2]) : null,
      open: Number.isFinite(Number(d[3])) ? Number(d[3]) : null,
      high: Number.isFinite(Number(d[4])) ? Number(d[4]) : null,
      low: Number.isFinite(Number(d[5])) ? Number(d[5]) : null,
      source: 'TradingView direct',
      sourceMode: 'solution_ai_direct',
      observedAt: fetchedAt,
    };
  }
  return out;
}

async function yahooOne(symbol) {
  const encoded = encodeURIComponent(symbol + '.VN');
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encoded}?range=1d&interval=1m&includePrePost=false&events=div%2Csplits`;
  const response = await fetchBounded(url, {
    headers: { 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 SoluTION.AI/1.0' },
  }, 5500);
  if (!response.ok) throw new Error(`Yahoo HTTP ${response.status}`);
  const payload = await response.json();
  const result = payload?.chart?.result?.[0];
  const stamps = result?.timestamp || [];
  const quote = result?.indicators?.quote?.[0] || {};
  for (let i = stamps.length - 1; i >= 0; i -= 1) {
    const price = Number(quote.close?.[i]);
    if (!Number.isFinite(price) || price <= 0) continue;
    const reference = Number(result?.meta?.chartPreviousClose);
    return {
      symbol,
      exchange: result?.meta?.exchangeName || null,
      price,
      changePct: Number.isFinite(reference) && reference > 0 ? (price / reference - 1) * 100 : null,
      volume: Number.isFinite(Number(quote.volume?.[i])) ? Number(quote.volume[i]) : null,
      open: Number.isFinite(Number(quote.open?.[i])) ? Number(quote.open[i]) : null,
      high: Number.isFinite(Number(quote.high?.[i])) ? Number(quote.high[i]) : null,
      low: Number.isFinite(Number(quote.low?.[i])) ? Number(quote.low[i]) : null,
      source: 'Yahoo Finance fallback',
      sourceMode: 'solution_ai_fallback',
      observedAt: new Date(Number(stamps[i]) * 1000).toISOString(),
    };
  }
  throw new Error('Yahoo returned no intraday price');
}

export default async function handler(req, res) {
  cors(res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'GET') return res.status(405).json({ status: 'error', error: 'METHOD_NOT_ALLOWED' });

  const symbols = symbolList(req);
  if (!symbols.length) return res.status(400).json({ status: 'error', error: 'INVALID_SYMBOL' });

  const startedAt = Date.now();
  const errors = [];
  let quotes = {};
  try {
    quotes = await tradingView(symbols);
  } catch (error) {
    errors.push(`TradingView: ${error?.message || error}`);
  }

  const missing = symbols.filter(symbol => !quotes[symbol]);
  if (missing.length) {
    const fallback = await Promise.allSettled(missing.map(yahooOne));
    fallback.forEach((result, index) => {
      const symbol = missing[index];
      if (result.status === 'fulfilled') quotes[symbol] = result.value;
      else errors.push(`Yahoo ${symbol}: ${result.reason?.message || result.reason}`);
    });
  }

  const coverage = Object.keys(quotes).length;
  if (!coverage) {
    return res.status(502).json({
      status: 'error',
      error: 'SOLUTION_AI_LIVE_UNAVAILABLE',
      requested: symbols.length,
      coverage: 0,
      fetchedAt: new Date().toISOString(),
      errors: errors.slice(0, 8),
    });
  }

  return res.status(200).json({
    status: coverage === symbols.length ? 'ok' : 'partial',
    scope: 'solution-ai',
    requested: symbols.length,
    coverage,
    fetchedAt: new Date().toISOString(),
    latencyMs: Date.now() - startedAt,
    quotes,
    errors: errors.slice(0, 8),
  });
}
