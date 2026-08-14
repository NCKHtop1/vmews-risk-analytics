import { groundedJson, geminiConfigured, schemas } from '../lib/gemini-provider.mjs';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=900');
  res.setHeader('X-Content-Type-Options', 'nosniff');

  if (!geminiConfigured()) {
    return res.status(503).json({
      error: 'GEMINI_API_KEY_MISSING',
      message: 'Gemini is the configured live provider, but GEMINI_API_KEY has not been added yet.',
      provider: 'Gemini API',
      fallback: '/data/fallback-market.json',
    });
  }

  try {
    const result = await groundedJson({
      schema: schemas.market,
      input: `Act as the VMEWS live market data adapter. Use Google Search grounding. Return the newest verified COMPLETED-session Vietnam market context: VN-Index close/change/volume/breadth and current USD/VND, DXY, US 10Y, VIX and Brent. Use null for unverifiable values. Never fabricate historical OHLCV.`,
    });
    return res.status(200).json({
      source: 'Gemini API · Google Search grounding',
      symbol: 'VNINDEX',
      fetchedAt: new Date().toISOString(),
      snapshot: result.data,
      citations: result.citations,
      model: result.model,
      interactionId: result.interactionId,
      rows: [],
      note: 'Long historical price series remain immutable repository research assets; Gemini is used only for external live context.',
    });
  } catch (error) {
    return res.status(502).json({
      error: 'GEMINI_LIVE_FEED_UNAVAILABLE',
      message: error?.message || 'Unable to fetch Gemini-grounded market context',
      provider: 'Gemini API',
      fallback: '/data/fallback-market.json',
    });
  }
}
