import pathlib, importlib.util, json
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

base_path = pathlib.Path(__file__).with_name('stocks2.py')
spec = importlib.util.spec_from_file_location('stock_ews_base', base_path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

VERSION = 'STOCK-EWS-4.0.2-SEGMENTED'


def _two_year_start(start, end):
    floor = end - timedelta(days=2 * 366)
    return max(start, floor)


def market_module(start, end, asof=None):
    fetch_start = _two_year_start(start, end)
    rows, audit, intraday = base.fetch_history('VNINDEX', fetch_start, end, segmented=True, index=True)
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


def scan_one(symbol, start, end, market, macro):
    fetch_start = _two_year_start(start, end)
    rows, audit, intraday = base.fetch_history(symbol, fetch_start, end, segmented=True, index=False)
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


# Patch the original module so detail() and scan() keep the existing model logic
# while using production-safe segmented price retrieval.
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
            elif mode == 'health':
                out = {
                    'ok': True,
                    'version': VERSION,
                    'time': datetime.now(base.VN_TZ).isoformat(),
                    'priceSource': 'Vnstock v4/KBS',
                    'historyRetrieval': 'segmented',
                    'maxScanSymbols': base.SCAN_MAX,
                }
            else:
                out = base.scan(q)
            if isinstance(out, dict):
                out['version'] = VERSION
            self.sendj(200, out)
        except Exception as e:
            self.sendj(503, {
                'error': 'STOCK_EWS_REQUEST_FAILED',
                'message': str(e),
                'type': type(e).__name__,
                'version': VERSION,
                'priceSource': 'Vnstock v4/KBS',
                'retryable': True,
            })
