"""VMEWS pooled HOSE champion/challenger trainer v1.1.

This module deliberately reuses the already-reviewed panel construction/model
helpers from train_pooled_hose_model.py, but fixes the time axis for a panel
sampled every five trading sessions. All purges/calibration windows below are
expressed in sampled panel dates only after being converted from trading
sessions. Candidate choice is made on development folds; the final last-15%
date block is sealed and used once for promotion.
"""
import importlib.util
import json
import math
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'pooled-hose'
OUT.mkdir(parents=True, exist_ok=True)
VERSION = 'VMEWS-POOLED-HOSE-1.1.0'
FEATURE_VERSION = 'PANEL-PIT-PRICE-LIQUIDITY-1.0'
PURGE_TRADING_SESSIONS = 20
CALIBRATION_TRADING_SESSIONS = 126
MIN_UNIQUE_PANEL_DATES = 420


def _load_base():
    path = ROOT / 'scripts' / 'train_pooled_hose_model.py'
    spec = importlib.util.spec_from_file_location('vmews_pool_base', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load_base()
PURGE_DATES = max(1, math.ceil(PURGE_TRADING_SESSIONS / B.SAMPLE_STEP))
CAL_DATES = max(12, math.ceil(CALIBRATION_TRADING_SESSIONS / B.SAMPLE_STEP))


def date_slice(df, start_idx, end_idx, dates):
    if start_idx >= end_idx:
        return df.iloc[0:0].copy()
    lo, hi = dates[start_idx], dates[end_idx - 1]
    return df[(df['date'] >= lo) & (df['date'] <= hi)].copy()


def eval_split(name, train, cal, test):
    model = B.model_factory(name)
    model.fit(train[B.FEATURES], train['crash'])
    raw_cal = B.predict_raw(model, cal)
    calibrator = B.fit_platt(raw_cal, cal['crash'])
    p_cal = B.calibrate(calibrator, raw_cal)
    threshold = B.choose_threshold(cal['crash'], p_cal)
    raw_test = B.predict_raw(model, test)
    p_test = B.calibrate(calibrator, raw_test)
    out = B.metrics(test, p_test, threshold)
    out['calibrationN'] = int(len(cal))
    out['calibrationEvents'] = int(cal['crash'].sum())
    out['prAucCI95'] = B.bootstrap_pr_ci(test, p_test)
    return out, model, calibrator, p_test


def dev_fold(df, dates, dev_n, train_frac, cal_frac, test_frac, model_name):
    train_end = int(dev_n * train_frac)
    cal_start = train_end + PURGE_DATES
    cal_end = int(dev_n * cal_frac)
    test_start = cal_end + PURGE_DATES
    test_end = int(dev_n * test_frac)
    if test_end > dev_n:
        test_end = dev_n
    if min(train_end, cal_end - cal_start, test_end - test_start) <= 0:
        return None
    tr = date_slice(df, 0, train_end, dates)
    ca = date_slice(df, cal_start, cal_end, dates)
    te = date_slice(df, test_start, test_end, dates)
    if len(tr) < 5000 or len(ca) < 900 or len(te) < 900:
        return None
    if ca['crash'].sum() < 20 or te['crash'].sum() < 20:
        return None
    m, _, _, _ = eval_split(model_name, tr, ca, te)
    m.update({
        'trainTo': str(dates[train_end - 1].date()),
        'calFrom': str(dates[cal_start].date()), 'calTo': str(dates[cal_end - 1].date()),
        'testFrom': str(dates[test_start].date()), 'testTo': str(dates[test_end - 1].date()),
        'purgeTradingSessionsEquivalent': PURGE_DATES * B.SAMPLE_STEP,
    })
    return m


def development_folds(df, sealed_idx, dates, model_name):
    # Fixed a priori expanding design. No hyperparameter/model changes are made
    # after observing the sealed block.
    specs = [(.44, .56, .68), (.56, .68, .80), (.68, .80, .96)]
    folds = []
    for a, b, c in specs:
        m = dev_fold(df, dates, sealed_idx, a, b, c, model_name)
        if m:
            folds.append(m)
    if len(folds) < 2:
        raise RuntimeError(f'Only {len(folds)} valid development folds for {model_name}')

    def avg(k):
        vals = [float(x[k]) for x in folds if x.get(k) is not None and math.isfinite(float(x[k]))]
        return float(np.mean(vals)) if vals else None

    base = avg('baseRate') or 0.0
    pr = avg('prAuc') or 0.0
    pr_skill = (pr - base) / max(.05, 1.0 - base)
    brier = avg('brierSkill') or 0.0
    return {
        'folds': folds, 'meanPrAuc': pr, 'meanBaseRate': base,
        'meanPrSkill': pr_skill, 'meanBrierSkill': brier,
        'selectionScore': pr_skill + .25 * max(0.0, brier),
    }


def sealed_split(df, dates, sealed_idx):
    cal_end = sealed_idx - PURGE_DATES
    cal_start = max(0, cal_end - CAL_DATES)
    train_end = cal_start - PURGE_DATES
    if train_end <= 0:
        raise RuntimeError('Sealed split leaves no training history')
    tr = date_slice(df, 0, train_end, dates)
    ca = date_slice(df, cal_start, cal_end, dates)
    te = date_slice(df, sealed_idx, len(dates), dates)
    meta = {
        'trainTo': str(dates[train_end - 1].date()),
        'calFrom': str(dates[cal_start].date()), 'calTo': str(dates[cal_end - 1].date()),
        'sealedFrom': str(dates[sealed_idx].date()), 'sealedTo': str(dates[-1].date()),
        'sampleStepTradingSessions': B.SAMPLE_STEP,
        'purgePanelDates': PURGE_DATES,
        'purgeTradingSessionsEquivalent': PURGE_DATES * B.SAMPLE_STEP,
        'calibrationPanelDates': CAL_DATES,
        'calibrationTradingSessionsEquivalent': CAL_DATES * B.SAMPLE_STEP,
    }
    return tr, ca, te, meta


def build_panel():
    universe = B.hose_universe()
    rows_by_symbol, sources, errors = {}, {}, []
    with ThreadPoolExecutor(max_workers=12) as ex:
        fut = {ex.submit(B.fetch_one, m): m for m in universe}
        for f in as_completed(fut):
            sym, rows, source, err = f.result()
            if rows:
                rows_by_symbol[sym] = rows
                sources[sym] = source
            else:
                errors.append({'symbol': sym, 'error': err})
    coverage = len(rows_by_symbol) / len(universe)
    if coverage < .90:
        raise RuntimeError(f'Price-history coverage too low: {len(rows_by_symbol)}/{len(universe)}')

    panel_rows, current_rows, corp = [], [], 0
    for sym, rows in rows_by_symbol.items():
        samples, current, suspects = B.build_symbol_panel(sym, rows)
        panel_rows.extend(samples)
        if current:
            current_rows.append(current)
        corp += len(suspects)
    panel = B.add_cross_section(pd.DataFrame(panel_rows), labelled=True)
    current = B.add_cross_section(pd.DataFrame(current_rows), labelled=False)
    if len(panel) < 30000 or panel['symbol'].nunique() < 150:
        raise RuntimeError(f'Pooled panel unexpectedly small: {len(panel)} states / {panel.symbol.nunique()} symbols')
    return universe, rows_by_symbol, panel, current, corp, errors


def main():
    universe, histories, panel, current, corp, errors = build_panel()
    dates = sorted(panel['date'].drop_duplicates().tolist())
    if len(dates) < MIN_UNIQUE_PANEL_DATES:
        raise RuntimeError(f'Not enough sampled panel dates: {len(dates)} < {MIN_UNIQUE_PANEL_DATES}')

    sealed_idx = int(len(dates) * .85)
    candidates = {name: development_folds(panel, sealed_idx, dates, name)
                  for name in ('logistic_l2', 'hist_gbdt')}
    champion = max(candidates, key=lambda k: candidates[k]['selectionScore'])

    tr, ca, te, split_meta = sealed_split(panel, dates, sealed_idx)
    sealed, _, _, sealed_p = eval_split(champion, tr, ca, te)
    baseline = B.structural_eval(ca, te)
    promoted, gate_reasons = B.promotion_gate(sealed, baseline)

    # Production fit uses the frozen champion. It does not re-open the sealed
    # block for model selection. The recent labelled window is calibration only.
    prod_cal_end = len(dates)
    prod_cal_start = max(0, prod_cal_end - CAL_DATES)
    prod_train_end = prod_cal_start - PURGE_DATES
    prod_train = date_slice(panel, 0, prod_train_end, dates)
    prod_cal = date_slice(panel, prod_cal_start, prod_cal_end, dates)
    prod_model = B.model_factory(champion)
    prod_model.fit(prod_train[B.FEATURES], prod_train['crash'])
    prod_raw_cal = B.predict_raw(prod_model, prod_cal)
    prod_platt = B.fit_platt(prod_raw_cal, prod_cal['crash'])
    if prod_platt is None:
        raise RuntimeError('Production Platt calibration could not be fit')
    prod_p_cal = B.calibrate(prod_platt, prod_raw_cal)
    prod_threshold = B.choose_threshold(prod_cal['crash'], prod_p_cal)

    current_scores = {}
    modal_date = None
    if not current.empty:
        modal_date = current['date'].value_counts().idxmax()
        cf = current[current['date'] == modal_date].copy()
        if len(cf) >= B.MIN_CROSS_SECTION:
            raw = B.predict_raw(prod_model, cf)
            prob = B.calibrate(prod_platt, raw)
            for row, rr, pp in zip(cf.to_dict('records'), raw, prob):
                current_scores[row['symbol']] = {
                    'symbol': row['symbol'], 'modelAsOf': str(pd.Timestamp(row['date']).date()),
                    'rawScore': float(rr),
                    'crashProbability': float(pp) if promoted else None,
                    'probabilityUsable': bool(promoted),
                    'riskPercentile': B.percentile(sealed_p, pp),
                    'relativeRisk': float(pp / sealed['baseRate']) if sealed['baseRate'] > 0 else None,
                    'technical': float(row['technical']),
                    'turnover20': float(math.expm1(row['logTurnover20'])),
                    'domain': 'HOSE_CURRENT_LIQUID_PIT',
                }

    validation = {
        'version': VERSION, 'featureVersion': FEATURE_VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'researchDesign': 'Current-HOSE pooled panel; one state per 5 sessions; date-based expanding development folds; 20-trading-session-equivalent purges; final last-15% sampled-date block sealed for promotion; chronological Platt calibration.',
        'eventDefinition': {'horizonSessions': B.HORIZON, 'forwardDrawdownThreshold': B.CRASH_THRESHOLD},
        'timeAxis': {'sampleStepTradingSessions': B.SAMPLE_STEP, 'purgePanelDates': PURGE_DATES,
                     'purgeTradingSessionsEquivalent': PURGE_DATES * B.SAMPLE_STEP,
                     'calibrationPanelDates': CAL_DATES,
                     'calibrationTradingSessionsEquivalent': CAL_DATES * B.SAMPLE_STEP},
        'universe': {'reference': len(universe), 'historyCovered': len(histories),
                     'historyCoverageRatio': len(histories) / len(universe),
                     'panelSymbols': int(panel['symbol'].nunique()),
                     'currentScored': len(current_scores),
                     'currentModelDate': str(pd.Timestamp(modal_date).date()) if modal_date is not None else None},
        'dataset': {'states': int(len(panel)), 'positiveStates': int(panel['crash'].sum()),
                    'baseRate': float(panel['crash'].mean()), 'uniquePanelDates': len(dates),
                    'start': str(dates[0].date()), 'end': str(dates[-1].date()),
                    'sampleStepTradingSessions': B.SAMPLE_STEP,
                    'minTurnoverVnd': B.MIN_TURNOVER,
                    'corporateActionSuspectsNeutralized': corp},
        'candidateDevelopment': candidates, 'champion': champion,
        'sealedSplit': split_meta, 'sealedTest': sealed,
        'structuralBaselineSealed': baseline,
        'incremental': {
            'deltaPrAucVsStructural': float(sealed['prAuc'] - baseline['prAuc']),
            'deltaBrierSkillVsStructural': float((sealed['brierSkill'] or 0) - (baseline['brierSkill'] or 0)),
        },
        'promotionGate': {
            'passed': promoted, 'reasons': gate_reasons,
            'rule': '>=100 sealed crash episodes; PR-AUC > base+0.02 and >= structural+0.005; positive Brier skill; ROC-AUC >=0.58; crash-episode recall >=35%.',
        },
        'production': {'trainTo': str(dates[prod_train_end - 1].date()),
                       'calibrationFrom': str(dates[prod_cal_start].date()),
                       'calibrationTo': str(dates[-1].date()),
                       'calibrationN': int(len(prod_cal)),
                       'calibrationEvents': int(prod_cal['crash'].sum()),
                       'decisionThreshold': float(prod_threshold)},
        'features': B.FEATURES,
        'sources': {'listingReference': 'VCI via vnstock',
                    'priceHistory': 'Yahoo Finance primary; existing Vnstock/CDN fallback for Yahoo gaps'},
        'limitations': [
            'Historical panel uses the current HOSE reference universe. Delisted historical constituents are not reconstructed, so survivorship bias remains an explicit limitation.',
            'Corporate actions use a 22% one-day discontinuity research guard. Authoritative adjusted-price/corporate-action data remain preferable.',
            'This is a 20-session drawdown risk classifier, not a buy/sell model or guaranteed forecast.',
            'Candidate choice is frozen before the sealed block. The sealed block is a promotion test, not a tuning set.',
            'Future live performance must be monitored for drift and calibration decay.'
        ],
        'fetchErrors': errors[:40],
    }

    bundle = {
        'version': VERSION, 'featureVersion': FEATURE_VERSION,
        'champion': champion, 'features': B.FEATURES,
        'model': prod_model, 'platt': prod_platt,
        'promotionPassed': promoted,
        'sealedBaseRate': sealed['baseRate'],
        'sealedReferenceProbabilities': np.asarray(sealed_p, dtype=float),
        'productionThreshold': prod_threshold,
        'trainingCutoff': str(dates[prod_train_end - 1].date()),
        'calibrationCutoff': str(dates[-1].date()),
        'sampleStepTradingSessions': B.SAMPLE_STEP,
        'purgeTradingSessionsEquivalent': PURGE_DATES * B.SAMPLE_STEP,
    }
    joblib.dump(bundle, OUT / 'model.joblib', compress=3)
    (OUT / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (OUT / 'current-scores.json').write_text(json.dumps({
        'version': VERSION, 'generatedAt': datetime.now(timezone.utc).isoformat(),
        'modelAsOf': str(pd.Timestamp(modal_date).date()) if modal_date is not None else None,
        'champion': champion, 'promotionPassed': promoted,
        'sealedTest': sealed, 'scores': current_scores,
    }, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (OUT / 'model-meta.json').write_text(json.dumps({
        'version': VERSION, 'featureVersion': FEATURE_VERSION,
        'champion': champion, 'promotionPassed': promoted,
        'features': B.FEATURES, 'trainingCutoff': bundle['trainingCutoff'],
        'calibrationCutoff': bundle['calibrationCutoff'],
        'sealedTest': sealed, 'structuralBaselineSealed': baseline,
    }, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

    summary = {
        'version': VERSION, 'panelStates': len(panel),
        'panelSymbols': int(panel['symbol'].nunique()),
        'panelDates': len(dates), 'positiveStates': int(panel['crash'].sum()),
        'champion': champion, 'promotionPassed': promoted,
        'sealedPrAuc': sealed['prAuc'], 'sealedBaseRate': sealed['baseRate'],
        'sealedBrierSkill': sealed['brierSkill'],
        'sealedEpisodes': sealed['eventEpisodes'],
        'sealedEpisodeRecall': sealed['episodeRecall'],
        'baselinePrAuc': baseline['prAuc'],
        'deltaPrAuc': sealed['prAuc'] - baseline['prAuc'],
        'currentScored': len(current_scores), 'gateReasons': gate_reasons,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not promoted:
        raise RuntimeError('Pooled model did not pass the sealed promotion gate: ' + ' | '.join(gate_reasons))


if __name__ == '__main__':
    main()
