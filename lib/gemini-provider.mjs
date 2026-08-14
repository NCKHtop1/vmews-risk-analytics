const API_URL = 'https://generativelanguage.googleapis.com/v1beta/interactions';
const DEFAULT_MODEL = process.env.GEMINI_MODEL || 'gemini-3.6-flash';

export class GeminiConfigError extends Error {
  constructor(message) {
    super(message);
    this.name = 'GeminiConfigError';
  }
}

export function geminiConfigured() {
  return Boolean(String(process.env.GEMINI_API_KEY || '').trim());
}

function parseJsonOutput(text) {
  const raw = String(text || '').trim();
  if (!raw) throw new Error('Gemini returned an empty structured response');
  const cleaned = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
  return JSON.parse(cleaned);
}

function walk(value, visit) {
  if (Array.isArray(value)) {
    for (const item of value) walk(item, visit);
    return;
  }
  if (!value || typeof value !== 'object') return;
  visit(value);
  for (const item of Object.values(value)) walk(item, visit);
}

export function extractCitations(payload) {
  const seen = new Set();
  const citations = [];
  walk(payload, (node) => {
    if (node.type !== 'url_citation') return;
    const url = String(node.url || node.uri || '').trim();
    if (!url || seen.has(url)) return;
    seen.add(url);
    citations.push({
      url,
      title: String(node.title || node.source || '').trim() || null,
    });
  });
  return citations;
}

export async function groundedJson({ input, schema, model = DEFAULT_MODEL, timeoutMs = 45000 }) {
  const key = String(process.env.GEMINI_API_KEY || '').trim();
  if (!key) {
    throw new GeminiConfigError('GEMINI_API_KEY is not configured');
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': key,
      },
      body: JSON.stringify({
        model,
        input,
        tools: [{ type: 'google_search' }],
        response_format: {
          type: 'text',
          mime_type: 'application/json',
          schema,
        },
      }),
      signal: controller.signal,
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload?.error?.message || payload?.message || `Gemini HTTP ${response.status}`;
      throw new Error(detail);
    }
    if (payload?.status && !['completed', 'incomplete'].includes(payload.status)) {
      throw new Error(`Gemini interaction status: ${payload.status}`);
    }

    const data = parseJsonOutput(payload.output_text);
    return {
      data,
      model,
      citations: extractCitations(payload),
      interactionId: payload.id || null,
      status: payload.status || 'completed',
    };
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error('Gemini request timed out');
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export const schemas = {
  market: {
    type: 'object',
    properties: {
      asOf: { type: 'string', description: 'ISO-8601 timestamp or date for the newest verified observations.' },
      sessionDate: { type: ['string', 'null'], description: 'Latest completed Vietnam market session date when verified.' },
      vnindex: {
        type: 'object',
        properties: {
          last: { type: ['number', 'null'] },
          changePct: { type: ['number', 'null'], description: 'Decimal return, e.g. -0.012 for -1.2%.' },
          volume: { type: ['number', 'null'] },
          breadthAdvancers: { type: ['integer', 'null'] },
          breadthDecliners: { type: ['integer', 'null'] },
        },
        required: ['last', 'changePct', 'volume', 'breadthAdvancers', 'breadthDecliners'],
      },
      macro: {
        type: 'object',
        properties: {
          usdVnd: { type: ['number', 'null'] },
          dxy: { type: ['number', 'null'] },
          us10y: { type: ['number', 'null'] },
          vix: { type: ['number', 'null'] },
          brent: { type: ['number', 'null'] },
        },
        required: ['usdVnd', 'dxy', 'us10y', 'vix', 'brent'],
      },
      summary: { type: 'string' },
    },
    required: ['asOf', 'sessionDate', 'vnindex', 'macro', 'summary'],
  },
  news: {
    type: 'object',
    properties: {
      asOf: { type: 'string' },
      symbol: { type: 'string' },
      items: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            headline: { type: 'string' },
            publisher: { type: 'string' },
            publishedAt: { type: ['string', 'null'] },
            sentiment: { type: 'string', enum: ['NEGATIVE', 'NEUTRAL', 'POSITIVE', 'MIXED'] },
            materiality: { type: 'string', enum: ['LOW', 'MEDIUM', 'HIGH'] },
            summary: { type: 'string' },
          },
          required: ['headline', 'publisher', 'publishedAt', 'sentiment', 'materiality', 'summary'],
        },
      },
      riskSummary: { type: 'string' },
    },
    required: ['asOf', 'symbol', 'items', 'riskSummary'],
  },
  stock: {
    type: 'object',
    properties: {
      asOf: { type: 'string' },
      symbol: { type: 'string' },
      quote: {
        type: 'object',
        properties: {
          last: { type: ['number', 'null'] },
          changePct: { type: ['number', 'null'] },
          sessionDate: { type: ['string', 'null'] },
        },
        required: ['last', 'changePct', 'sessionDate'],
      },
      fundamentals: {
        type: 'object',
        properties: {
          pe: { type: ['number', 'null'] },
          pb: { type: ['number', 'null'] },
          roe: { type: ['number', 'null'] },
          revenueGrowth: { type: ['number', 'null'] },
          profitGrowth: { type: ['number', 'null'] },
        },
        required: ['pe', 'pb', 'roe', 'revenueGrowth', 'profitGrowth'],
      },
      riskContext: { type: 'string' },
    },
    required: ['asOf', 'symbol', 'quote', 'fundamentals', 'riskContext'],
  },
};
