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
FORECAST_DASHBOARD = ROOT / 'data' / 'forecast-dashboard-v12.json'


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


def _current_quote_day():
    """Current trading date once the market has opened, including the lunch break."""
    local = datetime.now(VN)
    mins = local.hour * 60 + local.minute
    return local.weekday() < 5 and 9 * 60 <= mins <= 15 * 60 + 15


def _strict_live_session():
    """Only the actual continuous trading windows require minute-level freshness."""
    local = datetime.now(VN)
    mins = local.hour * 60 + local.minute
    return local.weekday() < 5 and (
        9 * 60 <= mins <= 11 * 60 + 30 or
        13 * 60 <= mins <= 14 * 60 + 45
    )


def _forecast_symbols():
    """Use the published forecast universe instead of limiting live quotes to the old Core-100 list."""
    try:
        dashboard = json.loads(FORECAST_DASHBOARD.read_text(encoding='utf-8'))
        rows = dashboard.get('symbols') or {}
        symbols = [
            str(symbol).upper()
            for symbol, snapshot in rows.items()
            if isinstance(snapshot, dict)
            and snapshot.get('exchange') == 'HOSE'
            and snapshot.get('dataFreshness') == 'CURRENT'
        ]
        if len(symbols) >= 100:
            return sorted(set(symbols))
    except Exception:
        pass
    return sorted({str(x['symbol']).upper() for x in COMPANIES if x.get('symbol')})


def _live_quotes():
    symbols = _forecast_symbols()
    collected = datetime.now(timezone.utc).isoformat()
    fresh = {}
    stale = {}
    errors = []

    try:
        payload = json.loads(market.request(market.API + 'price/symbols/getList', {'symbols': symbols}))
        fresh = market.normalize_board(payload, symbols, collected)
        if _current_quote_day():
            max_age = 18 if _strict_live_session() else None
            fresh, stale = market.current_session_quotes(fresh, max_age_minutes=max_age)
            if stale:
                errors.append(f'Vietcap stale session quotes rejected: {len(stale)}')
    except Exception as exc:
        fresh = {}
        errors.append('Vietcap quotes: ' + str(exc))

    missing = [symbol for symbol in symbols if symbol not in fresh]
    if _current_quote_day() and missing:
        try:
            kbs_rows = market.kbs_current_board(missing, collected)
            fresh.update(kbs_rows)
            errors.append(f'KBS current-session fallback filled {len(kbs_rows)}/{len(missing)} symbols')
        except Exception as exc:
            errors.append('KBS fallback: ' + str(exc))

    expected = len(symbols)
    required = max(1, int(expected * .90 + .999999))
    if not fresh:
        raise RuntimeError('No usable live quotes')
    if _current_quote_day() and len(fresh) < required:
        raise RuntimeError(f'Current-session quote coverage too low: {len(fresh)}/{expected}; ' + '; '.join(errors[:3]))

    providers = sorted({row.get('source') for row in fresh.values() if row.get('source')})
    return {
        'mode': 'quotes',
        'checkedAt': collected,
        'status': 'ok',
        'liveFallback': True,
        'source': 'Vietcap + KBS live API fallback',
        'providers': providers,
        'coverage': len(fresh),
        'expected': expected,
        'latestSourceTime': market.newest_source_time(fresh),
        'staleRejected': len(stale),
        'errors': errors,
        'quotes': fresh,
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
