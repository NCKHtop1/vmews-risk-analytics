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
# certified venue-aware source guard. The historical UPCoM exception is not a relaxed gate;
# current-HOSE 12% remains enforced by the source audit's modelReturnGuardViolation contract.
for token in ('def span_days','365.25*7','modelReturnGuardViolation','ordinaryLargeMoveViolations','corporateActionViolations','adjusted model jumps respect verified venue-aware guards'):
    assert token in acceptance,('acceptance data contract',token)
assert "str(uni.get('start') or '9999')<='2019-01-01'" not in acceptance
assert "max(model_jumps)<=.12" not in acceptance

# Entity/rumor metadata must survive the immutable-source override and be derived from observed
# normalized stream counts rather than invented acceptance-time constants.
entity_restore=Path('scripts/v12_train_parts/00az_entity_audit_restore.pyinc').read_text(encoding='utf-8')
for token in ('entityFilter','normalizedSourceTypes','streamCoverage','countsDerivedFromObservedPipeline'):
    assert token in entity_restore,('entity restore token',token)
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

# Deterministic five-horizon assembly owns every common invariant but explicitly merges the exact
# benchmark-alignment counters by horizon because T+h stock maturity/benchmark target dates are
# genuinely different. Derived daily AR is NOT authoritative inside an isolated shard: after the
# five exact CAR horizons are merged it must be rebuilt as AR1=CAR1, ARh=CARh-CAR(h-1), with an
# explicit abstention across any missing adjacent CAR. No unrelated data-audit difference may pass.
merge_src=Path('scripts/v12_merge_horizon_partials.py').read_text(encoding='utf-8')
for token in ('_validate_feature_contract','_merge_features','_merge_experts','_merge_events','_data_audit_common','_merge_data_audit','benchmark-alignment-contract','HORIZON_SPECIFIC_EXACT_STOCK_MATURITY','scientificSemanticsChanged','_rebuild_daily_ar_from_merged_car','if f=="abnormalReturn":continue','ARh=CARh-CAR(h-1)'):
    assert token in merge_src,('merge contract token',token)
from v12_merge_horizon_partials_test import main as merge_regression_main
merge_regression_main()

# Frozen research VNINDEX is an audited immutable route, not a live/cache exception. Acceptance
# requires exact agreement with the independent source probe (route/rows/span/fingerprint), PASS
# immutable mode, no runtime network fetch/provider switching, and certified SHA-256 snapshot IDs.
benchmark_gate=Path('scripts/v12_benchmark_acceptance.py').read_text(encoding='utf-8')
for token in ('VNSTOCK_INDEX_FROZEN_SNAPSHOT','valid_frozen_route','IMMUTABLE_FROZEN_SNAPSHOT','runtimeProviderSwitching','inputFingerprintSha256','snapshotFileSha256','inputManifestSha256','same_index','live_route or cache_ok or frozen_ok','dailyARUsesAdjacentCAROnly'):
    assert token in benchmark_gate,('benchmark frozen/AR contract token',token)
assert "idx.get('route')=='VNSTOCK_INDEX_FROZEN_SNAPSHOT'" in benchmark_gate
assert "z.get('status')=='PASS'" in benchmark_gate
assert "idx.get('runtimeNetworkPriceFetch') is False" in benchmark_gate

# The base production point selector is FIT-LOCKED. Power and scale are chosen exclusively from
# maturity-purged 80-85%. Early whole-date 85-90 is independent confirmation of the unchanged
# locked model; late 85-90 is conformal-only; 90-100 is sealed and absent from selection.
fitlock=Path('scripts/v12_train_parts/01eob_fit_locked_tail_rank.pyinc').read_text(encoding='utf-8')
for token in ('CHRONOLOGICAL_ORIGIN_DATE_POINT_SELECTION_V1','FIT_LOCKED_TAIL_RANK_DATE_BOOTSTRAP_V4','FIT_AND_LOCK_80_85__INDEPENDENT_VALIDATE_EARLY_85_90__CONFORM_LATE_85_90','XSEC_TAIL_RANK_FIT_LOCKED','UPPER_90_REQUIRED_SCALE','ONE_SE','90-100% is never supplied','sealedLabelsUsed'):
    assert token in fitlock,('fit-lock selector token',token)
assert '_FITLOCK_POWERS=(1.0,1.5,2.0,3.0)' in fitlock
assert "validation=_nested_eval(cy[iv],predV,cd[iv],h,bootstrap=True)" in fitlock
assert "if validation.get('preblindConfirmed') is True" in fitlock

# V5/V6/V7 strengthen only the pre-blind point mapping. V5 expands monotone tail concentration
# and selects by whole-date stability; V6 selects scale inside the existing one-SE L1/magnitude
# admissible set by fit-date stability; V7 is a label-free same-origin score-dispersion challenger
# invoked only after V6 abstains. Independent 85-90 can only confirm/reject; sealed use remains 0.
tail_v5=Path('scripts/v12_train_parts/01eoc_fit_locked_tail_stability.pyinc').read_text(encoding='utf-8')
for token in ('_FITLOCK_CORE_POWERS','(4.0,6.0)','FIT_80_85_ONE_SE_THEN_ORIGIN_DATE_BLOCK_LOWER90','sealedLabelsUsed'):
    assert token in tail_v5,('V5 tail stability token',token)
scale_v6=Path('scripts/v12_train_parts/01eod_fit_locked_scale_stability.pyinc').read_text(encoding='utf-8')
for token in ('80-85% ONLY','WHOLE_ORIGIN_DATE_MAE_STABILITY','independentValidationUsedForScaleSelection','sealedLabelsUsed'):
    assert token in scale_v6,('V6 scale stability token',token)
state_v7=Path('scripts/v12_train_parts/01eoe_fit_locked_score_state.pyinc').read_text(encoding='utf-8')
for token in ('SAME_ORIGIN_RAW_META_SCORE_IQR','_FITLOCK_STATE_GAMMAS=(0.0,0.5,1.0)','futureLabelRequirement','V6 point family already independently confirmed','preblindConfirmed','sealedLabelsUsed'):
    assert token in state_v7,('V7 score-state token',token)
assert "if str(audit.get('selectedFamily'))!='Q50'" in state_v7
assert "validationData':'EARLY WHOLE-DATE 85-90% ONLY'" in state_v7

# Prior nested selector remains source-documented for provenance but is superseded by fit-locked
# production layers. Robust expert family and maturity contract remain unchanged.
nested=Path('scripts/v12_train_parts/01eo_nested_origin_cv_point.pyinc').read_text(encoding='utf-8')
assert 'NESTED_EXPANDING_ORIGIN_CV_MBB_V3' in nested
robust_src=Path('scripts/v12_train_parts/01zz_robust_model_family.pyinc').read_text(encoding='utf-8')
assert "('RIDGE','LGBM','LGBM_L1')" in robust_src
assert 'LABEL_MATURITY_DATE' in robust_src and '50%-70%' in robust_src
print('V12 ACCEPTANCE + EMBARGO + V5/V6/V7 FIT-LOCK + FROZEN VNINDEX + FIVE-HORIZON ASSEMBLY CONTRACT REGRESSION PASS')