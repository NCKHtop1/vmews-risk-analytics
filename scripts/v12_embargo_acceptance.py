import json,pathlib
from datetime import datetime,timezone
DATA=pathlib.Path('data');model=json.loads((DATA/'forecast-model-v12.json').read_text(encoding='utf-8'));rows=[];bad=[]
for h in range(1,6):
    z=(model.get('horizons') or {}).get(str(h),{});e=z.get('embargoAudit') or {};wf=z.get('walkForwardReplay') or {}
    checks={
        'horizon':int(e.get('horizon') or -1)==h,
        'labelPurgeSessions':int(e.get('labelPurgeSessions') or -1)==h,
        'calibrationBoundaryEmbargoSessions':int(e.get('calibrationBoundaryEmbargoSessions') or -1)==h,
        'orderedCalA':str(e.get('calAStart') or '')<str(e.get('calAEndExclusive') or '')<=str(e.get('calBStart') or ''),
        'orderedCalB':str(e.get('calBStart') or '')<str(e.get('calBEndExclusive') or '')<=str(e.get('sealedAuditStart') or ''),
        'walkForwardPurge':int(wf.get('purgeSessions') or -1)==h,
        'walkForwardNoFutureTraining':int(wf.get('futureRowsUsedForTraining') or -1)==0,
    }
    row={'horizon':h,'checks':checks,'embargoAudit':e,'walkForwardStatus':wf.get('status')};rows.append(row)
    if not all(checks.values()):bad.append(row)
out={'version':'VMEWS-EMBARGO-GATE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS' if not bad else 'FAIL','horizons':rows,'failures':bad,'policy':'T+h model labels are purged before prediction origin; calibration and conformal blocks end h sessions before the next block so no label matures inside the following calibration/sealed-audit block.'};(DATA/'embargo-gate-v12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(0 if not bad else 1)
