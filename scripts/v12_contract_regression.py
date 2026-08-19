from pathlib import Path
import subprocess,sys

# Zero is a valid leakage-counter value and must never be coerced to the missing sentinel -1.
acceptance=Path('scripts/v12_acceptance.py').read_text(encoding='utf-8')
embargo=Path('scripts/v12_embargo_acceptance.py').read_text(encoding='utf-8')
for script,source in (('scripts/v12_acceptance.py',acceptance),('scripts/v12_embargo_acceptance.py',embargo)):
    assert "int(wf.get('futureRowsUsedForTraining') or -1)==0" not in source,(script,'expert zero coercion')
    assert "int(wf.get('futureMetaRowsUsedForTraining') or -1)==0" not in source,(script,'meta zero coercion')
    assert "int(wf.get('futureCalibrationRowsUsedForTraining') or -1)==0" not in source,(script,'calibration zero coercion')
needle_expert="wf.get('futureRowsUsedForTraining') is not None and int(wf.get('futureRowsUsedForTraining'))==0"
assert needle_expert in acceptance,('scripts/v12_acceptance.py','expert explicit zero')
assert needle_expert in embargo,('scripts/v12_embargo_acceptance.py','expert explicit zero')
needle_meta="wf.get('futureMetaRowsUsedForTraining') is not None and int(wf.get('futureMetaRowsUsedForTraining'))==0"
needle_cal="wf.get('futureCalibrationRowsUsedForTraining') is not None and int(wf.get('futureCalibrationRowsUsedForTraining'))==0"
assert needle_meta in embargo,('scripts/v12_embargo_acceptance.py','meta explicit zero')
assert needle_cal in embargo,('scripts/v12_embargo_acceptance.py','calibration explicit zero')
wf={'status':'PASS','futureRowsUsedForTraining':0,'futureMetaRowsUsedForTraining':0,'futureCalibrationRowsUsedForTraining':0,'blocks':[1,2,3,4]}
for key in ('futureRowsUsedForTraining','futureMetaRowsUsedForTraining','futureCalibrationRowsUsedForTraining'):
    assert wf.get(key) is not None and int(wf[key])==0,(key,wf)
assert len(wf['blocks'])>=3
part=Path('scripts/v12_train_parts/02b_daily_audit_metrics.pyinc').read_text(encoding='utf-8')
for token in ('icDays','icPositiveDayShare','icBootstrap95','spreadTStat'):assert token in part,token

# Deterministic five-horizon assembly regression: horizon-specific event-prior metadata and T+h
# event outcome maps are merged, while unrelated common provenance corruption must still fail.
merge_src=Path('scripts/v12_merge_horizon_partials.py').read_text(encoding='utf-8')
for token in ('_validate_feature_contract','_merge_features','_merge_experts','_merge_events','scientificSemanticsChanged'):
    assert token in merge_src,('merge contract token',token)
from v12_merge_horizon_partials_test import main as merge_regression_main
merge_regression_main()

# Point selector V2 must match the actual final gate across multiple exact-maturity chronological
# OOS regimes. The sealed 90-100% block is evaluation-only; thresholds are unchanged and candidate
# magnitude is filtered by the existing gate rather than manufactured to satisfy it.
gate_src=Path('scripts/v12_train_parts/01em_gate_aligned_point.pyinc').read_text(encoding='utf-8')
for token in ('CHRONOLOGICAL_ORIGIN_DATE_POINT_SELECTION_V2','EXACT_MATURITY_PURGED_EXPANDING_ROLLING_ORIGIN','NO_CHANGE_ZERO_RETURN','XSEC_RANK_ONLY','marketDriftIntercept','sealedLabelsUsed','magnitude forcing'):
    assert token in gate_src,('gate V2 token',token)
assert '90-100% remains sealed' in gate_src
subprocess.run([sys.executable,'scripts/v12_point_selector_unit.py'],check=True)

# Keep the robust L1 expert family inside exact-maturity 50-70% model-kind selection. This affects
# the underlying direct score family only; it cannot see calibration or sealed labels.
robust_src=Path('scripts/v12_train_parts/01zz_robust_model_family.pyinc').read_text(encoding='utf-8')
assert "('RIDGE','LGBM','LGBM_L1')" in robust_src
assert 'LABEL_MATURITY_DATE' in robust_src and '50%-70%' in robust_src
print('V12 ACCEPTANCE + EMBARGO + POINT SELECTOR V2 + FIVE-HORIZON ASSEMBLY CONTRACT REGRESSION PASS')
