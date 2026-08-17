import json
from datetime import datetime, timezone
from v12_source_capture import build_source_capture_store

SYMBOLS = "ADS AFX BMI BRC BTP C32 C47 CLC CMV DBC DGC DXS EVE FMC GHC HAG IMP KBC KDH KHG KSB LHG LSS MSN NLG NNC NT2 ORS PAC PDV PVP REE SAV SFC SJD SMC STG TNI TPC TRC TSC VFG VND".split()
store,audits,failures=build_source_capture_store(SYMBOLS)
rows={}
for s in SYMBOLS:
    a=audits.get(s) or {}; attempts=a.get('attempts') or (failures.get(s) or {}).get('attempts') or []
    quality=[]
    for x in attempts:
        if 'QUALITY' not in str(x.get('stage') or ''): continue
        quality.append({'stage':x.get('stage'),'ok':x.get('ok'),'providerCode':x.get('providerCode'),'referenceProviderCode':x.get('referenceProviderCode'),'rows':x.get('rows'),'eligible':x.get('eligible'),'ineligibleReasons':x.get('ineligibleReasons'),'corporateAction':x.get('corporateAction') or {}})
    rows[s]={'captured':s in store,'eligible':a.get('eligible'),'route':a.get('route'),'ineligibleReasons':a.get('ineligibleReasons'),'corporateAction':a.get('corporateAction') or {},'eventReference':a.get('corporateActionEventReference'),'qualityCandidates':quality,'failure':failures.get(s)}
result={'version':'VMEWS-V12-CA-FOCUS-DIAGNOSTIC-1.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'symbols':rows,'summary':{'requested':len(SYMBOLS),'captured':len(store),'eligible':sum((audits.get(s) or {}).get('eligible') is True for s in SYMBOLS),'ineligible':[s for s in SYMBOLS if (audits.get(s) or {}).get('eligible') is not True]}}
open('v12-ca-focus.json','w',encoding='utf-8').write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
print(json.dumps(result['summary'],ensure_ascii=False))
