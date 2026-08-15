import json,pathlib
from datetime import datetime,timezone
DATA=pathlib.Path('data');model=json.loads((DATA/'forecast-model-v12.json').read_text(encoding='utf-8'));rows=[];bad=[]
for h in range(1,6):
    z=(model.get('horizons') or {}).get(str(h),{});e=z.get('embargoAudit') or {};wf=z.get('walkForwardReplay') or {};sealed=str(e.get('sealedAuditStart') or '')
    checks={
        'horizon':int(e.get('horizon') or -1)==h,
        'labelPurgeSessions':int(e.get('labelPurgeSessions') or -1)==h,
        'calibrationBoundaryEmbargoSessions':int(e.get('calibrationBoundaryEmbargoSessions') or -1)==h,
        'purgeUsesActualLabelMaturity':e.get('purgeMethod')=='LABEL_MATURITY_DATE' and e.get('ordinalOriginPurgeUsed') is False,
        'orderedCalA':str(e.get('calAStart') or '')<str(e.get('calAEndExclusive') or '')<=str(e.get('calBStart') or ''),
        'orderedCalB':str(e.get('calBStart') or '')<str(e.get('calBEndExclusive') or '')<=sealed,
        'modelLabelsMatureBefore80Lock':bool(e.get('maxModelTrainLabelMaturity')) and str(e.get('maxModelTrainLabelMaturity'))<str(e.get('modelTrainEndExclusive') or ''),
        'calALabelsMatureBefore85Lock':bool(e.get('maxCalALabelMaturity')) and str(e.get('maxCalALabelMaturity'))<str(e.get('calAEndExclusive') or ''),
        'calBLabelsMatureBeforeSealedAudit':bool(e.get('maxCalBLabelMaturity')) and str(e.get('maxCalBLabelMaturity'))<sealed,
        'walkForwardPurge':int(wf.get('purgeSessions') or -1)==h and wf.get('purgeMethod')=='LABEL_MATURITY_DATE' and wf.get('ordinalOriginPurgeUsed') is False,
        'walkForwardChronologyVerified':wf.get('chronologyVerified') is True,
        'walkForwardNoFutureExpertTraining':wf.get('futureRowsUsedForTraining') is not None and int(wf.get('futureRowsUsedForTraining'))==0,
        'walkForwardNoFutureMetaTraining':wf.get('futureMetaRowsUsedForTraining') is not None and int(wf.get('futureMetaRowsUsedForTraining'))==0 and str(wf.get('metaTrainMaxMaturity') or '')<str(wf.get('sealedAuditStart') or ''),
        'walkForwardNoFutureCalibration':wf.get('futureCalibrationRowsUsedForTraining') is not None and int(wf.get('futureCalibrationRowsUsedForTraining'))==0 and str(wf.get('calibrationMaxMaturity') or '')<str(wf.get('sealedAuditStart') or ''),
        'everyReplayBlockLabelSafe':bool(wf.get('blocks')) and all(x.get('noFutureLabelTraining') is True and str(x.get('maxTrainLabelMaturity') or '')<str(x.get('originBlockStart') or '') for x in wf.get('blocks') or []),
    }
    row={'horizon':h,'checks':checks,'embargoAudit':e,'walkForwardStatus':wf.get('status'),'walkForwardChronology':{k:wf.get(k) for k in ['purgeMethod','chronologyVerified','futureRowsUsedForTraining','futureMetaRowsUsedForTraining','futureCalibrationRowsUsedForTraining','metaTrainMaxMaturity','calibrationMaxMaturity','sealedAuditStart']}};rows.append(row)
    if not all(checks.values()):bad.append(row)
out={'version':'VMEWS-EMBARGO-GATE-12.1.1','generatedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS' if not bad else 'FAIL','horizons':rows,'failures':bad,'policy':'T+h rows are purged by the actual symbol-specific label maturity date, not by sampled-origin ordinal distance. Expert, meta, quantile/isotonic and conformal training must all mature strictly before the forecast or next sealed boundary.'};(DATA/'embargo-gate-v12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(0 if not bad else 1)
