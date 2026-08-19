import json,pathlib
from datetime import datetime,timezone
DATA=pathlib.Path('data')
audit=json.loads((DATA/'active-flow-audit-v12.json').read_text(encoding='utf-8'))
model=json.loads((DATA/'forecast-model-v12.json').read_text(encoding='utf-8'))
features=[str(x) for x in model.get('featureNames') or []]
active_like=[x for x in features if any(k in x.lower() for k in ['activebuy','activesell','aggressor','unmatchedbuy','unmatchedsell','difvolumebuysell'])]
certified=audit.get('certified') is True and audit.get('numericalFeaturesEnabled') is True
abstained=audit.get('status')=='ABSTAIN' and audit.get('certified') is False and audit.get('numericalFeaturesEnabled') is False and not active_like
passed=bool(certified or abstained)
out={
  'version':'VMEWS-ACTIVE-FLOW-GATE-12.0.0',
  'generatedAt':datetime.now(timezone.utc).isoformat(),
  'status':'PASS' if passed else 'FAIL',
  'mode':'CERTIFIED' if certified else 'ABSTAIN' if abstained else 'INVALID',
  'activeFeaturesInNumericalModel':active_like,
  'audit':audit,
  'rule':'Active/aggressor flow may enter the numerical model only with a reproducible historical PIT source. If unavailable, the only acceptable state is explicit abstention with zero active-flow features in featureNames; missingness must never be encoded as neutral/zero signal.'
}
(DATA/'active-flow-gate-v12.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if passed else 1)
