from pathlib import Path
acceptance=Path('scripts/v12_acceptance.py').read_text(encoding='utf-8')
assert "int(wf.get('futureRowsUsedForTraining') or -1)==0" not in acceptance
assert "wf.get('futureRowsUsedForTraining') is not None and int(wf.get('futureRowsUsedForTraining'))==0" in acceptance
wf={'status':'PASS','futureRowsUsedForTraining':0,'blocks':[1,2,3,4]}
assert wf.get('status')=='PASS' and wf.get('futureRowsUsedForTraining') is not None and int(wf['futureRowsUsedForTraining'])==0 and len(wf['blocks'])>=3
part=Path('scripts/v12_train_parts/02b_daily_audit_metrics.pyinc').read_text(encoding='utf-8')
for token in ('icDays','icPositiveDayShare','icBootstrap95','spreadTStat'): assert token in part,token
print('V12 ACCEPTANCE CONTRACT REGRESSION PASS')
