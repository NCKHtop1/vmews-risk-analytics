"""Build V11 dashboard charts from the exact price history accepted by the model."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))

import build_dashboard_v11 as base

CUR = json.loads((ROOT / 'data' / 'forecast-current-v11.json').read_text(encoding='utf-8'))


def model_chart(symbol):
    z = (CUR.get('symbols') or {}).get(symbol) or {}
    rows = z.get('chart') or []
    return symbol, [{'date': r['date'], 'close': r['close'], 'rawClose': r.get('rawClose', r['close']),
                     'volume': r.get('volume', 0), 'adjustmentFactor': r.get('adjustmentFactor', 1.0)}
                    for r in rows[-160:]]


base.chart = model_chart
base.main()

p = ROOT / 'data' / 'forecast-dashboard-v11.json'
dash = json.loads(p.read_text(encoding='utf-8'))
dash['dataPolicy'] = CUR.get('dataPolicy') or {}
dash['chartLineage'] = 'Exact accepted model history; no independent chart refetch.'
dash['chartSources'] = {s: ((z.get('sourceAudit') or {}).get('source') or z.get('source') or 'UNKNOWN')
                        for s, z in (CUR.get('symbols') or {}).items()}
p.write_text(json.dumps(dash, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
print(json.dumps({'chartLineage': dash['chartLineage'], 'chartSymbols': dash.get('counts', {}).get('chartSymbols'),
                  'sourceCounts': (dash.get('dataPolicy') or {}).get('sourceCounts')}, ensure_ascii=False))
