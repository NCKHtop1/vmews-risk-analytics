import json, math, pathlib, re
from collections import Counter
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'market-scan.json'
VN_TZ = timezone(timedelta(hours=7))
VERSION = 'VMEWS-MARKET-SCAN-3.1.0'
MIN_AVG_TURNOVER_30D = 500_000_000.0
RED_THRESHOLD = 78.0
YELLOW_THRESHOLD = 65.0
WATCH_THRESHOLD = 50.0


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def num(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def norm_symbol(v):
    s = str(v or '').upper().split(':')[-1]
    return re.sub(r'[^A-Z0-9]', '', s)


def norm_exchange(v):
    x = str(v or '').upper().strip()
    return {'HSX': 'HOSE', 'HOCHIMINH': 'HOSE', 'HANOI': 'HNX', 'UPCOM': 'UPCOM'}.get(x, x)


def row_date(v, fallback=None):
    x = num(v)
    if x is None:
        return fallback
    if x > 1e12:
        x /= 1000.0
    try:
        return datetime.fromtimestamp(x, timezone.utc).astimezone(VN_TZ).date().isoformat()
    except Exception:
        return fallback


def load_previous():
    try:
        p = json.loads(OUT.read_text(encoding='utf-8'))
        if p.get('version') != VERSION:
            return {}
        return {x['symbol']: x for x in p.get('ranking', []) if x.get('symbol')}
    except Exception:
        return {}


def reference_universe():
    from vnstock import Listing
    df = Listing(source='VCI').symbols_by_exchange(show_log=False)
    cols = {str(c).lower(): c for c in df.columns}
    sc = cols.get('symbol')
    ec = cols.get('exchange') or cols.get('board')
    tc = cols.get('type')
    nc = cols.get('organ_name') or cols.get('organ_short_name')
    if sc is None or ec is None:
        raise RuntimeError(f'VCI listing columns unexpected: {list(df.columns)}')
    out = {}
    for _, row in df.iterrows():
        sym = norm_symbol(row.get(sc))
        if not sym:
            continue
        typ = str(row.get(tc, 'STOCK')).upper() if tc is not None else 'STOCK'
        if typ != 'STOCK':
            continue
        ex = norm_exchange(row.get(ec))
        if ex not in {'HOSE', 'HNX', 'UPCOM'}:
            continue
        name = str(row.get(nc, sym) or sym).strip() if nc is not None else sym
        out[sym] = {'symbol': sym, 'exchange': ex, 'name': name}
    if len(out) < 500:
        raise RuntimeError(f'VCI stock reference universe too small ({len(out)}); refusing full-market label')
    return out


def fallback_market_context():
    try:
        p = json.loads((ROOT / 'data' / 'market-context.json').read_text(encoding='utf-8'))
        m = p.get('market') or {}
        return {'date': m.get('date'), 'momentum20': None, 'available': False, 'source': 'VMEWS VNINDEX date fallback only'}
    except Exception:
        return {'date': None, 'momentum20': None, 'available': False, 'source': 'Unavailable'}


def tradingview_market_context():
    fallback = fallback_market_context()
    try:
        from tradingview_screener import Query
        for ticker, label in [('HOSE:VNINDEX', 'VNINDEX'), ('HOSE:VN30', 'VN30 proxy')]:
            try:
                _, df = (Query().set_tickers(ticker)
                         .select('name', 'close', 'Perf.1M', 'update_mode', 'update_time').limit(5).get_scanner_data())
                if df is None or len(df) == 0:
                    continue
                row = df.iloc[0]
                perf = num(row.get('Perf.1M'))
                if perf is None:
                    continue
                return {
                    'date': row_date(row.get('update_time'), fallback.get('date')),
                    'momentum20': perf / 100.0,
                    'available': True,
                    'source': f'TradingView {label}',
                    'benchmarkTicker': ticker,
                    'updateMode': str(row.get('update_mode') or 'unknown'),
                }
            except Exception:
                continue
    except Exception:
        pass
    return fallback


def tradingview_snapshot():
    from tradingview_screener import stocks
    fields = [
        'name', 'description', 'exchange', 'type', 'typespecs', 'close', 'change', 'volume',
        'average_volume_30d_calc', 'relative_volume_10d_calc', 'Perf.5D', 'Perf.1M', 'Perf.3M',
        'High.3M', 'price_52_week_high', 'RSI', 'SMA50', 'SMA200', 'MACD.macd', 'MACD.signal',
        'Volatility.D', 'market_cap_basic', 'sector', 'update_mode', 'update_time'
    ]
    total, df = stocks('vietnam').select(*fields).limit(3000).get_scanner_data()
    if df is None or len(df) < 500:
        raise RuntimeError(f'TradingView Vietnam screener returned only {0 if df is None else len(df)} rows')
    return int(total), df


def transition(prev_status, current_status):
    rank = {'GREEN': 0, 'WATCH': 1, 'YELLOW': 2, 'RED': 3}
    if not prev_status:
        return 'BASELINE', False
    if prev_status == current_status:
        return 'UNCHANGED', False
    esc = prev_status in rank and current_status in rank and rank[current_status] > rank[prev_status] and current_status in {'YELLOW', 'RED'}
    return f'{prev_status} → {current_status}', esc


def score_row(row, market_mom20):
    close = num(row.get('close'))
    sma50 = num(row.get('SMA50'))
    sma200 = num(row.get('SMA200'))
    rsi = num(row.get('RSI'))
    macd = num(row.get('MACD.macd'))
    signal = num(row.get('MACD.signal'))
    perf5 = num(row.get('Perf.5D'))
    perf1m = num(row.get('Perf.1M'))
    perf3m = num(row.get('Perf.3M'))
    high3m = num(row.get('High.3M'))
    high52 = num(row.get('price_52_week_high'))
    change = num(row.get('change'))
    vol_d = num(row.get('Volatility.D'))
    volume = num(row.get('volume'), 0.0)
    avgvol30 = num(row.get('average_volume_30d_calc'), 0.0)
    relvol = num(row.get('relative_volume_10d_calc'), 0.0)
    if close is None or close <= 0 or sma50 is None or sma200 is None or sma50 <= 0 or sma200 <= 0 or rsi is None or perf1m is None:
        return None

    ret1 = (change or 0.0) / 100.0
    ret5 = (perf5 or 0.0) / 100.0
    mom20 = perf1m / 100.0
    mom3m = (perf3m or 0.0) / 100.0
    trend50 = close / sma50 - 1
    trend200 = close / sma200 - 1
    dd3m = close / high3m - 1 if high3m and high3m > 0 else min(0.0, mom3m)
    dd52 = close / high52 - 1 if high52 and high52 > 0 else None
    macd_norm = (macd - signal) / close if macd is not None and signal is not None else 0.0
    avg_turnover30 = close * avgvol30
    market_available = market_mom20 is not None and math.isfinite(float(market_mom20))
    relative20 = mom20 - float(market_mom20) if market_available else None

    p_dd = clamp(abs(min(dd3m, 0.0)) / .22)
    p_mom = clamp(abs(min(mom20, 0.0)) / .14)
    p_t50 = clamp(abs(min(trend50, 0.0)) / .12)
    p_t200 = clamp(abs(min(trend200, 0.0)) / .18)
    p_vol = clamp(((vol_d or 0.0) - 1.8) / 5.0)
    p_rsi = clamp((45.0 - rsi) / 20.0)
    p_macd = clamp(max(0.0, -macd_norm) / .025)
    p_sellvol = clamp(max(0.0, (relvol or 0.0) - 1.0) / 2.0) * clamp(max(0.0, -ret1) / .05)
    p_relative = clamp(max(0.0, -relative20) / .15) if market_available else 0.0
    raw_score = .18*p_dd + .16*p_mom + .14*p_t50 + .10*p_t200 + .12*p_vol + .10*p_rsi + .08*p_macd + .06*p_sellvol
    weight_sum = .94
    if market_available:
        raw_score += .06*p_relative
        weight_sum += .06
    technical = 100.0 * raw_score / weight_sum
    score = technical
    weak = mom20 < 0 or trend50 < 0

    stress_flags = {
        'drawdown': dd3m <= -.18,
        'momentum': mom20 <= -.10,
        'ma50': trend50 <= -.10,
        'ma200': trend200 <= -.15,
        'rsi': rsi <= 35,
        'macd': macd_norm <= -.008,
        'volatility': (vol_d or 0.0) >= 4.0,
        'selloffVolume': ret1 <= -.04 and (relvol or 0.0) >= 1.5,
        'relativeWeakness': market_available and relative20 <= -.12,
    }
    stress_count = sum(bool(v) for v in stress_flags.values())
    liquid = avg_turnover30 >= MIN_AVG_TURNOVER_30D

    contrib = [
        (.18*p_dd, f'3M drawdown {dd3m*100:.1f}%'),
        (.16*p_mom, f'1M momentum {mom20*100:.1f}%'),
        (.14*p_t50, f'vs SMA50 {trend50*100:.1f}%'),
        (.10*p_t200, f'vs SMA200 {trend200*100:.1f}%'),
        (.12*p_vol, f'daily volatility {(vol_d or 0):.1f}%'),
        (.10*p_rsi, f'RSI14 {rsi:.0f}'),
        (.08*p_macd, 'negative MACD impulse'),
        (.06*p_sellvol, f'selloff relative volume {(relvol or 0):.1f}x'),
    ]
    if market_available:
        contrib.append((.06*p_relative, f'1M vs benchmark {relative20*100:.1f}%'))
    drivers = [label for w, label in sorted(contrib, reverse=True) if w >= .012][:4]

    if not liquid:
        status, phase = 'ILLIQUID', 'EXCLUDED_LOW_LIQUIDITY'
    elif score >= RED_THRESHOLD and weak and stress_count >= 3:
        status, phase = 'RED', 'MULTI_SIGNAL_RED'
    elif score >= YELLOW_THRESHOLD and weak and stress_count >= 2:
        status, phase = 'YELLOW', 'MULTI_SIGNAL_YELLOW'
    elif score >= WATCH_THRESHOLD and weak and stress_count >= 1:
        status, phase = 'WATCH', 'WATCH'
    else:
        status, phase = 'GREEN', 'NORMAL'

    return {
        'close': close, 'ret1': ret1, 'ret5': ret5, 'mom20': mom20, 'mom3m': mom3m,
        'dd60': dd3m, 'drawdown52w': dd52, 'trend50': trend50, 'trend200': trend200,
        'rsi14': rsi, 'volatilityDailyPct': vol_d, 'relativeVolume10d': relvol,
        'volume': volume, 'averageVolume30d': avgvol30, 'medianTurnover20': avg_turnover30,
        'marketRelative20': relative20, 'marketRelativeEvidenceAvailable': market_available,
        'technicalScore': technical, 'score': score, 'status': status, 'phase': phase,
        'liquidEligible': liquid, 'drivers': drivers, 'independentStressSignals': stress_count,
        'stressFlags': stress_flags, 'historyReady': True,
        'priceBasis': 'TradingView EOD/delayed technical fields; SMA200 required for alert eligibility',
    }


def main():
    now = datetime.now(VN_TZ)
    previous = load_previous()
    reference = reference_universe()
    market = tradingview_market_context()
    tv_total, df = tradingview_snapshot()
    matched, duplicates = {}, 0

    for _, row in df.iterrows():
        sym = norm_symbol(row.get('name')) or norm_symbol(row.get('ticker'))
        if not sym or sym not in reference:
            continue
        tv_ex = norm_exchange(row.get('exchange'))
        ref = reference[sym]
        if tv_ex and tv_ex in {'HOSE', 'HNX', 'UPCOM'} and tv_ex != ref['exchange']:
            continue
        if sym in matched:
            duplicates += 1
            continue
        matched[sym] = row

    if len(matched) < 500:
        raise RuntimeError(f'Only {len(matched)} TradingView rows matched the VCI stock reference universe')

    provisional = []
    insufficient = 0
    low_liquidity = 0
    date_fallback = market.get('date')
    for sym, row in matched.items():
        f = score_row(row, market.get('momentum20'))
        if f is None:
            insufficient += 1
            continue
        if not f['liquidEligible']:
            low_liquidity += 1
        ref = reference[sym]
        d = row_date(row.get('update_time'), date_fallback)
        prev = previous.get(sym, {})
        tr, esc = transition(prev.get('status'), f['status'])
        provisional.append({
            **ref, **f, 'date': d, 'provider': 'TradingView Vietnam Screener',
            'updateMode': str(row.get('update_mode') or 'unknown'),
            'marketCap': num(row.get('market_cap_basic')), 'sector': str(row.get('sector') or ''),
            'transition': tr, 'newEscalation': esc,
        })

    if not provisional:
        raise RuntimeError('No securities produced usable market-wide features')
    dated = [x['date'] for x in provisional if x.get('date')]
    model_date = Counter(dated).most_common(1)[0][0] if dated else date_fallback
    if not model_date:
        raise RuntimeError('Unable to establish model date from screener or market context')

    stale = 0
    for x in provisional:
        x['stale'] = x.get('date') != model_date
        if x['stale']:
            x['status'] = 'STALE'
            x['phase'] = 'EXCLUDED_STALE_DATA'
            x['newEscalation'] = False
            stale += 1

    eligible = [x for x in provisional if not x['stale'] and x['liquidEligible']]
    eligible.sort(key=lambda x: (x['score'], x['technicalScore']), reverse=True)
    red = [x for x in eligible if x['status'] == 'RED']
    yellow = [x for x in eligible if x['status'] == 'YELLOW']
    watch = [x for x in eligible if x['status'] == 'WATCH']
    escalations = [x for x in eligible if x.get('newEscalation')]
    attention = sorted(red + yellow, key=lambda x: (not x.get('newEscalation'), x['status'] != 'RED', -x['score']))[:30]
    coverage_ratio = len(matched) / len(reference) if reference else 0.0
    current_ratio = (len(provisional) - stale) / len(reference) if reference else 0.0

    payload = {
        'version': VERSION,
        'generatedAt': now.isoformat(), 'reviewDate': now.date().isoformat(), 'modelDate': model_date,
        'scope': 'VCI reference universe of listed common stocks on HOSE, HNX and UPCOM, cross-matched to TradingView Vietnam stock screener.',
        'method': 'Cross-sectional T-day early-warning screen using daily trend, momentum, 3M drawdown, volatility, RSI, MACD, selloff relative volume, optional market-relative weakness, multi-signal confirmation and liquidity gating.',
        'thresholds': {'red': RED_THRESHOLD, 'yellow': YELLOW_THRESHOLD, 'watch': WATCH_THRESHOLD, 'redMinIndependentSignals': 3, 'yellowMinIndependentSignals': 2, 'minAverageTurnover30dVnd': MIN_AVG_TURNOVER_30D, 'historyGate': 'SMA200 must be available'},
        'coverage': {
            'listedUniverse': len(reference), 'tradingViewUniverseRows': len(df), 'tradingViewReportedTotal': tv_total,
            'priceCovered': len(matched), 'featureReady': len(provisional), 'eligibleLiquidCurrent': len(eligible),
            'insufficientHistoryOrIndicatorsExcluded': insufficient, 'lowLiquidityExcluded': low_liquidity,
            'staleEodExcluded': stale, 'unmatchedReference': max(0, len(reference)-len(matched)),
            'duplicateScreenerRowsIgnored': duplicates, 'coverageRatio': coverage_ratio, 'currentFeatureCoverageRatio': current_ratio,
        },
        'breadth': {'red': len(red), 'yellow': len(yellow), 'watch': len(watch), 'newEscalations': len(escalations), 'redShareEligible': len(red)/len(eligible) if eligible else 0.0, 'yellowShareEligible': len(yellow)/len(eligible) if eligible else 0.0},
        'marketContext': {'available': market.get('available', False), 'vnindexMomentum20d': market.get('momentum20'), 'vnindexModelDate': market.get('date'), 'source': market.get('source'), 'benchmarkTicker': market.get('benchmarkTicker'), 'updateMode': market.get('updateMode')},
        'topAttention': attention, 'redList': red, 'yellowList': yellow, 'newEscalations': escalations, 'ranking': eligible,
        'sources': {'referenceUniverse': 'VCI via vnstock Listing.symbols_by_exchange()', 'crossSection': 'TradingView Vietnam stock screener via tradingview-screener', 'marketContext': market.get('source'), 'deepResearch': 'Second-stage VMEWS single-name engine; not part of the broad scan score'},
        'governance': [
            'RED/YELLOW are screening states, not buy/sell recommendations or calibrated crash probabilities.',
            'RED requires at least three independent stress conditions; YELLOW requires at least two. A drawdown alone cannot force a RED state.',
            'Unavailable benchmark-relative evidence is excluded and remaining broad-scan weights are renormalized; it is never replaced with a neutral zero-return assumption.',
            'Only securities cross-matched to the reference universe with current data, SMA200 history and minimum 30-day average turnover can enter RED/YELLOW.',
            'Stale, insufficient-history and illiquid securities are disclosed in coverage and excluded from the morning alert list.',
            'Unauthenticated TradingView data may be delayed; this is suitable for scheduled pre-session/post-close risk triage, not intraday execution.',
            'A full deep-model review remains a second-stage action for flagged names.'
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'modelDate': model_date, 'listed': len(reference), 'tvRows': len(df), 'matched': len(matched), 'coverage': round(coverage_ratio,4), 'eligible': len(eligible), 'red': len(red), 'yellow': len(yellow), 'watch': len(watch), 'escalations': len(escalations), 'stale': stale, 'insufficient': insufficient, 'lowLiquidity': low_liquidity, 'marketAvailable': market.get('available'), 'benchmark': market.get('benchmarkTicker'), 'benchmarkMomentum20': market.get('momentum20')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
