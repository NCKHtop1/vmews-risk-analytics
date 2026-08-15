from pathlib import Path

# Zero is a valid leakage-counter value and must never be coerced to the missing sentinel -1.
# The broad acceptance and the dedicated embargo gate expose slightly different contracts, so
# protect the patterns each script actually owns instead of requiring embargo-only counters in
# v12_acceptance.py.
acceptance=Path('scripts/v12_acceptance.py').read_text(encoding='utf-8')
embargo=Path('scripts/v12_embargo_acceptance.py').read_text(encoding='utf-8')
for script,source in (('scripts/v12_acceptance.py',acceptance),('scripts/v12_embargo_acceptance.py',embargo)):
    assert "int(wf.get('futureRowsUsedForTraining') or -1)==0" not in source,(script,'expert zero coercion')
    assert "int(wf.get('futureMetaRowsUsedForTraining') or -1)==0" not in source,(script,'meta zero coercion')
    assert "int(wf.get('futureCalibrationRowsUsedForTraining') or -1)==0" not in source,(script,'calibration zero coercion')

# Both gates inspect the expert-training counter and must accept an explicit zero.
needle_expert="wf.get('futureRowsUsedForTraining') is not None and int(wf.get('futureRowsUsedForTraining'))==0"
assert needle_expert in acceptance,('scripts/v12_acceptance.py','expert explicit zero')
assert needle_expert in embargo,('scripts/v12_embargo_acceptance.py','expert explicit zero')

# The dedicated embargo gate additionally owns meta-model and calibration chronology checks.
needle_meta="wf.get('futureMetaRowsUsedForTraining') is not None and int(wf.get('futureMetaRowsUsedForTraining'))==0"
needle_cal="wf.get('futureCalibrationRowsUsedForTraining') is not None and int(wf.get('futureCalibrationRowsUsedForTraining'))==0"
assert needle_meta in embargo,('scripts/v12_embargo_acceptance.py','meta explicit zero')
assert needle_cal in embargo,('scripts/v12_embargo_acceptance.py','calibration explicit zero')

wf={'status':'PASS','futureRowsUsedForTraining':0,'futureMetaRowsUsedForTraining':0,'futureCalibrationRowsUsedForTraining':0,'blocks':[1,2,3,4]}
assert wf.get('status')=='PASS'
for key in ('futureRowsUsedForTraining','futureMetaRowsUsedForTraining','futureCalibrationRowsUsedForTraining'):
    assert wf.get(key) is not None and int(wf[key])==0,(key,wf)
assert len(wf['blocks'])>=3

part=Path('scripts/v12_train_parts/02b_daily_audit_metrics.pyinc').read_text(encoding='utf-8')
for token in ('icDays','icPositiveDayShare','icBootstrap95','spreadTStat'): assert token in part,token
print('V12 ACCEPTANCE + EMBARGO ZERO-COUNTER CONTRACT REGRESSION PASS')
