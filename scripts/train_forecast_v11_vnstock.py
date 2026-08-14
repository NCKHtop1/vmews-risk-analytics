"""Production entrypoint for Forecast V11 with VNStock as the primary EOD source."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))

import train_forecast_v11 as m
from vnstock_primary_history import vnstock_adjusted

_SOURCE_AUDIT = {}
_YAHOO = m.yahoo_adjusted
_LOCAL = m.local_rows


def _one_vnstock_first(sym):
    audit = None
    try:
        raw, audit = vnstock_adjusted(sym, years=9, min_rows=520)
        source = audit.get('source', 'VNSTOCK')
    except BaseException as ve:
        try:
            raw, ya = _YAHOO(sym, '10y', 15)
            source = 'YAHOO_ADJUSTED_FALLBACK'
            audit = {'source': source, 'symbol': sym, 'rows': len(raw),
                     'provider': ya.get('provider'), 'vnstockError': str(ve)[:500]}
        except BaseException as ye:
            raw = _LOCAL(sym)
            source = 'LOCAL_SNAPSHOT_LAST_RESORT'
            audit = {'source': source, 'symbol': sym, 'rows': len(raw),
                     'vnstockError': str(ve)[:500], 'yahooError': str(ye)[:500]}
    rows, fs = m.stock_features(raw)
    if len(rows) < 520 or len(fs) < 260:
        return sym, [], None
    out = []
    for f in fs:
        i = f['i']
        z = {'symbol': sym, 'source': source, **f,
             'avgTurnover30': float(sum(rows[j]['modelClose'] * rows[j]['volume']
                                           for j in range(max(0, i - 29), i + 1)) /
                                    max(1, i - max(0, i - 29) + 1))}
        for h in m.HORIZONS:
            z['y' + str(h)] = (float(math.log(rows[i + h]['modelClose'] / rows[i]['modelClose']))
                               if i + h < len(rows) else float('nan'))
        out.append(z)
    audit = dict(audit or {})
    audit['acceptedRows'] = len(rows)
    audit['acceptedStart'] = rows[0]['date']
    audit['acceptedEnd'] = rows[-1]['date']
    _SOURCE_AUDIT[sym] = audit
    return sym, out, {'symbol': sym, 'source': source, 'sourceAudit': audit,
                      'rows': rows, 'feature': out[-1]}


m.one = _one_vnstock_first

# train_forecast_v11_clean executes the full chronological DEV/CAL/AUD pipeline
# on import and leaves its accepted panel in CACHE.
import train_forecast_v11_clean as clean  # noqa: E402,F401

cur_path = ROOT / 'data' / 'forecast-current-v11.json'
cur = json.loads(cur_path.read_text(encoding='utf-8'))
latest = (clean.CACHE.get('panel') or (None, {}))[1]
source_counts = {}
for s, z in cur.get('symbols', {}).items():
    v = latest.get(s) or {}
    rows = v.get('rows') or []
    if rows:
        z['chart'] = [{'date': r['date'], 'close': float(r.get('modelClose', r['close'])),
                       'rawClose': float(r['close']), 'volume': float(r.get('volume') or 0),
                       'adjustmentFactor': float(r.get('adjustmentFactor', 1.0) or 1.0)}
                      for r in rows[-180:]]
    z['sourceAudit'] = v.get('sourceAudit') or _SOURCE_AUDIT.get(s) or {'source': z.get('source')}
    src = str(z.get('source') or 'UNKNOWN')
    source_counts[src] = source_counts.get(src, 0) + 1
cur['dataPolicy'] = {
    'version': 'VMEWS-DATA-POLICY-VNSTOCK-FIRST-1.0.0',
    'priority': ['VNStock Unified Market', 'VNStock VCI', 'VNStock KBS',
                 'Yahoo adjusted fallback', 'immutable local snapshot last resort'],
    'corporateActionGuard': 'Raw close retained; modelClose neutralizes one-session abs(log-return) > 0.18 reference-price discontinuities.',
    'sourceCounts': source_counts,
}
cur_path.write_text(json.dumps(cur, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

model_path = ROOT / 'data' / 'forecast-model-v11.json'
model = json.loads(model_path.read_text(encoding='utf-8'))
model['dataPolicy'] = cur['dataPolicy']
model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
print(json.dumps({'vnstockFirst': True, 'sourceCounts': source_counts, 'current': cur.get('count')}, ensure_ascii=False))
