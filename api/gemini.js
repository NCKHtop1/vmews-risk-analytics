import { groundedJson, geminiConfigured, GeminiConfigError, schemas } from '../lib/gemini-provider.mjs';

const SYMBOL_RE = /^[A-Z0-9]{1,8}$/;

function send(res, status, body) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  return res.status(status).json(body);
}

function marketPrompt() {
  return `You are the live external data adapter for VMEWS, a Vietnam market-risk research system.
Use Google Search grounding and return ONLY verified, current market observations in the requested JSON schema.
Focus on the latest COMPLETED Vietnam trading session, not an unfinished intraday bar.
Collect VN-Index level, daily percent change, volume and breadth when verifiable, plus USD/VND, DXY, US 10Y yield, VIX and Brent.
Use null for any number you cannot verify from search evidence. Never invent a value. Keep summary factual and concise.`;
}

function newsPrompt(symbol) {
  return `Search for material, recent news about Vietnam-listed stock ${symbol}.
Prioritize exchange/regulator/company disclosures and reputable financial reporting. De-duplicate repeated stories.
Return up to 10 items. Treat rumors as low confidence and say so in the summary. Do not invent dates, publishers, events or numbers.
Sentiment is the likely directional information tone for the company, not a buy/sell recommendation.`;
}

function stockPrompt(symbol) {
  return `Search current verified information for Vietnam-listed stock ${symbol}.
Return the latest completed-session price/change when verifiable and the newest reported fundamentals requested by the schema.
Use null whenever a value cannot be verified. Do not synthesize historical OHLCV and do not produce investment advice.
The riskContext field should explain material current facts in neutral risk-management language.`;
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return send(res, 405, { error: 'METHOD_NOT_ALLOWED' });
  if (!geminiConfigured()) {
    return send(res, 503, {
      error: 'GEMINI_API_KEY_MISSING',
      message: 'Set GEMINI_API_KEY in the server environment before enabling Gemini live data.',
      configured: false,
    });
  }

  const mode = String(req.query?.mode || 'market').toLowerCase();
  const symbol = String(req.query?.symbol || '').trim().toUpperCase();
  try {
    let result;
    if (mode === 'market') {
      result = await groundedJson({ input: marketPrompt(), schema: schemas.market });
    } else if (mode === 'news') {
      if (!SYMBOL_RE.test(symbol)) return send(res, 400, { error: 'INVALID_SYMBOL' });
      result = await groundedJson({ input: newsPrompt(symbol), schema: schemas.news });
    } else if (mode === 'stock') {
      if (!SYMBOL_RE.test(symbol)) return send(res, 400, { error: 'INVALID_SYMBOL' });
      result = await groundedJson({ input: stockPrompt(symbol), schema: schemas.stock });
    } else {
      return send(res, 400, { error: 'INVALID_MODE', allowed: ['market', 'news', 'stock'] });
    }

    return send(res, 200, {
      provider: 'Gemini API',
      grounding: 'Google Search',
      fetchedAt: new Date().toISOString(),
      ...result,
    });
  } catch (error) {
    const status = error instanceof GeminiConfigError ? 503 : 502;
    return send(res, status, {
      error: 'GEMINI_LIVE_DATA_FAILED',
      message: error?.message || 'Gemini request failed',
    });
  }
}
