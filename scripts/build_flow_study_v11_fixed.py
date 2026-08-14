import json,math
from pathlib import Path
import build_flow_study_v11 as m

ROOT=Path('.')
m.main()
flow=json.loads((ROOT/'data/flow-v11.json').read_text(encoding='utf-8'))
study=json.loads((ROOT/'data/flow-study-v11.json').read_text(encoding='utf-8'))
quality={}
for typ in ('foreign','prop'):
    groups=study['groups'][typ]
    adequate=sum((z or {}).get('n',0)>=250 for z in groups.values())
    rows=[]
    nonzero=0;total=0
    fld=typ+'NetValue'
    for a in flow.get('symbols',{}).values():
        for r in a:
            if fld in r:
                total+=1
                try:
                    if abs(float(r.get(fld) or 0))>1e-12:nonzero+=1
                except:pass
    share=nonzero/max(1,total)
    usable=adequate>=3 and share>=.01
    quality[typ]={'usable':usable,'adequateStates':adequate,'nonzeroShare':share,'observations':total}
    if not usable:
        for s,z in list(study.get('current',{}).items()):z.pop(typ,None)
study['typeQuality']=quality
study['governance']['displayRule']='A flow type is rendered only when historical observations are non-degenerate and at least three state buckets have >=250 observations.'
(ROOT/'data/flow-study-v11.json').write_text(json.dumps(study,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print(json.dumps({'flowQuality':quality,'currentSymbols':len(study.get('current',{}))},ensure_ascii=False))
