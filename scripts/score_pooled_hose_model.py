"""Daily inference for the frozen/promoted pooled HOSE champion.

This script never retrains or promotes a model. It rebuilds the current
completed-EOD cross-section with the exact production feature recipe and applies
the frozen pooled champion. Post-freeze robustness governance can downgrade
absolute probability display without changing the underlying ranking model.
"""
import importlib.util
import json
import math
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import joblib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'pooled-hose'
MODEL = OUT / 'model.joblib'
SCORES = OUT / 'current-scores.json'
ROBUSTNESS = OUT / 'robustness.json'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = load('vmews_pool_base_daily', ROOT / 'scripts' / 'train_pooled_hose_model.py')


def current_from_rows(symbol, rows):
    _, current, _ = B.build_symbol_panel(symbol, rows)
    return current


def robust_governance():
    if not ROBUSTNESS.exists():
        raise RuntimeError('No post-freeze pooled robustness audit is available')
    p = json.loads(ROBUSTNESS.read_text(encoding='utf-8'))
    if p.get('modelVersion') != 'VMEWS-POOLED-HOSE-1.2.0':
        raise RuntimeError(f"Robustness/model mismatch: {p.get('modelVersion')}")
    rank = p.get('rankRobustnessGate') or {}
    prob = p.get('absoluteProbabilityGate') or {}
    if not rank.get('passed'):
        raise RuntimeError('Frozen pooled ranking has not passed the post-freeze robustness gate')
    buckets = p.get('riskBuckets') or []
    if len(buckets) != 10:
        raise RuntimeError('Pooled robustness audit does not contain 10 empirical sealed risk buckets')
    return p, rank, prob, buckets


def bucket_for_percentile(buckets, q):
    q = min(1.0, max(0.0, float(q)))
    k = min(10, max(1, int(math.ceil(max(q, 1e-12) * 10))))
    return next((x for x in buckets if int(x.get('bucket', 0)) == k), buckets[k-1])


def main():
    if not MODEL.exists():
        raise RuntimeError('No promoted pooled model artifact is available')
    bundle = joblib.load(MODEL)
    if not bundle.get('promotionPassed'):
        raise RuntimeError('Pooled predictive model artifact is not promotion-approved')
    if bundle.get('featureVersion') != B.FEATURE_VERSION:
        raise RuntimeError(f"Feature version mismatch: {bundle.get('featureVersion')} vs {B.FEATURE_VERSION}")
    robust, rank_gate, probability_gate, buckets = robust_governance()

    universe = B.hose_universe()
    rows_by_symbol, errors = {}, []
    with ThreadPoolExecutor(max_workers=12) as ex:
        fut = {ex.submit(B.fetch_one, m): m for m in universe}
        for f in as_completed(fut):
            sym, rows, _, err = f.result()
            if rows:
                rows_by_symbol[sym] = rows
            else:
                errors.append({'symbol': sym, 'error': err})
    if len(rows_by_symbol) / len(universe) < .90:
        raise RuntimeError(f'Daily history coverage too low: {len(rows_by_symbol)}/{len(universe)}')

    current_rows = []
    for sym, rows in rows_by_symbol.items():
        cur = current_from_rows(sym, rows)
        if cur:
            current_rows.append(cur)
    frame = B.add_cross_section(pd.DataFrame(current_rows), labelled=False)
    if frame.empty:
        raise RuntimeError('No current pooled cross-section was constructed')
    modal = frame['date'].value_counts().idxmax()
    frame = frame[frame['date'] == modal].copy()
    if len(frame) < B.MIN_CROSS_SECTION:
        raise RuntimeError(f'Current pooled cross-section too small: {len(frame)}')

    model, platt = bundle['model'], bundle['platt']
    raw = B.predict_raw(model, frame)
    internal_prob = B.calibrate(platt, raw)
    sealed_ref = bundle['sealedReferenceProbabilities']
    base = float(bundle['sealedBaseRate'])
    standalone = bool(bundle.get('standaloneAlertApproved', False))
    probability_usable = bool(probability_gate.get('passed'))
    rank_grade = str(rank_gate.get('grade') or 'MODERATE')
    scores = {}
    for row, rr, pp in zip(frame.to_dict('records'), raw, internal_prob):
        percentile = B.percentile(sealed_ref, pp)
        bucket = bucket_for_percentile(buckets, percentile)
        scores[row['symbol']] = {
            'symbol': row['symbol'],
            'modelAsOf': str(pd.Timestamp(row['date']).date()),
            'rawScore': float(rr),
            # This value is retained only so future matured live outcomes can
            # audit calibration stability. It is NOT user-facing and is NOT an
            # approved point probability while probabilityUsable is false.
            'auditCalibratedProbability': float(pp),
            'auditCalibrationUse': 'OUTCOME_MONITORING_ONLY_NOT_USER_FACING',
            # Absolute calibrated probability is intentionally withheld when
            # post-freeze sub-period calibration is unstable.
            'crashProbability': float(pp) if probability_usable else None,
            'probabilityUsable': probability_usable,
            'probabilityStatus': 'USABLE' if probability_usable else str(probability_gate.get('status') or 'WITHHELD'),
            'standaloneAlertApproved': standalone,
            'riskPercentile': percentile,
            'riskBucket': int(bucket['bucket']),
            'empiricalBucketEventRate': float(bucket['eventRate']),
            'empiricalBucketLiftVsBase': float(bucket['liftVsBase']) if bucket.get('liftVsBase') is not None else None,
            'sealedBaseRate': base,
            'technical': float(row['technical']),
            'turnover20': float(math.expm1(row['logTurnover20'])),
            'domain': 'HOSE_CURRENT_LIQUID_PIT',
        }

    payload = {
        'version': bundle['version'], 'featureVersion': bundle['featureVersion'],
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'modelAsOf': str(pd.Timestamp(modal).date()),
        'champion': bundle['champion'], 'promotionPassed': True,
        'rankRobustnessPassed': True, 'rankEvidenceGrade': rank_grade,
        'absoluteProbabilityUsable': probability_usable,
        'absoluteProbabilityStatus': 'USABLE' if probability_usable else str(probability_gate.get('status') or 'WITHHELD'),
        'absoluteProbabilityReasons': probability_gate.get('reasons') or [],
        'standaloneAlertApproved': standalone,
        'trainingCutoff': bundle.get('trainingCutoff'),
        'calibrationCutoff': bundle.get('calibrationCutoff'),
        'sealedBaseRate': base, 'currentScored': len(scores),
        'historyCoverage': len(rows_by_symbol) / len(universe),
        'robustnessVersion': robust.get('version'),
        'scores': scores, 'fetchErrors': errors[:30],
        'governance': (
            'Daily frozen pooled ranking inference only; no automatic retraining or model promotion. '
            + ('Absolute calibrated probability passed stability audit. ' if probability_usable else 'Absolute calibrated probability is WITHHELD because post-freeze calibration stability did not pass. ')
            + ('Standalone binary alert policy is approved.' if standalone else 'Standalone binary alert policy is NOT approved; pooled evidence cannot create RED/YELLOW or autonomous actions.')
            + ' Internal calibrated scores are retained only for future matured-outcome calibration monitoring and are not user-facing probabilities while the probability gate is withheld.'
        )
    }
    SCORES.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({
        'version': payload['version'], 'modelAsOf': payload['modelAsOf'],
        'currentScored': len(scores), 'historyCoverage': payload['historyCoverage'],
        'rankEvidenceGrade': rank_grade, 'absoluteProbabilityUsable': probability_usable,
        'standaloneAlertApproved': standalone,
    }, indent=2))


if __name__ == '__main__':
    main()
