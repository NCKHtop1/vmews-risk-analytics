import math
import statistics
from datetime import datetime, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))


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


def vnstock_equity_history(symbol, years=11):
    """Fallback daily OHLCV for Vietnamese equities using Vnstock Unified UI.

    Vnstock free Market.equity(...).ohlcv() commonly returns equity prices in
    thousand-VND units. We detect that representation and normalize display/model
    prices back to VND so the series is compatible with the Yahoo path used by VMEWS.
    """
    from vnstock.ui import Market

    today = datetime.now(VN_TZ).date()
    start = (today - timedelta(days=366 * years)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    df = Market().equity(symbol).ohlcv(start=start, end=end, interval='1D')
    if df is None or len(df) == 0:
        raise RuntimeError(f'{symbol}: Vnstock returned no OHLCV rows')

    cols = {str(c).strip().lower(): c for c in df.columns}
    time_col = cols.get('time') or cols.get('date') or cols.get('trading_date')
    close_col = cols.get('close')
    if time_col is None or close_col is None:
        raise RuntimeError(f'{symbol}: unexpected Vnstock OHLCV columns {list(df.columns)}')

    raw = []
    for _, r in df.iterrows():
        d = _date_text(r.get(time_col))
        c = _finite(r.get(close_col))
        if not d or c is None or c <= 0:
            continue
        o = _finite(r.get(cols.get('open'))) if cols.get('open') is not None else None
        h = _finite(r.get(cols.get('high'))) if cols.get('high') is not None else None
        l = _finite(r.get(cols.get('low'))) if cols.get('low') is not None else None
        v = _finite(r.get(cols.get('volume'))) if cols.get('volume') is not None else 0.0
        raw.append({'date': d, 'open': o or c, 'high': h or c, 'low': l or c, 'close': c, 'volume': max(0.0, v or 0.0)})

    if not raw:
        raise RuntimeError(f'{symbol}: Vnstock OHLCV contained no usable rows')

    sample = [x['close'] for x in raw[-120:] if x['close'] > 0]
    med = statistics.median(sample) if sample else raw[-1]['close']
    scale = 1000.0 if med < 1000.0 else 1.0
    if scale != 1.0:
        for x in raw:
            for k in ('open', 'high', 'low', 'close'):
                x[k] *= scale

    ded = {x['date']: x for x in raw}
    rows = [ded[k] for k in sorted(ded)]
    return rows, {
        'source': 'Vnstock',
        'provider': 'Unified Market equity OHLCV (KBS/VCI routing)',
        'symbol': symbol,
        'rows': len(rows),
        'unitNormalization': 'x1000 to VND' if scale == 1000.0 else 'already VND',
        'ok': True,
    }
