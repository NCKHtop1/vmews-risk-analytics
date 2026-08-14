import json, os, math, importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import train_forecast_v10 as v
from forecast_v4_features import stock_features

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'))
MANIFEST=ROOT/'data/hose-fallbacks/manifest.json'

def load_core():
    p=ROOT/'api/stocks.py';spec=importlib.util.spec_from_file_location('vmews_v10_hose_core',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
CORE=load_core()

def one(sym,route):
    local=ROOT/f'data/hose-fallbacks/{sym}.json'
    raw=None
    if local.exists():
        try:raw=json.loads(local.read_text(encoding='utf-8')).get('history') or None
        except:raw=None
    if not raw:
        try:raw,_,_=CORE.yahoo_chart(sym,'10y',5)
        except:return sym,[]
    try:
        rows,fs=stock_features(raw)
        if len(rows)<520 or len(fs)<260:return sym,[]
        out=[]
        for f in fs:
            i=f['i'];z={'symbol':sym,**f}
            for h in v.HORIZONS:z['y'+str(h)]=math.log(rows[i+h]['modelClose']/rows[i]['modelClose']) if i+h<len(rows) else np.nan
            out.append(z)
        return sym,out
    except:return sym,[]

def hose_panel(root='.'):
    m=json.loads(MANIFEST.read_text(encoding='utf-8'));routes=m.get('routes') or {};items=[(s,r) for s,r in routes.items() if int((r or {}).get('rows') or 0)>=520];P=[];used=[]
    with ThreadPoolExecutor(max_workers=10) as ex:
        fut={ex.submit(one,s,r):s for s,r in items}
        for f in as_completed(fut):
            s,a=f.result()
            if a:P.extend(a);used.append(s)
    dates=sorted(set(x['date'] for x in P));keep=set(dates[::5]);P=[x for x in P if x['date'] in keep]
    by={}
    for x in P:by.setdefault(x['date'],[]).append(x)
    for a in by.values():
        mr=float(np.median([x['ret20'] for x in a]));rs=float(np.mean([x['technical']>=50 for x in a]))
        for x in a:x['marketRet20']=mr;x['riskShare']=rs
    print(json.dumps({'hoseReference':m.get('hoseReference'),'eligibleLongHistory':len(items),'loadedSymbols':len(set(used)),'sampledRows':len(P),'sampledDates':len(keep)},ensure_ascii=False))
    if len(set(used))<250 or len(P)<100000:raise RuntimeError('HOSE training panel coverage below production floor')
    return P,len(set(used))

v.FEATURES=list(v.BASE)
v.build_panel=hose_panel
v.train(str(ROOT))
p=ROOT/'data/forecast-model-v10.json';z=json.loads(p.read_text(encoding='utf-8'))
z['governance']['featureParity']='STRICT: numerical forecast uses stock-local BASE features only; cross-sectional scan, macro, risk, flow and news are independent context.'
z['governance']['crossSectionalFeaturesInNumericalModel']=False
z['governance']['trainingUniverse']='Current HOSE common-stock reference from the resolver manifest; symbols require at least 520 completed sessions.'
z['governance']['sampleCadence']='Every 5th completed trading date for development/calibration/audit; T+3/T+5 labels still use actual subsequent sessions.'
z['governance']['survivorshipBias']='Current-HOSE reference creates survivorship/listing bias; results are not claimed for historical delisted constituents.'
p.write_text(json.dumps(z,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'featureCount':len(z['featureNames']),'symbols':z['universe']['symbols'],'rows':z['universe']['rows'],'promotion':z['promotion']},ensure_ascii=False))
