"""VNStock-first daily OHLCV adapter for VMEWS Forecast V11.

Policy: VNStock Unified Market -> explicit VCI -> explicit KBS. The caller owns
any external fallback (Yahoo, immutable snapshot). Raw close is retained for
UI; modelClose removes only implausibly large one-session reference-price
jumps so corporate actions are not learned as market crashes/rallies.
"""
from __future__ import annotations

import math
import os
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
MIN_INTERVAL = float(os.environ.get('VNSTOCK_MIN_INTERVAL_SECONDS', '3.2'))
CA_LOG_JUMP = float(os.environ.get('VMEWS_CA_LOG_JUMP', '0.18'))
_LOCK = threading.Lock()
_LAST_CALL = 0.0


def _finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _date_text(v):
    try:
        if hasattr(v, 'date'):
            return v.date().isoformat()
    except Exception:
        pass
    s = str(v or '').strip()
    return s[:10] if len(s) >= 10 else s


def _normalize_df(df, symbol, provider):
    if df is None or len(df) == 0:
        raise RuntimeError(f'{symbol}: {provider} returned no OHLCV rows')
    cols = {str(c).strip().lower(): c for c in df.columns}
    tc = cols.get('time') or cols.get('date') or cols.get('trading_date')
    cc = cols.get('close')
    if tc is None or cc is None:
        raise RuntimeError(f'{symbol}: unexpected {provider} columns {list(df.columns)}')
    raw = []
    for _, r in df.iterrows():
        d = _date_text(r.get(tc)); c = _finite(r.get(cc))
        if not d or c is None or c <= 0:
            continue
        o = _finite(r.get(cols.get('open'))) if cols.get('open') is not None else None
        h = _finite(r.get(cols.get('high'))) if cols.get('high') is not None else None
        l = _finite(r.get(cols.get('low'))) if cols.get('low') is not None else None
        v = _finite(r.get(cols.get('volume'))) if cols.get('volume') is not None else 0.0
        raw.append({'date': d, 'open': o or c, 'high': h or c, 'low': l or c,
                    'close': c, 'volume': max(0.0, v or 0.0)})
    if not raw:
        raise RuntimeError(f'{symbol}: {provider} contained no usable rows')
    sample = [x['close'] for x in raw[-120:] if x['close'] > 0]
    med = statistics.median(sample) if sample else raw[-1]['close']
    scale = 1000.0 if med < 1000.0 else 1.0
    if scale != 1.0:
        for x in raw:
            for k in ('open', 'high', 'low', 'close'):
                x[k] *= scale
    ded = {x['date']: x for x in raw}
    return [ded[k] for k in sorted(ded)], scale


def _pace():
    global _LAST_CALL
    wait = MIN_INTERVAL - (time.monotonic() - _LAST_CALL)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL = time.monotonic()


def _corporate_action_guard(rows, threshold=CA_LOG_JUMP):
    rows = [dict(x) for x in rows]
    if not rows:
        return rows, []
    closes = [float(x['close']) for x in rows]
    factor = [1.0] * len(rows)
    running = 1.0
    events = []
    factor[-1] = 1.0
    for i in range(len(rows) - 1, 0, -1):
        ratio = closes[i] / closes[i - 1] if closes[i - 1] > 0 else 1.0
        if ratio > 0 and abs(math.log(ratio)) > threshold:
            running *= ratio
            events.append({'date': rows[i]['date'], 'rawCloseRatio': ratio,
                           'rawLogJump': math.log(ratio)})
        factor[i - 1] = running
    for i, x in enumerate(rows):
        x['modelClose'] = float(x['close']) * factor[i]
        x['adjustmentFactor'] = factor[i]
    events.reverse()
    return rows, events


def _unified(symbol, start, end):
    from vnstock.ui import Market
    df = Market().equity(symbol).ohlcv(start=start, end=end, interval='1D', count=4000)
    return _normalize_df(df, symbol, 'VNStock Unified Market')


def _explicit(symbol, source, start, end):
    from vnstock import Vnstock
    stock = Vnstock().stock(symbol=symbol, source=source)
    df = stock.quote.history(start=start, end=end, interval='1D')
    return _normalize_df(df, symbol, f'VNStock {source}')


def vnstock_adjusted(symbol, years=9, min_rows=520):
    today = datetime.now(VN_TZ).date()
    start = (today - timedelta(days=366 * years)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    attempts = [
        ('VNSTOCK_UNIFIED', lambda: _unified(symbol, start, end)),
        ('VNSTOCK_VCI', lambda: _explicit(symbol, 'VCI', start, end)),
        ('VNSTOCK_KBS', lambda: _explicit(symbol, 'KBS', start, end)),
    ]
    errors = []
    # V11 trainer is multi-threaded. Serialize guest VNStock calls so the model
    # cannot accidentally exceed the public request cadence.
    with _LOCK:
        for label, fn in attempts:
            try:
                _pace()
                rows, scale = fn()
                if len(rows) < min_rows:
                    errors.append(f'{label}: only {len(rows)} rows')
                    continue
                guarded, events = _corporate_action_guard(rows)
                return guarded, {
                    'source': label, 'symbol': symbol, 'rows': len(guarded),
                    'start': guarded[0]['date'], 'end': guarded[-1]['date'],
                    'unitNormalization': 'x1000 to VND' if scale == 1000.0 else 'already VND',
                    'corporateActionGuard': {'thresholdAbsLogReturn': CA_LOG_JUMP,
                                             'events': len(events), 'details': events[-12:]},
                }
            except BaseException as e:
                errors.append(f'{label}: {e}')
    raise RuntimeError(f'{symbol}: VNStock routes failed; ' + ' | '.join(errors))
