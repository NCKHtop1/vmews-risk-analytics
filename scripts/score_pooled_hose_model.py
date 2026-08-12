"""Daily inference for the frozen/promoted pooled HOSE champion.

This script never retrains or promotes a model. It rebuilds the current
completed-EOD cross-section with the exact production feature recipe and applies
the versioned model artifact produced by the dual-gate pooled trainer.
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


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = load('vmews_pool_base_daily', ROOT / 'scripts' / 'train_pooled_hose_model.py')


def current_from_rows(symbol, rows):
    _, current, _ = B.build_symbol_panel(symbol, rows)
    return current


def main():
    if not MODEL.exists():
        raise RuntimeError('No promoted pooled model artifact is available')
    bundle = joblib.load(MODEL)
    if not bundle.get('promotionPassed'):
        raise RuntimeError('Pooled predictive model artifact is not promotion-approved')
    if bundle.get('featureVersion') != B.FEATURE_VERSION:
        raise RuntimeError(f"Feature version mismatch: {bundle.get('featureVersion')} vs {B.FEATURE_VERSION}")

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
    prob = B.calibrate(platt, raw)
    sealed_ref = bundle['sealedReferenceProbabilities']
    base = float(bundle['sealedBaseRate'])
    standalone = bool(bundle.get('standaloneAlertApproved', False))
    evidence_grade = str(bundle.get('evidenceGrade') or 'MODERATE')
    scores = {}
    for row, rr, pp in zip(frame.to_dict('records'), raw, prob):
        scores[row['symbol']] = {
            'symbol': row['symbol'], 'modelAsOf': str(pd.Timestamp(row['date']).date()),
            'rawScore': float(rr), 'crashProbability': float(pp),
            'probabilityUsable': True, 'standaloneAlertApproved': standalone,
            'riskPercentile': B.percentile(sealed_ref, pp),
            'relativeRisk': float(pp / base) if base > 0 else None,
            'technical': float(row['technical']),
            'turnover20': float(math.expm1(row['logTurnover20'])),
            'domain': 'HOSE_CURRENT_LIQUID_PIT',
        }

    payload = {
        'version': bundle['version'], 'featureVersion': bundle['featureVersion'],
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'modelAsOf': str(pd.Timestamp(modal).date()),
        'champion': bundle['champion'], 'promotionPassed': True,
        'standaloneAlertApproved': standalone, 'evidenceGrade': evidence_grade,
        'trainingCutoff': bundle.get('trainingCutoff'),
        'calibrationCutoff': bundle.get('calibrationCutoff'),
        'sealedBaseRate': base, 'currentScored': len(scores),
        'historyCoverage': len(rows_by_symbol) / len(universe),
        'scores': scores, 'fetchErrors': errors[:30],
        'governance': (
            'Daily frozen pooled predictive-evidence inference only; no automatic retraining or model promotion. '
            + ('Standalone binary alert policy is approved.' if standalone else 'Standalone binary alert policy is NOT approved; pooled scores cannot create RED/YELLOW or autonomous actions.')
        )
    }
    SCORES.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'version': payload['version'], 'modelAsOf': payload['modelAsOf'],
                      'currentScored': len(scores), 'historyCoverage': payload['historyCoverage'],
                      'standaloneAlertApproved': standalone, 'evidenceGrade': evidence_grade}, indent=2))


if __name__ == '__main__':
    main()
