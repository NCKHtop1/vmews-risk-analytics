import importlib.util
import json
import math
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'hose-fallbacks'
OUT.mkdir(parents=True, exist_ok=True)
VN_TZ = timezone(timedelta(hours=7))
MIN_DEEP_ROWS = 240
MIN_FORECAST_ROWS = 520
CACHE_HISTORY_ROWS = 900


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = load_module('vmews_hose_core', ROOT / 'api' / 'stocks.py')
radar = load_module('vmews_hose_radar', ROOT / 'api' / 'radar.py')
price_history = load_module('vmews_hose_price', ROOT / 'api' / 'price_history.py')


def clean(v):
    import re
    return re.sub(r'[^A-Z0-9]', '', str(v or '').upper())[:8]


def hose_universe():
    from vnstock import Listing
    df = Listing(source='VCI').symbols_by_exchange(show_log=False)
    cols = {str(c).lower(): c for c in df.columns}
    sc = cols.get('symbol')
    ec = cols.get('exchange') or cols.get('board')
    nc = cols.get('organ_name') or cols.get('organ_short_name')
    tc = cols.get('type')
    if sc is None or ec is None:
        raise RuntimeError(f'Unexpected VCI listing columns: {list(df.columns)}')
    out = []
    for _, row in df.iterrows():
        sym = clean(row.get(sc))
        ex = str(row.get(ec) or '').upper().strip()
        ex = {'HSX': 'HOSE', 'HOCHIMINH': 'HOSE'}.get(ex, ex)
        typ = str(row.get(tc, 'STOCK')).upper() if tc is not None else 'STOCK'
        if not sym or ex != 'HOSE' or typ != 'STOCK':
            continue
        name = str(row.get(nc, sym) or sym).strip() if nc is not None else sym
        out.append({'symbol': sym, 'name': name, 'exchange': 'HOSE'})
    out = list({x['symbol']: x for x in out}.values())
    if len(out) < 250:
        raise RuntimeError(f'HOSE reference universe unexpectedly small: {len(out)}')
    return sorted(out, key=lambda x: x['symbol'])


def yahoo_probe(meta):
    sym = meta['symbol']
    try:
        rows, _, host = core.yahoo_chart(sym, '10y', 5)
        return sym, rows, {
            'source': 'Yahoo Finance', 'provider': host, 'symbol': sym,
            'rows': len(rows), 'ok': True
        }
    except Exception as e:
        return sym, None, {
            'source': 'Yahoo Finance', 'symbol': sym, 'ok': False,
            'error': str(e)[:240]
        }


def vnstock_once(sym):
    from vnstock.ui import Market
    today = datetime.now(VN_TZ).date()
    start = (today - timedelta(days=366 * 11)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    df = Market().equity(sym).ohlcv(start=start, end=end, interval='1D', count=4000)
    rows, scale = price_history._normalize_df(df, sym, 'Vnstock Unified Market')
    return rows, {
        'source': 'Vnstock',
        'provider': 'Unified Market equity OHLCV (KBS/VCI routing)',
        'symbol': sym, 'rows': len(rows), 'ok': True,
        'unitNormalization': 'x1000 to VND' if scale == 1000.0 else 'already VND'
    }


def simple_current(rows):
    c = [float(x['close']) for x in rows]
    i = len(c) - 1
    last = c[-1]

    def ret(n):
        return last / c[-1-n] - 1 if len(c) > n and c[-1-n] > 0 else None

    peak = max(c[-60:]) if c else last
    return {
        'i': i, 'date': rows[-1]['date'], 'close': last,
        'ret1': ret(1), 'ret5': ret(5), 'mom20': ret(20),
        'dd60': last / peak - 1 if peak else None,
        'trend50': None, 'trend200': None, 'rsi14': None,
        'technical': None, 'technicalDrivers': {}
    }


def full_payload(meta, rows, audit, route):
    cur, hz, fs = core.technical_state(rows)
    try:
        mp = json.loads((ROOT / 'data' / 'market-context.json').read_text(encoding='utf-8'))
        market = mp.get('market') or {'score': 50, 'available': False, 'reason': 'Static market context unavailable'}
    except Exception:
        market = {'score': 50, 'available': False, 'reason': 'Static market context unavailable'}
    mods = {
        'technical': {'score': cur['technical'], 'available': True, 'drivers': cur.get('technicalDrivers', {})},
        'analog': hz['20'],
        'market': market,
        'macro': {'score': 50, 'available': False, 'note': 'Optional context omitted from immutable CDN mirror.'},
        'sentiment': {'score': 50, 'available': False, 'note': 'Event intelligence is loaded from its own PIT snapshot.'},
        'fundamental': {'score': 50, 'available': False, 'note': 'Optional current fundamentals are not copied into PIT price history.'}
    }
    score, conf = radar.aggregate(mods)
    phase, color, state = radar.classify(score, cur, conf)
    cutoff = cur['i']
    history = rows[-CACHE_HISTORY_ROWS:]
    return {
        'version': 'VMEWS-HOSE-RESOLVER-1.1.0',
        'mode': 'detail', 'symbol': meta['symbol'], 'name': meta['name'], 'exchange': 'HOSE',
        'request': {'from': None, 'to': None, 'asOf': None},
        'fetchedAt': datetime.now(timezone.utc).isoformat(), 'modelAsOf': cur['date'],
        'quote': None, 'score': score, 'confidence': conf, 'phase': phase,
        'color': color, 'state': state, 'effectiveScore': score,
        'liveOverlay': {'available': False, 'score': score, 'intradayReturn': None},
        'reasons': radar.reasons(mods), 'current': cur, 'horizons': hz, 'modules': mods,
        'news': [], 'fundamentals': {}, 'history': history,
        'scoreHistory': [
            {'date': f['date'], 'technical': f['technical']}
            for f in fs if f['i'] <= cutoff and f['date'] >= history[0]['date']
        ],
        'crashReplay': radar.replay(rows, fs, cutoff),
        'dataQuality': {
            **radar.pct_quality(rows, audit),
            'forecastEligible': len(rows) >= MIN_FORECAST_ROWS,
            'forecastMinRows': MIN_FORECAST_ROWS,
            'cachedHistoryRows': len(history),
            'totalSourceRows': len(rows)
        },
        'warnings': [], 'audit': [audit],
        'resolver': {'route': route, 'immutableMirror': True, 'historyLimit': CACHE_HISTORY_ROWS},
        'source': {
            'price': f"{audit.get('source')} · {audit.get('provider')}",
            'quote': 'Not used', 'market': 'Static VMEWS VNINDEX context snapshot',
            'fundamental': 'Separate optional current context',
            'sentiment': 'Separate PIT event-intelligence snapshot',
            'macro': 'Separate context; excluded when unavailable'
        }
    }


def limited_payload(meta, rows, audit, route):
    cur = simple_current(rows)
    unavailable = {
        'score': 50, 'available': False,
        'reason': 'Insufficient completed history for the validated forecast model.'
    }
    history = rows[-CACHE_HISTORY_ROWS:]
    return {
        'version': 'VMEWS-HOSE-RESOLVER-1.1.0', 'mode': 'detail',
        'symbol': meta['symbol'], 'name': meta['name'], 'exchange': 'HOSE',
        'request': {'from': None, 'to': None, 'asOf': None},
        'fetchedAt': datetime.now(timezone.utc).isoformat(), 'modelAsOf': cur['date'], 'quote': None,
        'score': 50, 'confidence': 0.0, 'phase': 'INSUFFICIENT_HISTORY',
        'color': 'GRAY', 'state': 'REVIEW', 'effectiveScore': 50,
        'liveOverlay': {'available': False, 'score': 50, 'intradayReturn': None},
        'reasons': ['Limited-history observation only'], 'current': cur,
        'horizons': {'5': unavailable, '20': unavailable, '60': unavailable},
        'modules': {
            'technical': unavailable, 'analog': unavailable, 'market': unavailable,
            'macro': unavailable, 'sentiment': unavailable, 'fundamental': unavailable
        },
        'news': [], 'fundamentals': {}, 'history': history,
        'scoreHistory': [], 'crashReplay': [],
        'dataQuality': {
            'status': 'REVIEW', 'rows': len(rows), 'start': rows[0]['date'], 'end': rows[-1]['date'],
            'coverageRatio': min(1.0, len(rows) / MIN_DEEP_ROWS), 'largeGaps': 0,
            'intradayBarExcluded': False, 'requestAudit': [audit],
            'forecastEligible': False, 'forecastMinRows': MIN_FORECAST_ROWS,
            'cachedHistoryRows': len(history), 'totalSourceRows': len(rows)
        },
        'warnings': [f'Only {len(rows)} completed sessions are available; numerical forecast is intentionally withheld.'],
        'audit': [audit], 'resolver': {'route': route, 'immutableMirror': True, 'historyLimit': CACHE_HISTORY_ROWS},
        'source': {
            'price': f"{audit.get('source')} · {audit.get('provider')}", 'quote': 'Not used',
            'market': 'Excluded for limited-history observation', 'fundamental': 'Excluded',
            'sentiment': 'Excluded', 'macro': 'Excluded'
        }
    }


def write_payload(meta, rows, audit, route):
    payload = full_payload(meta, rows, audit, route) if len(rows) >= MIN_DEEP_ROWS else limited_payload(meta, rows, audit, route)
    (OUT / f"{meta['symbol']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False),
        encoding='utf-8'
    )
    return payload


def main():
    universe = hose_universe()

    # Rebuild the mirror atomically at the dataset level: stale symbol files from
    # previous universes must not survive and masquerade as current PIT data.
    for p in OUT.glob('*.json'):
        if p.name != 'manifest.json':
            try:
                p.unlink()
            except Exception:
                pass

    yahoo = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        fut = {ex.submit(yahoo_probe, m): m for m in universe}
        for f in as_completed(fut):
            sym, rows, audit = f.result()
            yahoo[sym] = (rows, audit)

    routes = {}
    unresolved = []
    primary = []
    fallback_deep = []
    fallback_limited = []
    forecast_eligible = []

    # IMPORTANT: Yahoo-primary symbols are also written to CDN. The old resolver
    # only recorded PRIMARY_YAHOO in the manifest and created no file. A transient
    # API/provider failure then looked like "insufficient EOD" in the browser.
    for meta in universe:
        sym = meta['symbol']
        rows, audit = yahoo.get(sym, (None, {'source': 'Yahoo Finance', 'symbol': sym, 'ok': False}))
        if rows and len(rows) >= MIN_DEEP_ROWS:
            try:
                payload = write_payload(meta, rows, audit, 'PRIMARY_YAHOO_WITH_CDN_MIRROR')
                primary.append(sym)
                if payload['dataQuality']['forecastEligible']:
                    forecast_eligible.append(sym)
                routes[sym] = {
                    'route': 'PRIMARY_YAHOO_WITH_CDN_MIRROR', 'rows': len(rows),
                    'cachedRows': len(payload['history']), 'forecastEligible': payload['dataQuality']['forecastEligible'],
                    'source': audit.get('source'), 'provider': audit.get('provider')
                }
                continue
            except Exception as e:
                # Try the independent source rather than publishing a broken mirror.
                audit = {**audit, 'mirrorError': str(e)[:220]}

        try:
            rows2, audit2 = vnstock_once(sym)
            if not rows2:
                raise RuntimeError('Vnstock returned no completed rows')
            route = 'CDN_VNSTOCK_DEEP' if len(rows2) >= MIN_DEEP_ROWS else 'CDN_LIMITED_HISTORY'
            payload = write_payload(meta, rows2, audit2, route)
            if len(rows2) >= MIN_DEEP_ROWS:
                fallback_deep.append(sym)
            else:
                fallback_limited.append(sym)
            if payload['dataQuality']['forecastEligible']:
                forecast_eligible.append(sym)
            routes[sym] = {
                'route': route, 'rows': len(rows2), 'cachedRows': len(payload['history']),
                'forecastEligible': payload['dataQuality']['forecastEligible'],
                'source': audit2.get('source'), 'provider': audit2.get('provider')
            }
        except BaseException as e:
            # A short Yahoo history can still be published for chart-only observation.
            yr, ya = yahoo.get(sym, (None, {}))
            if yr:
                try:
                    payload = write_payload(meta, yr, ya, 'CDN_LIMITED_YAHOO_HISTORY')
                    fallback_limited.append(sym)
                    routes[sym] = {
                        'route': 'CDN_LIMITED_YAHOO_HISTORY', 'rows': len(yr),
                        'cachedRows': len(payload['history']), 'forecastEligible': False,
                        'source': ya.get('source'), 'provider': ya.get('provider')
                    }
                    continue
                except Exception as e2:
                    e = RuntimeError(f'{e}; limited Yahoo payload failed: {e2}')
            unresolved.append({'symbol': sym, 'error': str(e)[:300], 'yahoo': ya.get('error') if isinstance(ya, dict) else None})
        # Guest Vnstock requests are deliberately slow; the runner adds a stronger throttle.
        time.sleep(0.2)

    resolved = len(routes)
    manifest = {
        'version': 'VMEWS-HOSE-RESOLVER-1.1.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'hoseReference': len(universe),
        'primaryYahooDeep': len(primary),
        'cdnVnstockDeep': len(fallback_deep),
        'cdnLimitedHistory': len(fallback_limited),
        'resolved': resolved,
        'cachedSymbols': resolved,
        'routeCoverageRatio': resolved / len(universe) if universe else 0,
        'deepResearchCoverageRatio': (len(primary) + len(fallback_deep)) / len(universe) if universe else 0,
        'forecastEligibleCount': len(set(forecast_eligible)),
        'forecastEligibleSymbols': sorted(set(forecast_eligible)),
        'forecastMinRows': MIN_FORECAST_ROWS,
        'cacheHistoryRows': CACHE_HISTORY_ROWS,
        'fallbackSymbols': fallback_deep + fallback_limited,
        'limitedSymbols': fallback_limited,
        'unresolved': unresolved,
        'routes': routes
    }
    (OUT / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8'
    )
    print(json.dumps({k: manifest[k] for k in [
        'hoseReference', 'primaryYahooDeep', 'cdnVnstockDeep', 'cdnLimitedHistory',
        'resolved', 'routeCoverageRatio', 'deepResearchCoverageRatio', 'forecastEligibleCount'
    ]}, ensure_ascii=False))
    if unresolved:
        raise RuntimeError(f'Unresolved HOSE symbols: {[x["symbol"] for x in unresolved]}')


if __name__ == '__main__':
    main()
