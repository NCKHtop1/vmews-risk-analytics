import json, math, os, pathlib, re, statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'market-scan.json'
VN_TZ = timezone(timedelta(hours=7))
MIN_HISTORY = 220
MIN_MEDIAN_TURNOVER_20D = 500_000_000.0
MAX_WORKERS = 24
RED_THRESHOLD = 70.0
YELLOW_THRESHOLD = 55.0
WATCH_THRESHOLD = 45.0


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs):
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def median(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and math.isfinite(x)]
    return statistics.median(xs) if xs else 0.0


def rank_pct(v, hist):
    hist = [x for x in hist if isinstance(x, (int, float)) and math.isfinite(x)]
    return sum(x <= v for x in hist) / len(hist) if hist else 0.5


def ema(values, n):
    a = 2 / (n + 1)
    out, e = [], None
    for v in values:
        e = v if e is None else a * v + (1 - a) * e
        out.append(e)
    return out


def rsi14(closes):
    if len(closes) < 15:
        return 50.0
    gains, losses = [], []
    for i in range(len(closes) - 14, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag, al = mean(gains), mean(losses)
    return 100.0 if al < 1e-12 else 100 - 100 / (1 + ag / al)


def load_previous():
    try:
        p = json.loads(OUT.read_text(encoding='utf-8'))
        return {x['symbol']: x for x in p.get('ranking', []) if x.get('symbol')}
    except Exception:
        return {}


def listing_universe():
    from vnstock import Listing
    df = Listing(source='VCI').symbols_by_exchange(show_log=False)
    cols = {str(c).lower(): c for c in df.columns}
    symbol_col = cols.get('symbol')
    exchange_col = cols.get('exchange') or cols.get('board')
    type_col = cols.get('type')
    name_col = cols.get('organ_name') or cols.get('organ_short_name')
    if not symbol_col or not exchange_col:
        raise RuntimeError(f'VCI listing columns unexpected: {list(df.columns)}')
    out, seen = [], set()
    for _, row in df.iterrows():
        sym = re.sub(r'[^A-Z0-9]', '', str(row.get(symbol_col, '')).upper())
        if not sym or sym in seen:
            continue
        typ = str(row.get(type_col, 'STOCK')).upper() if type_col else 'STOCK'
        if typ != 'STOCK':
            continue
        ex = str(row.get(exchange_col, '')).upper().replace('HSX', 'HOSE')
        if ex not in {'HOSE', 'HNX', 'UPCOM'}:
            continue
        seen.add(sym)
        out.append({'symbol': sym, 'exchange': ex, 'name': str(row.get(name_col, sym) or sym).strip() if name_col else sym})
    if len(out) < 500:
        raise RuntimeError(f'VCI stock universe too small ({len(out)}); refusing to label scan as full-market')
    return out


def yahoo_history(symbol):
    ys = f'{symbol}.VN'
    last = None
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        try:
            url = f'https://{host}/v8/finance/chart/{quote(ys)}?interval=1d&includePrePost=false&events=div%2Csplits&range=2y'
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 VMEWS-MarketScan/1.0', 'Accept': 'application/json'})
            with urlopen(req, timeout=8) as r:
                payload = json.loads(r.read().decode())
            result = (payload.get('chart', {}).get('result') or [None])[0]
            if not result:
                raise RuntimeError(str(payload.get('chart', {}).get('error')))
            ts = result.get('timestamp') or []
            quote_data = ((result.get('indicators') or {}).get('quote') or [{}])[0]
            adj_data = ((result.get('indicators') or {}).get('adjclose') or [{}])[0].get('adjclose') or []
            rows = []
            for i, t in enumerate(ts):
                try:
                    raw_close = float((quote_data.get('close') or [])[i])
                    if not math.isfinite(raw_close) or raw_close <= 0:
                        continue
                    try:
                        adjusted = float(adj_data[i])
                        if not math.isfinite(adjusted) or adjusted <= 0:
                            adjusted = raw_close
                    except Exception:
                        adjusted = raw_close
                    try:
                        vol = float((quote_data.get('volume') or [])[i] or 0)
                        if not math.isfinite(vol) or vol < 0:
                            vol = 0.0
                    except Exception:
                        vol = 0.0
                    rows.append({
                        'date': datetime.fromtimestamp(t, timezone.utc).date().isoformat(),
                        'close': raw_close,
                        'modelClose': adjusted,
                        'volume': vol,
                    })
                except Exception:
                    pass
            ded = {x['date']: x for x in rows}
            rows = [ded[k] for k in sorted(ded)]
            if len(rows) < 60:
                raise RuntimeError(f'{ys}: only {len(rows)} rows')
            return rows, host
        except Exception as e:
            last = e
    raise RuntimeError(f'{ys}: {last}')


def market_momentum_20d():
    try:
        p = json.loads((ROOT / 'data' / 'market-context.json').read_text(encoding='utf-8'))
        rows = (p.get('market') or {}).get('history') or []
        if len(rows) >= 21:
            c = [float(x['close']) for x in rows]
            return c[-1] / c[-21] - 1
    except Exception:
        pass
    return 0.0


def scan_features(rows, market_mom20):
    if len(rows) < MIN_HISTORY:
        return None
    mc = [r['modelClose'] for r in rows]
    raw = [r['close'] for r in rows]
    vols = [r['volume'] for r in rows]
    rets = [0.0] + [math.log(mc[i] / mc[i - 1]) for i in range(1, len(mc))]
    i = len(mc) - 1
    vol20_series = []
    for j in range(max(20, i - 252), i + 1):
        vol20_series.append(stdev(rets[max(1, j - 19):j + 1]) * math.sqrt(252))
    vol20 = vol20_series[-1] if vol20_series else 0.0
    vp = rank_pct(vol20, vol20_series[:-1]) if len(vol20_series) > 1 else 0.5
    peak60 = max(mc[-60:])
    dd60 = mc[-1] / peak60 - 1
    mom20 = mc[-1] / mc[-21] - 1
    ret5 = mc[-1] / mc[-6] - 1
    ret1 = mc[-1] / mc[-2] - 1
    ma50 = mean(mc[-50:])
    ma200 = mean(mc[-200:])
    trend50 = mc[-1] / ma50 - 1
    trend200 = mc[-1] / ma200 - 1
    rs = rsi14(mc)
    e12, e26 = ema(mc, 12), ema(mc, 26)
    macd = [a - b for a, b in zip(e12, e26)]
    sig = ema(macd, 9)
    macd_norm = (macd[-1] - sig[-1]) / mc[-1] if mc[-1] else 0.0
    prev_vols = [v for v in vols[-21:-1] if v > 0]
    volume_z = (vols[-1] - mean(prev_vols)) / (stdev(prev_vols) or 1.0) if vols[-1] > 0 and prev_vols else 0.0
    turnovers = [raw[j] * vols[j] for j in range(max(0, len(rows) - 20), len(rows)) if raw[j] > 0 and vols[j] > 0]
    median_turnover20 = median(turnovers)
    relative20 = mom20 - market_mom20

    p_dd = clamp(abs(min(dd60, 0)) / .22)
    p_mom = clamp(abs(min(mom20, 0)) / .14)
    p_t50 = clamp(abs(min(trend50, 0)) / .12)
    p_t200 = clamp(abs(min(trend200, 0)) / .18)
    p_vol = clamp((vp - .45) / .55)
    p_rsi = clamp((45 - rs) / 20)
    p_macd = clamp(max(0, -macd_norm) / .025)
    p_volume = clamp(max(0, volume_z) / 3.0) * clamp(max(0, -ret1) / .05)
    technical = 100 * (.18 * p_dd + .16 * p_mom + .14 * p_t50 + .10 * p_t200 + .16 * p_vol + .10 * p_rsi + .08 * p_macd + .08 * p_volume)
    relative_penalty = clamp(max(0, -relative20) / .15)
    screen_score = .90 * technical + .10 * (100 * relative_penalty)

    contrib = [
        (.18 * p_dd, f'60D drawdown {dd60 * 100:.1f}%'),
        (.16 * p_mom, f'20D momentum {mom20 * 100:.1f}%'),
        (.14 * p_t50, f'vs MA50 {trend50 * 100:.1f}%'),
        (.10 * p_t200, f'vs MA200 {trend200 * 100:.1f}%'),
        (.16 * p_vol, f'volatility percentile {vp * 100:.0f}%'),
        (.10 * p_rsi, f'RSI14 {rs:.0f}'),
        (.08 * p_macd, 'negative MACD impulse'),
        (.08 * p_volume, f'selloff volume z {volume_z:.1f}'),
        (.10 * relative_penalty, f'20D vs VNINDEX {relative20 * 100:.1f}%'),
    ]
    drivers = [label for weight, label in sorted(contrib, reverse=True) if weight > .015][:4]
    weak = mom20 < 0 or trend50 < 0
    liquid = median_turnover20 >= MIN_MEDIAN_TURNOVER_20D
    if not liquid:
        status, phase = 'ILLIQUID', 'EXCLUDED_LOW_LIQUIDITY'
    elif dd60 <= -.15 and screen_score >= YELLOW_THRESHOLD:
        status, phase = 'RED', 'ACTIVE_DRAWDOWN'
    elif screen_score >= RED_THRESHOLD and weak:
        status, phase = 'RED', 'PRE_CRASH_RED'
    elif screen_score >= YELLOW_THRESHOLD and weak:
        status, phase = 'YELLOW', 'PRE_CRASH_YELLOW'
    elif screen_score >= WATCH_THRESHOLD and weak:
        status, phase = 'WATCH', 'WATCH'
    else:
        status, phase = 'GREEN', 'NORMAL'
    return {
        'date': rows[-1]['date'], 'close': raw[-1], 'ret1': ret1, 'ret5': ret5, 'mom20': mom20,
        'dd60': dd60, 'trend50': trend50, 'trend200': trend200, 'rsi14': rs,
        'volatilityPercentile': vp, 'volumeZ': volume_z, 'medianTurnover20': median_turnover20,
        'marketRelative20': relative20, 'technicalScore': technical, 'score': screen_score,
        'status': status, 'phase': phase, 'liquidEligible': liquid, 'drivers': drivers,
        'historyRows': len(rows), 'priceBasis': 'Yahoo adjusted close for model path; raw close for display/liquidity',
    }


def transition(prev_status, current_status):
    rank = {'GREEN': 0, 'WATCH': 1, 'YELLOW': 2, 'RED': 3}
    if not prev_status:
        return 'NEW', False
    if prev_status == current_status:
        return 'UNCHANGED', False
    if current_status not in rank or prev_status not in rank:
        return f'{prev_status} → {current_status}', False
    esc = rank[current_status] > rank[prev_status] and current_status in {'YELLOW', 'RED'}
    return f'{prev_status} → {current_status}', esc


def main():
    now = datetime.now(VN_TZ)
    previous = load_previous()
    universe = listing_universe()
    market_mom20 = market_momentum_20d()
    results, errors = [], []
    covered = 0
    low_history = 0

    def one(meta):
        rows, host = yahoo_history(meta['symbol'])
        f = scan_features(rows, market_mom20)
        return meta, rows, host, f

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(one, meta): meta for meta in universe}
        for fut in as_completed(futures):
            meta = futures[fut]
            try:
                meta, rows, host, f = fut.result()
                covered += 1
                if f is None:
                    low_history += 1
                    continue
                prev = previous.get(meta['symbol'], {})
                tr, escalated = transition(prev.get('status'), f['status'])
                results.append({**meta, **f, 'provider': host, 'transition': tr, 'newEscalation': escalated})
            except Exception as e:
                errors.append({'symbol': meta['symbol'], 'exchange': meta['exchange'], 'error': str(e)[:180]})

    if not results:
        raise RuntimeError('No securities produced usable market-scan features')
    dates = [x['date'] for x in results]
    model_date = Counter(dates).most_common(1)[0][0]
    stale = 0
    low_liquidity = 0
    for x in results:
        if x['date'] != model_date:
            x['stale'] = True
            x['status'] = 'STALE'
            x['phase'] = 'EXCLUDED_STALE_EOD'
            x['newEscalation'] = False
            stale += 1
        else:
            x['stale'] = False
        if not x['liquidEligible']:
            low_liquidity += 1

    eligible = [x for x in results if not x['stale'] and x['liquidEligible']]
    eligible.sort(key=lambda x: (x['score'], x['technicalScore']), reverse=True)
    red = [x for x in eligible if x['status'] == 'RED']
    yellow = [x for x in eligible if x['status'] == 'YELLOW']
    watch = [x for x in eligible if x['status'] == 'WATCH']
    escalations = [x for x in eligible if x.get('newEscalation')]
    attention = sorted(red + yellow, key=lambda x: (not x.get('newEscalation'), x['status'] != 'RED', -x['score']))[:30]

    payload = {
        'version': 'VMEWS-MARKET-SCAN-1.0.0',
        'generatedAt': now.isoformat(),
        'reviewDate': now.date().isoformat(),
        'modelDate': model_date,
        'scope': 'All listed common stocks returned by VCI across HOSE, HNX and UPCOM; non-stock instruments excluded.',
        'method': 'Cross-sectional T-day early-warning screen using adjusted EOD price path, technical deterioration, volatility regime, selloff volume, market-relative weakness and liquidity gating.',
        'thresholds': {
            'red': RED_THRESHOLD, 'yellow': YELLOW_THRESHOLD, 'watch': WATCH_THRESHOLD,
            'minHistorySessions': MIN_HISTORY, 'minMedianTurnover20dVnd': MIN_MEDIAN_TURNOVER_20D,
        },
        'coverage': {
            'listedUniverse': len(universe), 'priceCovered': covered, 'featureReady': len(results),
            'eligibleLiquidCurrent': len(eligible), 'lowHistoryExcluded': low_history,
            'lowLiquidityExcluded': low_liquidity, 'staleEodExcluded': stale, 'priceErrors': len(errors),
            'coverageRatio': covered / len(universe) if universe else 0.0,
        },
        'breadth': {
            'red': len(red), 'yellow': len(yellow), 'watch': len(watch),
            'newEscalations': len(escalations),
            'redShareEligible': len(red) / len(eligible) if eligible else 0.0,
            'yellowShareEligible': len(yellow) / len(eligible) if eligible else 0.0,
        },
        'marketContext': {'vnindexMomentum20d': market_mom20},
        'topAttention': attention,
        'redList': red,
        'yellowList': yellow,
        'newEscalations': escalations,
        'ranking': eligible,
        'errors': errors[:120],
        'sources': {
            'universe': 'VCI listing via vnstock Listing.symbols_by_exchange()',
            'priceHistory': 'Yahoo Finance chart API; .VN symbols; adjusted close preferred for model path',
            'marketContext': 'VMEWS VNINDEX EOD snapshot',
        },
        'governance': [
            'RED/YELLOW are screening states, not buy/sell recommendations or calibrated crash probabilities.',
            'Only securities with current EOD data, sufficient history and minimum 20-day median turnover can enter RED/YELLOW.',
            'Stale, newly listed and illiquid securities are reported in coverage but excluded from the morning attention list.',
            'A full deep-model review remains a second-stage action for flagged names.',
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'modelDate': model_date, 'listed': len(universe), 'covered': covered, 'eligible': len(eligible),
        'red': len(red), 'yellow': len(yellow), 'watch': len(watch), 'escalations': len(escalations), 'errors': len(errors)
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
