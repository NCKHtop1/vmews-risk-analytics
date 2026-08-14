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
        return sym, rows, {'source': 'Yahoo Finance', 'provider': host, 'symbol': sym, 'rows': len(rows), 'ok': True}
    except Exception as e:
        return sym, None, {'source': 'Yahoo Finance', 'symbol': sym, 'ok': False, 'error': str(e)[:240]}


def vnstock_once(sym):
    from vnstock.ui import Market
    today = datetime.now(VN_TZ).date()
    start = (today - timedelta(days=366 * 11)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    df = Market().equity(sym).ohlcv(start=start, end=end, interval='1D', count=4000)
    rows, scale = price_history._normalize_df(df, sym, 'Vnstock Unified Market')
    return rows, {
        'source': 'Vnstock', 'provider': 'Unified Market equity OHLCV (KBS/VCI routing)',
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


def full_payload(meta, rows, audit):
    cur, hz, fs = core.technical_state(rows)
    try:
        mp = json.loads((ROOT / 'data' / 'market-context.json').read_text(encoding='utf-8'))
        market = mp.get('market') or {'score': 50, 'available': False, 'reason': 'Static market context unavailable'}
    except Exception:
        market = {'score': 50, 'available': False, 'reason': 'Static market context unavailable'}
    mods = {
        'technical': {'score': cur['technical'], 'available': True, 'drivers': cur.get('technicalDrivers', {})},
        'analog': hz['20'], 'market': market,
        'macro': {'score': 50, 'available': False, 'note': 'Excluded from CDN fallback cache.'},
        'sentiment': {'score': 50, 'available': False, 'note': 'Merged from the browser research-news snapshot when available.'},
        'fundamental': {'score': 50, 'available': False, 'note': 'Excluded from static fallback; current API detail is preferred when available.'}
    }
    score, conf = radar.aggregate(mods)
    phase, color, state = radar.classify(score, cur, conf)
    cutoff = cur['i']
    return {
        'version': 'VMEWS-HOSE-FALLBACK-1.0.0', 'mode': 'detail', 'symbol': meta['symbol'], 'name': meta['name'],
        'exchange': 'HOSE', 'request': {'from': None, 'to': None, 'asOf': None},
        'fetchedAt': datetime.now(timezone.utc).isoformat(), 'modelAsOf': cur['date'],
        'quote': None, 'score': score, 'confidence': conf, 'phase': phase, 'color': color, 'state': state,
        'effectiveScore': score, 'liveOverlay': {'available': False, 'score': score, 'intradayReturn': None},
        'reasons': radar.reasons(mods), 'current': cur, 'horizons': hz, 'modules': mods,
        'news': [], 'fundamentals': {}, 'history': rows[-1800:],
        'scoreHistory': [{'date': f['date'], 'technical': f['technical']} for f in fs if f['i'] <= cutoff],
        'crashReplay': radar.replay(rows, fs, cutoff), 'dataQuality': radar.pct_quality(rows, audit),
        'warnings': ['Universal HOSE CDN fallback used because the primary Yahoo detail route was unavailable or insufficient.'],
        'audit': [audit],
        'source': {'price': f"{audit.get('source')} · {audit.get('provider')}", 'quote': 'Not used',
                   'market': 'Static VMEWS VNINDEX context snapshot', 'fundamental': 'Excluded in static fallback',
                   'sentiment': 'Browser research-news merge when available', 'macro': 'Excluded in static fallback'}
    }


def limited_payload(meta, rows, audit):
    cur = simple_current(rows)
    unavailable = {'score': 50, 'available': False, 'reason': 'Insufficient completed history for the full structural/deep model stack.'}
    return {
        'version': 'VMEWS-HOSE-FALLBACK-1.0.0', 'mode': 'detail', 'symbol': meta['symbol'], 'name': meta['name'],
        'exchange': 'HOSE', 'request': {'from': None, 'to': None, 'asOf': None},
        'fetchedAt': datetime.now(timezone.utc).isoformat(), 'modelAsOf': cur['date'], 'quote': None,
        'score': 50, 'confidence': 0.0, 'phase': 'INSUFFICIENT_HISTORY', 'color': 'GRAY', 'state': 'REVIEW',
        'effectiveScore': 50, 'liveOverlay': {'available': False, 'score': 50, 'intradayReturn': None},
        'reasons': ['Limited-history observation only'], 'current': cur,
        'horizons': {'5': unavailable, '20': unavailable, '60': unavailable},
        'modules': {'technical': unavailable, 'analog': unavailable, 'market': unavailable, 'macro': unavailable,
                    'sentiment': unavailable, 'fundamental': unavailable},
        'news': [], 'fundamentals': {}, 'history': rows[-1800:], 'scoreHistory': [], 'crashReplay': [],
        'dataQuality': {'status': 'REVIEW', 'rows': len(rows), 'start': rows[0]['date'], 'end': rows[-1]['date'],
                        'coverageRatio': min(1.0, len(rows) / 240.0), 'largeGaps': 0, 'intradayBarExcluded': False,
                        'requestAudit': [audit]},
        'warnings': [f'Only {len(rows)} completed sessions are available. Price chart is shown, but full RF/ANFIS/VAE/LSTM validation is not considered reliable.'],
        'audit': [audit],
        'source': {'price': f"{audit.get('source')} · {audit.get('provider')}", 'quote': 'Not used',
                   'market': 'Excluded for limited-history fallback', 'fundamental': 'Excluded', 'sentiment': 'Excluded', 'macro': 'Excluded'}
    }


def main():
    universe = hose_universe()
    by_symbol = {x['symbol']: x for x in universe}
    # Keep only fallback files; Yahoo-supported names continue to use the primary API.
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

    primary_deep = []
    needs_fallback = []
    for m in universe:
        rows, audit = yahoo[m['symbol']]
        if rows is not None and len(rows) >= 240:
            primary_deep.append(m['symbol'])
        else:
            needs_fallback.append(m)

    fallback_deep = []
    fallback_limited = []
    unresolved = []
    routes = {s: {'route': 'PRIMARY_YAHOO', 'rows': len(yahoo[s][0]), 'source': 'Yahoo Finance'} for s in primary_deep}

    for idx, meta in enumerate(needs_fallback):
        sym = meta['symbol']
        rows = None
        audit = None
        try:
            rows, audit = vnstock_once(sym)
        except Exception as e:
            yr, ya = yahoo[sym]
            if yr:
                rows, audit = yr, ya
            else:
                unresolved.append({'symbol': sym, 'error': str(e)[:260], 'yahoo': ya.get('error')})
        if rows:
            try:
                payload = full_payload(meta, rows, audit) if len(rows) >= 240 else limited_payload(meta, rows, audit)
                (OUT / f'{sym}.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
                if len(rows) >= 240:
                    fallback_deep.append(sym)
                    route = 'CDN_VNSTOCK_DEEP'
                else:
                    fallback_limited.append(sym)
                    route = 'CDN_LIMITED_HISTORY'
                routes[sym] = {'route': route, 'rows': len(rows), 'source': audit.get('source'), 'provider': audit.get('provider')}
            except Exception as e:
                unresolved.append({'symbol': sym, 'error': f'payload: {e}'[:260]})
        # Guest limit is 20 requests/minute. Stay below it deliberately.
        if idx < len(needs_fallback) - 1:
            time.sleep(3.25)

    resolved = len(routes)
    manifest = {
        'version': 'VMEWS-HOSE-RESOLVER-1.0.0', 'generatedAt': datetime.now(timezone.utc).isoformat(),
        'hoseReference': len(universe), 'primaryYahooDeep': len(primary_deep),
        'cdnVnstockDeep': len(fallback_deep), 'cdnLimitedHistory': len(fallback_limited),
        'resolved': resolved, 'routeCoverageRatio': resolved / len(universe) if universe else 0,
        'deepResearchCoverageRatio': (len(primary_deep) + len(fallback_deep)) / len(universe) if universe else 0,
        'fallbackSymbols': fallback_deep + fallback_limited, 'limitedSymbols': fallback_limited,
        'unresolved': unresolved, 'routes': routes
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({k: manifest[k] for k in ['hoseReference','primaryYahooDeep','cdnVnstockDeep','cdnLimitedHistory','resolved','routeCoverageRatio','deepResearchCoverageRatio']}, ensure_ascii=False))
    if unresolved:
        raise RuntimeError(f'Unresolved HOSE symbols: {[x["symbol"] for x in unresolved]}')


if __name__ == '__main__':
    main()
