import json
import pathlib
import importlib.util
import subprocess
from datetime import datetime, timezone, timedelta, time as dtime

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'market-scan.json'
VN_TZ = timezone(timedelta(hours=7))
POLICY = json.loads((ROOT / 'data' / 'alert-policy.json').read_text(encoding='utf-8'))

spec = importlib.util.spec_from_file_location('vmews_market_scan_legacy', ROOT / 'scripts' / 'update_market_scan.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)

bands = POLICY['riskIndexBands']
elig = POLICY['eligibility']
confirm = POLICY['marketConfirmation']
scan.VERSION = 'VMEWS-MARKET-SCAN-4.1.0'
scan.RED_THRESHOLD = float(bands['red'])
scan.YELLOW_THRESHOLD = float(bands['yellow'])
scan.WATCH_THRESHOLD = float(bands['watch'])
scan.MIN_AVG_TURNOVER_30D = float(elig['minAverageTurnover30dVnd'])


def upgrade_payload(payload, note=None):
    payload['version'] = scan.VERSION
    payload['policyVersion'] = POLICY['version']
    payload.setdefault('thresholds', {}).update({
        'red': scan.RED_THRESHOLD,
        'yellow': scan.YELLOW_THRESHOLD,
        'watch': scan.WATCH_THRESHOLD,
        'redMinIndependentSignals': confirm['redMinIndependentStressSignals'],
        'yellowMinIndependentSignals': confirm['yellowMinIndependentStressSignals'],
        'watchMinIndependentSignals': confirm['watchMinIndependentStressSignals'],
        'minAverageTurnover30dVnd': scan.MIN_AVG_TURNOVER_30D,
        'canonicalPolicy': POLICY['version'],
    })
    g = payload.setdefault('governance', [])
    canonical = f"Canonical alert policy: {POLICY['version']}; the same WATCH/YELLOW/RED risk-index bands are used by market scan, deep research and investor chart."
    if canonical not in g:
        g.insert(0, canonical)
    guard = 'Intraday overwrite guard: market-wide snapshots are published only from completed EOD/pre-session states; code pushes during the Vietnam cash session preserve the latest prior completed snapshot.'
    if guard not in g:
        g.insert(1, guard)
    if note:
        payload['snapshotGuardNote'] = note
    return payload


def load_previous_any_version():
    try:
        p = json.loads(OUT.read_text(encoding='utf-8'))
        return {x['symbol']: x for x in p.get('ranking', []) if x.get('symbol')}
    except Exception:
        return {}
scan.load_previous = load_previous_any_version


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


def in_vietnam_cash_session(now):
    return now.weekday() < 5 and dtime(8, 45) <= now.time() < dtime(15, 20)


def find_prior_completed_snapshot(today):
    """Find the newest committed market snapshot whose modelDate is before today."""
    try:
        commits = subprocess.check_output(
            ['git', 'log', '--format=%H', '--', 'data/market-scan.json'],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).splitlines()
    except Exception:
        return None
    for sha in commits[:80]:
        try:
            raw = subprocess.check_output(
                ['git', 'show', f'{sha}:data/market-scan.json'],
                cwd=ROOT, text=True, stderr=subprocess.DEVNULL
            )
            p = json.loads(raw)
            if p.get('modelDate') and p['modelDate'] < today:
                return p
        except Exception:
            continue
    return None


def guard_intraday():
    now = datetime.now(VN_TZ)
    if not in_vietnam_cash_session(now):
        return False
    today = now.date().isoformat()
    try:
        current = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception:
        current = None
    if current and current.get('modelDate') and current['modelDate'] < today:
        OUT.write_text(json.dumps(upgrade_payload(current, f'Intraday run at {now.isoformat()} skipped; retained completed EOD {current["modelDate"]}.'), ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'skippedIntraday': True, 'retainedModelDate': current['modelDate'], 'policyVersion': POLICY['version']}, ensure_ascii=False))
        return True
    prior = find_prior_completed_snapshot(today)
    if prior:
        prior['reviewDate'] = today
        prior['generatedAt'] = now.isoformat()
        OUT.write_text(json.dumps(upgrade_payload(prior, f'Intraday run at {now.isoformat()} restored prior completed EOD {prior.get("modelDate")} from repository history.'), ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'skippedIntraday': True, 'restoredModelDate': prior.get('modelDate'), 'policyVersion': POLICY['version']}, ensure_ascii=False))
        return True
    raise RuntimeError('Intraday market-wide refresh refused and no prior completed EOD snapshot could be recovered.')


if __name__ == '__main__':
    if not guard_intraday():
        scan.main()
        payload = json.loads(OUT.read_text(encoding='utf-8'))
        OUT.write_text(json.dumps(upgrade_payload(payload), ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'policyVersion': POLICY['version'], 'scannerVersion': scan.VERSION, 'modelDate': payload.get('modelDate')}, ensure_ascii=False))
