from pathlib import Path

# Zero is a valid leakage-counter value and must never be coerced to the missing sentinel -1.
# This regression protects both the broad research acceptance and the dedicated embargo gate.
for script in ('scripts/v12_acceptance.py','scripts/v12_embargo_acceptance.py'):
    source=Path(script).read_text(encoding='utf-8')
    assert "int(wf.get('futureRowsUsedForTraining') or -1)==0" not in source,(script,'expert zero coercion')
    assert "int(wf.get('futureMetaRowsUsedForTraining') or -1)==0" not in source,(script,'meta zero coercion')
    assert "int(wf.get('futureCalibrationRowsUsedForTraining') or -1)==0" not in source,(script,'calibration zero coercion')
    assert "wf.get('futureRowsUsedForTraining') is not None and int(wf.get('futureRowsUsedForTraining'))==0" in source,(script,'expert explicit zero')
    assert "wf.get('futureMetaRowsUsedForTraining') is not None and int(wf.get('futureMetaRowsUsedForTraining'))==0" in source,(script,'meta explicit zero')
    assert "wf.get('futureCalibrationRowsUsedForTraining') is not None and int(wf.get('futureCalibrationRowsUsedForTraining'))==0" in source,(script,'calibration explicit zero')

wf={'status':'PASS','futureRowsUsedForTraining':0,'futureMetaRowsUsedForTraining':0,'futureCalibrationRowsUsedForTraining':0,'blocks':[1,2,3,4]}
assert wf.get('status')=='PASS'
for key in ('futureRowsUsedForTraining','futureMetaRowsUsedForTraining','futureCalibrationRowsUsedForTraining'):
    assert wf.get(key) is not None and int(wf[key])==0,(key,wf)
assert len(wf['blocks'])>=3

part=Path('scripts/v12_train_parts/02b_daily_audit_metrics.pyinc').read_text(encoding='utf-8')
for token in ('icDays','icPositiveDayShare','icBootstrap95','spreadTStat'): assert token in part,token
print('V12 ACCEPTANCE + EMBARGO ZERO-COUNTER CONTRACT REGRESSION PASS')
