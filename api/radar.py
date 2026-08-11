import pathlib, importlib.util, json
from datetime import datetime, timedelta, date
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

base_path = pathlib.Path(__file__).with_name('stocks2.py')
spec = importlib.util.spec_from_file_location('stock_ews_base', base_path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

VERSION = 'STOCK-EWS-4.1.0-FINAL'
MIN_MODEL_ROWS = 240

_original_fetch_history = base.fetch_history


def _filter_rows(rows, start, end):
    a, b = start.isoformat(), end.isoformat()
    out = [r for r in (rows or []) if a <= str(r.get('date', '')) <= b]
    ded = {r['date']: r for r in out if r.get('date')}
    return [ded[k] for k in sorted(ded)]


def _yahoo_history(symbol, start, end, index=False):
    candidates = ['^VNINDEX.VN', 'VNINDEX.VN'] if index else [symbol]
    last = None
    for ticker in candidates:
        try:
            rows, meta, host = base.core.yahoo_chart(ticker, '10y', 9)
            rows = _filter_rows(rows, start, end)
            rows, intraday = base.strip_intraday(rows)
            if len(rows) < MIN_MODEL_ROWS:
                raise RuntimeError(f'Yahoo returned only {len(rows)} completed sessions for {ticker}')
            audit = [{
                'source': 'Yahoo Finance',
                'provider': host,
                'type': 'index.ohlcv.fallback' if index else 'equity.ohlcv.fallback',
                'symbol': 'VNINDEX' if index else symbol,
                'start': start.isoformat(),
                'end': end.isoformat(),
                'rows': len(rows),
                'ok': True,
                'fallback': True,
            }]
            return rows, audit, intraday
        except Exception as e:
            last = e
    raise RuntimeError(str(last or 'Yahoo fallback unavailable'))


def resilient_fetch_history(symbol, start, end, segmented=True, index=False):
    vn_rows = None
    vn_audit = []
    vn_intraday = False
    vn_error = None
    try:
        vn_rows, vn_audit, vn_intraday = _original_fetch_history(
            symbol, start, end, segmented=True, index=index
        )
        if len(vn_rows) >= MIN_MODEL_ROWS:
            for x in vn_audit:
                x['primary'] = True
            return vn_rows, vn_audit, vn_intraday
        vn_error = f'Vnstock returned {len(vn_rows)} completed sessions; model needs {MIN_MODEL_ROWS}+'
    except Exception as e:
        vn_error = str(e)

    try:
        rows, audit, intraday = _yahoo_history(symbol, start, end, index=index)
        if vn_audit:
            audit = vn_audit + [{
                'source': 'Vnstock',
                'provider': 'KBS',
                'type': 'fallback-trigger',
                'symbol': 'VNINDEX' if index else symbol,
                'ok': False,
                'error': vn_error,
            }] + audit
        elif vn_error:
            audit.insert(0, {
                'source': 'Vnstock',
                'provider': 'KBS',
                'type': 'fallback-trigger',
                'symbol': 'VNINDEX' if index else symbol,
                'ok': False,
                'error': vn_error,
            })
        return rows, audit, intraday
    except Exception as yerr:
        if vn_rows and len(vn_rows) >= 201:
            return vn_rows, vn_audit + [{
                'source': 'Yahoo Finance', 'ok': False, 'error': str(yerr)[:240]
            }], vn_intraday
        raise RuntimeError(
            f'Price history unavailable for {"VNINDEX" if index else symbol}: '
            f'Vnstock={vn_error}; Yahoo={yerr}'
        )


# All detail/validation-facing stock logic that imports this module gets a resilient
# price-history layer. Vnstock/KBS remains primary; Yahoo is only the operational fallback.
base.fetch_history = resilient_fetch_history


def _radar_history(symbol, start, end, index=False):
    """Fast independent history for the watchlist so Vnstock rate limits cannot blank the radar."""
    try:
        return _yahoo_history(symbol, start, end, index=index)
    except Exception:
        return resilient_fetch_history(symbol, start, end, segmented=True, index=index)


def _two_year_start(start, end):
    floor = end - timedelta(days=2 * 366)
    return max(start, floor)


def market_module(start, end, asof=None):
    fetch_start = _two_year_start(start, end)
    try:
        rows, audit, intraday = _radar_history('VNINDEX', fetch_start, end, index=True)
        cur, hz, _ = base.state_from_rows(rows, asof)
        a = hz['20']
        score = .65 * cur['technical'] + .35 * (a['score'] if a.get('available') else 50)
        return {
            'score': score,
            'available': True,
            'technical': cur['technical'],
            'analog20': a,
            'date': cur['date'],
            'audit': audit,
            'intradayBarExcluded': intraday,
        }
    except Exception as e:
        return {
            'score': 50,
            'available': False,
            'technical': None,
            'analog20': {'score': 50, 'rate': None, 'matches': 0, 'available': False},
            'date': None,
            'audit': [],
            'intradayBarExcluded': False,
            'reason': str(e)[:320],
        }


def scan_one(symbol, start, end, market, macro):
    fetch_start = _two_year_start(start, end)
    rows, audit, intraday = _radar_history(symbol, fetch_start, end, index=False)
    cur, hz, _ = base.state_from_rows(rows)
    mods = {
        'technical': {'score': cur['technical'], 'available': True},
        'analog': hz['20'],
        'market': market,
        'macro': macro,
        'sentiment': {'score': 50, 'available': False},
        'fundamental': {'score': 50, 'available': False},
    }
    score, conf = base.aggregate(mods)
    ov = {'available': False, 'score': score}
    cl = base.classify(score, cur, conf, ov)
    return {
        'symbol': symbol,
        'name': base.core.NAMES.get(symbol, symbol),
        'date': cur['date'],
        'close': cur['close'],
        'ret5': cur['ret5'],
        'score': score,
        'confidence': conf,
        'phase': cl['phase'],
        'color': cl['color'],
        'state': cl['state'],
        'effectiveScore': cl['effectiveScore'],
        'modules': mods,
        'current': cur,
        'audit': audit,
        'dataQuality': base.quality(rows, fetch_start, end, audit, intraday),
    }


base.market_module = market_module
base.scan_one = scan_one
base.VERSION = VERSION


class handler(BaseHTTPRequestHandler):
    def sendj(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        mode = q.get('mode', ['scan'])[0]
        try:
            if mode == 'detail':
                out = base.detail(q.get('symbol', ['FPT'])[0], q)
                if isinstance(out, dict):
                    out.setdefault('source', {})['price'] = 'Vnstock v4/KBS primary · Yahoo Finance fallback when required'
            elif mode == 'health':
                out = {
                    'ok': True,
                    'version': VERSION,
                    'time': datetime.now(base.VN_TZ).isoformat(),
                    'priceSource': 'Vnstock v4/KBS primary · Yahoo Finance operational fallback',
                    'radarPricePolicy': 'Yahoo-first for watchlist reliability; Vnstock-first for single-name analysis',
                    'minModelRows': MIN_MODEL_ROWS,
                    'maxScanSymbols': base.SCAN_MAX,
                }
            else:
                out = base.scan(q)
                if isinstance(out, dict):
                    out['dataSourcePolicy'] = 'Watchlist radar uses independent market history for reliability; single-name analysis prioritizes Vnstock/KBS.'
                    if isinstance(out.get('scanPolicy'), dict):
                        out['scanPolicy']['priceSource'] = 'Yahoo Finance radar · Vnstock/KBS primary for analysis'
            if isinstance(out, dict):
                out['version'] = VERSION
            self.sendj(200, out)
        except Exception as e:
            self.sendj(503, {
                'error': 'STOCK_EWS_REQUEST_FAILED',
                'message': str(e),
                'type': type(e).__name__,
                'version': VERSION,
                'priceSource': 'Vnstock v4/KBS + Yahoo Finance fallback',
                'retryable': True,
            })
