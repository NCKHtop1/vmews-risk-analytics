import importlib.util
import json
import pathlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).resolve().parents[1]
MARKET_PATH = ROOT / 'financial-report' / 'scripts' / 'refresh_market.py'
spec = importlib.util.spec_from_file_location('vmews_refresh_market_live', MARKET_PATH)
market = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market)

VN = timezone(timedelta(hours=7))
COMPANIES = json.loads((ROOT / 'financial-report' / 'data' / 'companies.json').read_text(encoding='utf-8'))


def _fast_request(url, payload=None, timeout=7):
    headers = {
        'User-Agent': 'FinQuery-live-fallback/1.0',
        'Accept': 'application/json, application/xml, text/xml, */*',
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers.update({
            'Content-Type': 'application/json',
            'Referer': 'https://trading.vietcap.com.vn/',
            'Origin': 'https://trading.vietcap.com.vn',
        })
    req = Request(url, data=data, headers=headers)
    with urlopen(req, timeout=timeout) as response:
        return response.read()


market.request = _fast_request


def _json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _live_news():
    current = datetime.now(timezone.utc)
    rows, sources = [], []
    workers = min(8, max(1, len(market.FEEDS)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(market._fetch_news_feed, publisher, url, COMPANIES, current)
            for publisher, url in market.FEEDS
        ]
        for future in as_completed(futures):
            items, source = future.result()
            rows.extend(items)
            sources.append(source)

    source_order = {url: i for i, (_, url) in enumerate(market.FEEDS)}
    sources.sort(key=lambda row: source_order.get(row.get('url'), 999))
    unique, titles = {}, set()
    for row in sorted(rows, key=lambda r: r.get('publishedAt') or '', reverse=True):
        try:
            published = datetime.fromisoformat(str(row.get('publishedAt')).replace('Z', '+00:00'))
        except Exception:
            continue
        if published < current - timedelta(days=30):
            continue
        title_key = market.clean(row.get('title')).casefold()
        url = row.get('url')
        if not url or url in unique or title_key in titles:
            continue
        unique[url] = row
        titles.add(title_key)

    good = [x for x in sources if x.get('status') == 'ok']
    if not good:
        raise RuntimeError('All live RSS sources failed')
    return {
        'mode': 'news',
        'checkedAt': datetime.now(timezone.utc).isoformat(),
        'lastSuccessAt': datetime.now(timezone.utc).isoformat(),
        'status': 'ok',
        'liveFallback': True,
        'sources': sources,
        'items': list(unique.values())[:1200],
    }


def _session_active():
    local = datetime.now(VN)
    mins = local.hour * 60 + local.minute
    return local.weekday() < 5 and (
        9 * 60 <= mins <= 11 * 60 + 40 or
        12 * 60 + 55 <= mins <= 15 * 60 + 15
    )


def _live_quotes():
    symbols = [x['symbol'] for x in COMPANIES]
    collected = datetime.now(timezone.utc).isoformat()
    payload = json.loads(market.request(market.API + 'price/symbols/getList', {'symbols': symbols}))
    rows = market.normalize_board(payload, symbols, collected)

    stale = {}
    if _session_active():
        rows, stale = market.current_session_quotes(rows)
        if len(rows) < 90:
            raise RuntimeError(f'Current-session Vietcap coverage too low: {len(rows)}/100')
    if not rows:
        raise RuntimeError('No usable live quotes')

    return {
        'mode': 'quotes',
        'checkedAt': collected,
        'status': 'ok',
        'liveFallback': True,
        'source': 'Vietcap live API fallback',
        'providers': ['Vietcap'],
        'coverage': len(rows),
        'expected': len(symbols),
        'latestSourceTime': market.newest_source_time(rows),
        'staleRejected': len(stale),
        'quotes': rows,
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, cache='s-maxage=180, stale-while-revalidate=180'):
        raw = json.dumps(_json_safe(payload), ensure_ascii=False, separators=(',', ':')).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self._send(204, {}, 'no-store')

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        mode = str(query.get('mode', ['news'])[0]).lower()
        try:
            if mode == 'quotes':
                return self._send(200, _live_quotes(), 's-maxage=60, stale-while-revalidate=60')
            if mode == 'news':
                return self._send(200, _live_news(), 's-maxage=180, stale-while-revalidate=180')
            return self._send(400, {'error': 'INVALID_MODE', 'allowed': ['news', 'quotes']}, 'no-store')
        except Exception as exc:
            return self._send(503, {
                'error': 'LIVE_MARKET_FALLBACK_UNAVAILABLE',
                'mode': mode,
                'message': str(exc)[:300],
                'checkedAt': datetime.now(timezone.utc).isoformat(),
            }, 'no-store')
