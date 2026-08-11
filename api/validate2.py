import pathlib, importlib.util, json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

base_path = pathlib.Path(__file__).with_name('validate.py')
spec = importlib.util.spec_from_file_location('qtrr_validation_base', base_path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

VERSION = 'QTRR-VALIDATION-1.2.0-FINAL'
MIN_VALIDATION_ROWS = 350
_original_fetch_history = base.fetch_history


def _yahoo_history(symbol, start, end):
    rows, meta, host = base.core.yahoo_chart(symbol, '10y', 9)
    a, b = start.isoformat(), end.isoformat()
    rows = [r for r in rows if a <= str(r.get('date', '')) <= b]
    ded = {r['date']: r for r in rows if r.get('date')}
    rows = [ded[k] for k in sorted(ded)]
    if len(rows) < MIN_VALIDATION_ROWS:
        raise RuntimeError(f'Yahoo returned only {len(rows)} usable rows; validation needs {MIN_VALIDATION_ROWS}')
    return rows, [{
        'source': 'Yahoo Finance',
        'provider': host,
        'type': 'validation.ohlcv.fallback',
        'symbol': symbol,
        'start': a,
        'end': b,
        'rows': len(rows),
        'ok': True,
        'fallback': True,
    }]


def resilient_fetch_history(symbol, start, end):
    primary_error = None
    try:
        rows, audit = _original_fetch_history(symbol, start, end)
        if len(rows) >= MIN_VALIDATION_ROWS:
            for x in audit:
                x['source'] = 'Vnstock'
                x['provider'] = 'KBS'
                x['primary'] = True
            return rows, audit
        primary_error = f'Vnstock returned only {len(rows)} rows'
    except Exception as e:
        primary_error = str(e)

    rows, audit = _yahoo_history(symbol, start, end)
    audit.insert(0, {
        'source': 'Vnstock',
        'provider': 'KBS',
        'type': 'fallback-trigger',
        'symbol': symbol,
        'ok': False,
        'error': primary_error,
    })
    return rows, audit


base.fetch_history = resilient_fetch_history
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
        try:
            if q.get('mode', [''])[0] == 'health':
                self.sendj(200, {
                    'ok': True,
                    'version': VERSION,
                    'time': datetime.now(base.VN_TZ).isoformat(),
                    'priceSource': 'Vnstock/KBS primary · Yahoo Finance fallback',
                    'minimumRows': MIN_VALIDATION_ROWS,
                })
                return
            out = base.validation(q.get('symbol', ['FPT'])[0], q)
            if isinstance(out, dict):
                out['version'] = VERSION
                out['priceSourcePolicy'] = 'Vnstock/KBS primary · Yahoo Finance fallback when validation history is insufficient'
            self.sendj(200, out)
        except Exception as e:
            self.sendj(503, {
                'error': 'VALIDATION_FAILED',
                'message': str(e),
                'type': type(e).__name__,
                'version': VERSION,
                'retryable': True,
            })
