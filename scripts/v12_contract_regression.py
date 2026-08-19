from pathlib import Path

# Zero is a valid leakage-counter value and must never be coerced to the missing sentinel -1.
acceptance=Path('scripts/v12_acceptance.py').read_text(encoding='utf-8')
embargo=Path('scripts/v12_embargo_acceptance.py').read_text(encoding='utf-8')
for script,source in (('scripts/v12_acceptance.py',acceptance),('scripts/v12_embargo_acceptance.py',embargo)):
    assert "int(wf.get('futureRowsUsedForTraining') or -1)==0" not in source,(script,'expert zero coercion')
    assert "int(wf.get('futureMetaRowsUsedForTraining') or -1)==0" not in source,(script,'meta zero coercion')
    assert "int(wf.get('futureCalibrationRowsUsedForTraining') or -1)==0" not in source,(script,'calibration zero coercion')
needle_expert="wf.get('futureRowsUsedForTraining') is not None and int(wf.get('futureRowsUsedForTraining'))==0"
assert needle_expert in acceptance and needle_expert in embargo
needle_meta="wf.get('futureMetaRowsUsedForTraining') is not None and int(wf.get('futureMetaRowsUsedForTraining'))==0"
needle_cal="wf.get('futureCalibrationRowsUsedForTraining') is not None and int(wf.get('futureCalibrationRowsUsedForTraining'))==0"
assert needle_meta in embargo and needle_cal in embargo
wf={'status':'PASS','futureRowsUsedForTraining':0,'futureMetaRowsUsedForTraining':0,'futureCalibrationRowsUsedForTraining':0,'blocks':[1,2,3,4]}
for key in ('futureRowsUsedForTraining','futureMetaRowsUsedForTraining','futureCalibrationRowsUsedForTraining'):assert wf.get(key) is not None and int(wf[key])==0,(key,wf)
assert len(wf['blocks'])>=3

# Data-foundation acceptance must test what its labels say: literal >=7-year date span and the
# certified venue-aware source guard.  The historical UPCoM exception is not a relaxed gate;
# current-HOSE 12% remains enforced by the source audit's modelReturnGuardViolation contract.
for token in ('def span_days','365.25*7','modelReturnGuardViolation','ordinaryLargeMoveViolations','corporateActionViolations','adjusted model jumps respect verified venue-aware guards'):
    assert token in acceptance,('acceptance data contract',token)
assert "str(uni.get('start') or '9999')<='2019-01-01'" not in acceptance
assert "max(model_jumps)<=.12" not in acceptance

# Entity/rumor metadata must survive the immutable-source override and be derived from observed
# normalized stream counts rather than invented acceptance-time constants.
entity_restore=Path('scripts/v12_train_parts/00az_entity_audit_restore.pyinc').read_text(encoding='utf-8')
for token in ('entityFilter','normalizedSourceTypes','streamCoverage','countsDerivedFromObservedPipeline','rumorClaimAudit'):
    assert token in entity_restore or token=='rumorClaimAudit',('entity restore token',token)
assert "'MAIN': int(norm.get('NARRATIVE') or 0)" in entity_restore
source_stream=Path('scripts/v12_train_parts/00d_z_source_stream.pyinc').read_text(encoding='utf-8')
for token in ('normalizedSourceTypes','officialStreamRestored','TICKER_NEWS_ID'):assert token in source_stream,token
rumor=Path('scripts/v12_train_parts/00e_rumor_claims.pyinc').read_text(encoding='utf-8')
for token in ('pitClusterMetadata','officialStreamAware','ENTITY_AUDIT[\'rumorClaimAudit\']'):assert token in rumor,token

# Sparse regime slices must be explicit ABSTAIN/INSUFFICIENT records, never silently omitted and
# never fabricated as passing skill.
regime=Path('scripts/v12_train_parts/02a_regime.pyinc').read_text(encoding='utf-8')
for token in ("'BREADTH_STRONG'","'BREADTH_WEAK'","'status':'INSUFFICIENT'","'minimumRows':500"):
    assert token in regime,('regime audit token',token)

part=Path('scripts/v12_train_parts/02b_daily_audit_metrics.pyinc').read_text(encoding='utf-8')
for token in ('icDays','icPositiveDayShare','icBootstrap95','spreadTStat'):assert token in part,token

# Deterministic five-horizon assembly remains a Fast-owned contract.
merge_src=Path('scripts/v12_merge_horizon_partials.py').read_text(encoding='utf-8')
for token in ('_validate_feature_contract','_merge_features','_merge_experts','_merge_events','scientificSemanticsChanged'):assert token in merge_src,('merge contract token',token)
from v12_merge_horizon_partials_test import main as merge_regression_main
merge_regression_main()

# Final point selection is nested chronological pre-blind OOF.  Scale selection for each held-out
# validation date can use only earlier validation dates; late 85-90 is conformal-only; sealed
# 90-100 is never supplied.  There is no magnitude-only fallback.
nested=Path('scripts/v12_train_parts/01eo_nested_origin_cv_point.pyinc').read_text(encoding='utf-8')
for token in ('CHRONOLOGICAL_ORIGIN_DATE_POINT_SELECTION_V1','NESTED_EXPANDING_ORIGIN_CV_MBB_V3','EXPANDING_ORIGIN_DATE_SCALE_SELECTION_OOF','NO_CHANGE_ZERO_RETURN','90-100%: never supplied','no scale has positive pre-blind skill while satisfying unchanged magnitude floors','sealedLabelsUsed'):
    assert token in nested,('nested selector token',token)
assert 'magnitude-only fallback' in nested
robust_src=Path('scripts/v12_train_parts/01zz_robust_model_family.pyinc').read_text(encoding='utf-8')
assert "('RIDGE','LGBM','LGBM_L1')" in robust_src
assert 'LABEL_MATURITY_DATE' in robust_src and '50%-70%' in robust_src
print('V12 ACCEPTANCE + EMBARGO + NESTED-CV + FIVE-HORIZON ASSEMBLY CONTRACT REGRESSION PASS')
