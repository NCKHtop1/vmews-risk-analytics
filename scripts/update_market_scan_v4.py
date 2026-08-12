import json
import pathlib
import importlib.util

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / 'data' / 'alert-policy.json').read_text(encoding='utf-8'))

spec = importlib.util.spec_from_file_location('vmews_market_scan_legacy', ROOT / 'scripts' / 'update_market_scan.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)

bands = POLICY['riskIndexBands']
elig = POLICY['eligibility']
confirm = POLICY['marketConfirmation']
scan.VERSION = 'VMEWS-MARKET-SCAN-4.0.0'
scan.RED_THRESHOLD = float(bands['red'])
scan.YELLOW_THRESHOLD = float(bands['yellow'])
scan.WATCH_THRESHOLD = float(bands['watch'])
scan.MIN_AVG_TURNOVER_30D = float(elig['minAverageTurnover30dVnd'])

# Preserve transition continuity when moving from scanner v3.x to v4.
def load_previous_any_version():
    try:
        p = json.loads(scan.OUT.read_text(encoding='utf-8'))
        return {x['symbol']: x for x in p.get('ranking', []) if x.get('symbol')}
    except Exception:
        return {}
scan.load_previous = load_previous_any_version

# Bind confirmation counts to the canonical policy without duplicating scanner logic.
_orig_score_row = scan.score_row
def score_row_policy(row, market_mom20):
    out = _orig_score_row(row, market_mom20)
    if out is None or not out.get('liquidEligible'):
        return out
    score = float(out['score'])
    weak = out.get('mom20', 0) < 0 or out.get('trend50', 0) < 0
    n = int(out.get('independentStressSignals', 0))
    if score >= scan.RED_THRESHOLD and weak and n >= int(confirm['redMinIndependentStressSignals']):
        out['status'], out['phase'] = 'RED', 'MULTI_SIGNAL_RED'
    elif score >= scan.YELLOW_THRESHOLD and weak and n >= int(confirm['yellowMinIndependentStressSignals']):
        out['status'], out['phase'] = 'YELLOW', 'MULTI_SIGNAL_YELLOW'
    elif score >= scan.WATCH_THRESHOLD and weak and n >= int(confirm['watchMinIndependentStressSignals']):
        out['status'], out['phase'] = 'WATCH', 'WATCH'
    else:
        out['status'], out['phase'] = 'GREEN', 'NORMAL'
    return out
scan.score_row = score_row_policy

if __name__ == '__main__':
    scan.main()
    payload = json.loads(scan.OUT.read_text(encoding='utf-8'))
    payload['policyVersion'] = POLICY['version']
    payload['thresholds'].update({
        'redMinIndependentSignals': confirm['redMinIndependentStressSignals'],
        'yellowMinIndependentSignals': confirm['yellowMinIndependentStressSignals'],
        'watchMinIndependentSignals': confirm['watchMinIndependentStressSignals'],
        'canonicalPolicy': POLICY['version'],
    })
    payload['governance'].insert(0, f"Canonical alert policy: {POLICY['version']}; the same RED/YELLOW/WATCH risk-index bands are used by market scan, deep research and investor chart.")
    scan.OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'policyVersion': POLICY['version'], 'scannerVersion': payload['version']}, ensure_ascii=False))
