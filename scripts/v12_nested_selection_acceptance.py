import json,pathlib
from datetime import datetime,timezone
DATA=pathlib.Path('data');m=json.loads((DATA/'forecast-model-v12.json').read_text(encoding='utf-8'));bad=[];rows=[]
for h in range(1,6):
    z=(m.get('horizons') or {}).get(str(h),{});choices=z.get('expertModelSelection') or {};prom=z.get('expertPromotion') or {};hrow={'horizon':h,'experts':{},'optional':{}}
    locks=[]
    for name in ['NUMERICAL','REGIME','EVENT','FLOW','FUNDAMENTAL_EVENT','RUMOR']:
        c=choices.get(name) or {};ok=bool(c.get('kind') in {'RIDGE','LGBM'} and c.get('selectionLockDate') and c.get('predictionAvailabilityEndExclusive') and c.get('selectionLockDate')<c.get('predictionAvailabilityEndExclusive') and '70%' in str(c.get('selectionWindow') or '') and '70%-80%' in str(c.get('incrementalOOSReserved') or ''))
        hrow['experts'][name]={'status':'PASS' if ok else 'FAIL','kind':c.get('kind'),'selectionLockDate':c.get('selectionLockDate'),'predictionAvailabilityEndExclusive':c.get('predictionAvailabilityEndExclusive'),'selectionRows':c.get('selectionRows')}
        if not ok:bad.append({'horizon':h,'expert':name,'type':'MODEL_KIND_SELECTION_NOT_LOCKED_PRE_INCREMENTAL','detail':c})
        if c.get('selectionLockDate'):locks.append(c.get('selectionLockDate'))
    for name in ['EVENT','FLOW','FUNDAMENTAL_EVENT','RUMOR']:
        p=prom.get(name) or {};ok=bool(p.get('modelKindSelectionLock') and p.get('selectionTestOriginStart') and p.get('selectionTestOriginEndExclusive') and p.get('modelKindSelectionLock')==p.get('selectionTestOriginStart') and p.get('selectionTestOriginStart')<p.get('selectionTestOriginEndExclusive') and p.get('selectionOutcomeMaturityBefore')==p.get('selectionTestOriginEndExclusive') and 'locked before' in str(p.get('nestedSelection') or ''))
        hrow['optional'][name]={'status':'PASS' if ok else 'FAIL','promoted':p.get('promoted'),'modelKindSelectionLock':p.get('modelKindSelectionLock'),'testStart':p.get('selectionTestOriginStart'),'testEndExclusive':p.get('selectionTestOriginEndExclusive'),'pValue':(p.get('incrementalICTest') or {}).get('pValue')}
        if not ok:bad.append({'horizon':h,'expert':name,'type':'INCREMENTAL_WINDOW_NOT_HELD_OUT_FROM_KIND_SELECTION','detail':p})
    hrow['commonKindLock']=len(set(locks))==1 if locks else False
    if not hrow['commonKindLock']:bad.append({'horizon':h,'type':'INCONSISTENT_KIND_LOCKS','locks':locks})
    rows.append(hrow)
out={'version':'VMEWS-NESTED-SELECTION-GATE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS' if not bad else 'FAIL','horizons':rows,'failures':bad,'policy':'Ridge/LightGBM kind selection is locked using chronological OOF origins 50%-70% only. Optional EVENT/FLOW/FUNDAMENTAL_EVENT/RUMOR incremental contribution is evaluated on the disjoint 70%-80% window with label-maturity purge and multiple-testing control. 80%-90% is distribution calibration; 90%-100% remains sealed audit.'};(DATA/'nested-selection-gate-v12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(0 if out['status']=='PASS' else 1)
