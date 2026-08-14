import json,pathlib
from datetime import datetime,timezone
DATA=pathlib.Path('data');model=json.loads((DATA/'forecast-model-v12.json').read_text(encoding='utf-8'));audit=json.loads((DATA/'data-audit-v12.json').read_text(encoding='utf-8'));sec=audit.get('sectorPIT') or {};features=set(model.get('featureNames') or []);forbidden=set(sec.get('candidateFields') or [])|{x for x in features if x.startswith('sectorRet') or x.startswith('sectorBreadth') or x.startswith('sectorRel') or x=='sectorAvailable'}
checks={
 'auditExists':bool(sec),
 'explicitAbstain':sec.get('status')=='ABSTAIN',
 'notPITCertified':sec.get('certified') is False and sec.get('pointInTimeEligible') is False,
 'numericalSectorDisabled':sec.get('numericalFeatureEnabled') is False,
 'historicalMembershipUnavailable':sec.get('historicalMembershipArchiveAvailable') is False,
 'currentReferenceCoverageAudited':float(sec.get('currentReferenceCoverage') or 0)>=.75,
 'noCurrentTaxonomyBackfilledIntoML':not any(x in features for x in forbidden),
 'reasonRecorded':bool(sec.get('reason')) and 'look-ahead' in str(sec.get('reason')).lower(),
}
out={'version':'VMEWS-SECTOR-PIT-GATE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'sectorAudit':sec,'forbiddenNumericalSectorFeatures':sorted(forbidden),'policy':'Sector reference is allowed as present-day descriptive metadata only. Historical ML use is blocked until an as-of/date-stamped sector-membership archive exists.'};(DATA/'sector-gate-v12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(0 if out['status']=='PASS' else 1)
