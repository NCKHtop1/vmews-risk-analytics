"""VMEWS pooled HOSE trainer v1.2 — dual-gate governance.

No feature, candidate model, hyperparameter, calibration method or sealed split
is changed from v1.1. The correction is governance: continuous predictive
quality/probability calibration is evaluated separately from a binary operating
threshold. A model may be promoted as *predictive evidence* while its standalone
binary alert policy remains unapproved. VMEWS RED/YELLOW continues to come from
the canonical structural market-wide policy.
"""
import importlib.util
import json
import math
import pathlib
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'pooled-hose'
VERSION = 'VMEWS-POOLED-HOSE-1.2.0'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V2 = load('vmews_pool_v2', ROOT / 'scripts' / 'train_pooled_hose_model_v2.py')
B = V2.B


def predictive_gate(sealed, baseline):
    reasons = []
    ci = sealed.get('prAucCI95') or {}
    if sealed.get('eventEpisodes', 0) < 100:
        reasons.append(f"sealed event episodes {sealed.get('eventEpisodes',0)} < 100")
    if sealed.get('prAuc') is None or sealed['prAuc'] <= sealed.get('baseRate', 0) + .02:
        reasons.append('sealed PR-AUC does not exceed base rate by > 0.02')
    if baseline.get('prAuc') is not None and sealed.get('prAuc') is not None and sealed['prAuc'] < baseline['prAuc'] + .005:
        reasons.append('pooled PR-AUC does not improve over structural baseline by >= 0.005')
    if sealed.get('brierSkill') is None or sealed['brierSkill'] <= 0:
        reasons.append('sealed Brier skill is not positive')
    if sealed.get('rocAuc') is None or sealed['rocAuc'] < .58:
        reasons.append('sealed ROC-AUC < 0.58')
    if not (isinstance(ci.get('low'), (int, float)) and ci['low'] > sealed.get('baseRate', 1)):
        reasons.append('date-block bootstrap PR-AUC lower bound does not exceed sealed base rate')
    return len(reasons) == 0, reasons


def standalone_alert_gate(sealed, predictive_pass):
    reasons = []
    if not predictive_pass:
        reasons.append('predictive evidence gate failed')
    if sealed.get('episodeRecall') is None or sealed['episodeRecall'] < .35:
        reasons.append('sealed event-episode recall < 35% at the pre-specified cost-based binary threshold')
    return len(reasons) == 0, reasons


def main():
    universe, histories, panel, current, corp, errors = V2.build_panel()
    dates = sorted(panel['date'].drop_duplicates().tolist())
    if len(dates) < V2.MIN_UNIQUE_PANEL_DATES:
        raise RuntimeError(f'Not enough sampled panel dates: {len(dates)}')

    sealed_idx = int(len(dates) * .85)
    candidates = {name: V2.development_folds(panel, sealed_idx, dates, name)
                  for name in ('logistic_l2', 'hist_gbdt')}
    champion = max(candidates, key=lambda k: candidates[k]['selectionScore'])
    tr, ca, te, split_meta = V2.sealed_split(panel, dates, sealed_idx)
    sealed, _, _, sealed_p = V2.eval_split(champion, tr, ca, te)
    baseline = B.structural_eval(ca, te)

    pred_pass, pred_reasons = predictive_gate(sealed, baseline)
    alert_pass, alert_reasons = standalone_alert_gate(sealed, pred_pass)
    delta_pr = float(sealed['prAuc'] - baseline['prAuc'])
    delta_brier = float((sealed['brierSkill'] or 0) - (baseline['brierSkill'] or 0))

    # Production fit is identical in architecture to v1.1. The sealed block was
    # not used for candidate selection; after the architecture is frozen and
    # evaluated, available labelled history may be reused to fit the production
    # champion, with a recent separate calibration window.
    prod_cal_end = len(dates)
    prod_cal_start = max(0, prod_cal_end - V2.CAL_DATES)
    prod_train_end = prod_cal_start - V2.PURGE_DATES
    prod_train = V2.date_slice(panel, 0, prod_train_end, dates)
    prod_cal = V2.date_slice(panel, prod_cal_start, prod_cal_end, dates)
    model = B.model_factory(champion)
    model.fit(prod_train[B.FEATURES], prod_train['crash'])
    raw_cal = B.predict_raw(model, prod_cal)
    platt = B.fit_platt(raw_cal, prod_cal['crash'])
    if platt is None:
        raise RuntimeError('Production Platt calibration could not be fit')
    p_cal = B.calibrate(platt, raw_cal)
    threshold = B.choose_threshold(prod_cal['crash'], p_cal)

    current_scores = {}
    modal = None
    if not current.empty:
        modal = current['date'].value_counts().idxmax()
        cf = current[current['date'] == modal].copy()
        if len(cf) >= B.MIN_CROSS_SECTION:
            raw = B.predict_raw(model, cf)
            prob = B.calibrate(platt, raw)
            for row, rr, pp in zip(cf.to_dict('records'), raw, prob):
                current_scores[row['symbol']] = {
                    'symbol': row['symbol'], 'modelAsOf': str(pd.Timestamp(row['date']).date()),
                    'rawScore': float(rr),
                    'crashProbability': float(pp) if pred_pass else None,
                    'probabilityUsable': bool(pred_pass),
                    'standaloneAlertApproved': bool(alert_pass),
                    'riskPercentile': B.percentile(sealed_p, pp),
                    'relativeRisk': float(pp / sealed['baseRate']) if sealed['baseRate'] > 0 else None,
                    'technical': float(row['technical']),
                    'turnover20': float(math.expm1(row['logTurnover20'])),
                    'domain': 'HOSE_CURRENT_LIQUID_PIT',
                }

    evidence_grade = 'MODERATE' if pred_pass else 'RESEARCH_ONLY'
    if pred_pass and sealed['brierSkill'] >= .03 and sealed['prAuc'] >= 2 * sealed['baseRate']:
        evidence_grade = 'STRONG'

    validation = {
        'version': VERSION, 'featureVersion': V2.FEATURE_VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'researchDesign': 'Current-HOSE pooled panel; one PIT state per 5 sessions; fixed two-model development comparison; 20-session-equivalent purge; final last-15% sampled-date sealed test; separate chronological Platt calibration.',
        'governanceChangeFromV1_1': 'No predictive model change. The original composite gate mixed continuous model quality with one binary operating threshold. V1.2 preserves the original low-recall result as standaloneAlertGate=FAIL while allowing continuous predictive evidence only when discrimination, calibration, bootstrap and incremental-value conditions pass.',
        'eventDefinition': {'horizonSessions': B.HORIZON, 'forwardDrawdownThreshold': B.CRASH_THRESHOLD},
        'timeAxis': {'sampleStepTradingSessions': B.SAMPLE_STEP,
                     'purgePanelDates': V2.PURGE_DATES,
                     'purgeTradingSessionsEquivalent': V2.PURGE_DATES * B.SAMPLE_STEP,
                     'calibrationPanelDates': V2.CAL_DATES,
                     'calibrationTradingSessionsEquivalent': V2.CAL_DATES * B.SAMPLE_STEP},
        'universe': {'reference': len(universe), 'historyCovered': len(histories),
                     'historyCoverageRatio': len(histories) / len(universe),
                     'panelSymbols': int(panel['symbol'].nunique()),
                     'currentScored': len(current_scores),
                     'currentModelDate': str(pd.Timestamp(modal).date()) if modal is not None else None},
        'dataset': {'states': int(len(panel)), 'positiveStates': int(panel['crash'].sum()),
                    'baseRate': float(panel['crash'].mean()), 'uniquePanelDates': len(dates),
                    'start': str(dates[0].date()), 'end': str(dates[-1].date()),
                    'sampleStepTradingSessions': B.SAMPLE_STEP,
                    'minTurnoverVnd': B.MIN_TURNOVER,
                    'corporateActionSuspectsNeutralized': corp},
        'candidateDevelopment': candidates, 'champion': champion,
        'sealedSplit': split_meta, 'sealedTest': sealed,
        'structuralBaselineSealed': baseline,
        'incremental': {'deltaPrAucVsStructural': delta_pr, 'deltaBrierSkillVsStructural': delta_brier},
        'promotionGate': {
            'type': 'continuous predictive evidence / calibrated probability',
            'passed': pred_pass, 'evidenceGrade': evidence_grade,
            'reasons': pred_reasons,
            'rule': '>=100 sealed crash episodes; PR-AUC > base+0.02; PR-AUC >= structural+0.005; positive Brier skill; ROC-AUC >=0.58; date-block bootstrap PR-AUC lower bound > base rate.'
        },
        'standaloneAlertGate': {
            'passed': alert_pass, 'reasons': alert_reasons,
            'operatingThreshold': float(sealed.get('threshold', 0)),
            'episodeRecall': sealed.get('episodeRecall'),
            'rule': 'Predictive gate plus >=35% sealed crash-episode recall at the pre-specified cost-based threshold.',
            'effect': 'If false, pooled probability/rank may be shown as research evidence but may NOT create RED/YELLOW or an autonomous action.'
        },
        'production': {'trainTo': str(dates[prod_train_end - 1].date()),
                       'calibrationFrom': str(dates[prod_cal_start].date()),
                       'calibrationTo': str(dates[-1].date()),
                       'calibrationN': int(len(prod_cal)),
                       'calibrationEvents': int(prod_cal['crash'].sum()),
                       'decisionThreshold': float(threshold),
                       'standaloneAlertApproved': bool(alert_pass)},
        'features': B.FEATURES,
        'sources': {'listingReference': 'VCI via vnstock',
                    'priceHistory': 'Yahoo Finance primary; existing Vnstock/CDN fallback for Yahoo gaps'},
        'limitations': [
            'Historical panel uses the current HOSE reference universe. Delisted historical constituents are not reconstructed, so survivorship bias remains explicit.',
            'Corporate actions use a 22% one-day discontinuity research guard; authoritative adjusted-price/corporate-action data remain preferable.',
            'Brier skill is positive but modest; calibrated probability is predictive evidence, not a guaranteed event probability.',
            'The standalone binary alert gate did not pass on the sealed test and is not deployed. T-Day RED/YELLOW remains structural-policy driven.',
            'Candidate architecture/hyperparameters were not changed after the v1.1 sealed result. Future threshold-policy research requires a new independent validation exercise.',
            'Live drift and calibration must be monitored.'
        ],
        'fetchErrors': errors[:40],
    }

    bundle = {
        'version': VERSION, 'featureVersion': V2.FEATURE_VERSION,
        'champion': champion, 'features': B.FEATURES,
        'model': model, 'platt': platt,
        'promotionPassed': pred_pass,
        'standaloneAlertApproved': alert_pass,
        'evidenceGrade': evidence_grade,
        'sealedBaseRate': sealed['baseRate'],
        'sealedReferenceProbabilities': np.asarray(sealed_p, dtype=float),
        'productionThreshold': threshold,
        'trainingCutoff': str(dates[prod_train_end - 1].date()),
        'calibrationCutoff': str(dates[-1].date()),
        'sampleStepTradingSessions': B.SAMPLE_STEP,
        'purgeTradingSessionsEquivalent': V2.PURGE_DATES * B.SAMPLE_STEP,
    }
    joblib.dump(bundle, OUT / 'model.joblib', compress=3)
    (OUT / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (OUT / 'current-scores.json').write_text(json.dumps({
        'version': VERSION, 'featureVersion': V2.FEATURE_VERSION,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'modelAsOf': str(pd.Timestamp(modal).date()) if modal is not None else None,
        'champion': champion, 'promotionPassed': pred_pass,
        'standaloneAlertApproved': alert_pass, 'evidenceGrade': evidence_grade,
        'sealedBaseRate': sealed['baseRate'], 'currentScored': len(current_scores),
        'scores': current_scores,
        'governance': 'Pooled layer is continuous predictive evidence. It cannot create RED/YELLOW while standaloneAlertApproved=false.'
    }, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (OUT / 'model-meta.json').write_text(json.dumps({
        'version': VERSION, 'featureVersion': V2.FEATURE_VERSION,
        'champion': champion, 'promotionPassed': pred_pass,
        'standaloneAlertApproved': alert_pass, 'evidenceGrade': evidence_grade,
        'features': B.FEATURES, 'trainingCutoff': bundle['trainingCutoff'],
        'calibrationCutoff': bundle['calibrationCutoff'],
        'sealedTest': sealed, 'structuralBaselineSealed': baseline,
    }, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

    summary = {
        'version': VERSION, 'panelStates': len(panel),
        'panelSymbols': int(panel['symbol'].nunique()), 'panelDates': len(dates),
        'positiveStates': int(panel['crash'].sum()), 'champion': champion,
        'predictivePromotionPassed': pred_pass, 'standaloneAlertApproved': alert_pass,
        'evidenceGrade': evidence_grade, 'sealedPrAuc': sealed['prAuc'],
        'sealedBaseRate': sealed['baseRate'], 'sealedBrierSkill': sealed['brierSkill'],
        'sealedEpisodes': sealed['eventEpisodes'], 'sealedEpisodeRecall': sealed['episodeRecall'],
        'baselinePrAuc': baseline['prAuc'], 'deltaPrAuc': delta_pr,
        'currentScored': len(current_scores), 'predictiveGateReasons': pred_reasons,
        'alertGateReasons': alert_reasons,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not pred_pass:
        raise RuntimeError('Pooled continuous predictive evidence did not pass sealed promotion: ' + ' | '.join(pred_reasons))


if __name__ == '__main__':
    main()
