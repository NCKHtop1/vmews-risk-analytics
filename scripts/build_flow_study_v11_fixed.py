import json,math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import build_flow_study_v11 as base

ROOT=Path('.');H=(1,2,3,4,5)
def finite(x):
    try:return math.isfinite(float(x))
    except:return False
def fstate(z):return 'STRONG_BUY' if z>=.75 else 'BUY' if z>=.2 else 'STRONG_SELL' if z<=-.75 else 'SELL' if z<=-.2 else 'NEUTRAL'
def stat(a):
    x=np.asarray([v for v in a if finite(v)],float)
    if not len(x):return None
    return {'n':int(len(x)),'meanAR':float(x.mean()),'medianAR':float(np.median(x)),'positiveRate':float(np.mean(x>0)),'q20':float(np.quantile(x,.2)),'q80':float(np.quantile(x,.8))}
def price(s):
    try:return base.price(s)
    except:return s,{},[]

def main():
    flow=json.loads((ROOT/'data/flow-v11.json').read_text(encoding='utf-8'))
    # Normalize coverage counters even for older validated source snapshots.
    src_current=flow.get('current',{})
    flow.setdefault('summary',{})['currentForeign']=sum(all(k in z for k in ('foreignZ60','foreignNet1','foreignNet5','foreignNet20')) for z in src_current.values())
    flow['summary']['currentProp']=sum(all(k in z for k in ('propZ60','propNet1','propNet5','propNet20')) for z in src_current.values())
    # Use only rows where the source actually reports gross foreign trading. Zero-gross
    # placeholder rows are not interpreted as genuine zero flow.
    valid={}
    for s,rows in flow.get('symbols',{}).items():
        a=[]
        for r in rows:
            gross=float(r.get('foreignBuyValue',0) or 0)+float(r.get('foreignSellValue',0) or 0)
            if gross>0 and 'foreignNetValue' in r:a.append(r)
        if len(a)>=25:valid[s]=a
    prices={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs={ex.submit(price,s):s for s in valid}
        for f in as_completed(fs):
            s,p,d=f.result();prices[s]=(p,d)
    obs=[]
    for s,rows in valid.items():
        p,dates=prices.get(s,({},[]));idx={d:i for i,d in enumerate(dates)}
        net=np.asarray([float(x.get('foreignNetValue',0) or 0) for x in rows],float)
        gross=np.asarray([float(x.get('foreignBuyValue',0) or 0)+float(x.get('foreignSellValue',0) or 0) for x in rows],float)
        # Daily origins after a 20-observation warmup. Outcomes overlap by design because
        # this is an event/state response layer, not the sealed numerical model.
        for j in range(20,len(rows)):
            d=rows[j]['date'];i=idx.get(d)
            if i is None:continue
            hist=net[max(0,j-59):j+1];sd=float(hist.std(ddof=1)) if len(hist)>2 else 0.;zz=float((net[j]-hist.mean())/(sd or 1));n5=float(net[max(0,j-4):j+1].sum());n20=float(net[max(0,j-19):j+1].sum());g20=float(gross[max(0,j-19):j+1].sum())
            z={'symbol':s,'date':d,'foreignZ':zz,'foreignState':fstate(zz),'foreignNet5':n5,'foreignNet20':n20,'foreignRatio20':n20/g20 if g20 else 0.}
            for h in H:
                if i+h<len(dates) and dates[i+h] in p and d in p:z['r'+str(h)]=math.log(p[dates[i+h]]/p[d])
            obs.append(z)
    # Cross-sectional abnormal returns by origin date remove broad market direction.
    med={}
    for h in H:
        by={}
        for x in obs:
            v=x.get('r'+str(h))
            if finite(v):by.setdefault(x['date'],[]).append(v)
        for d,a in by.items():
            if len(a)>=8:med[(d,h)]=float(np.median(a))
    for x in obs:
        for h in H:
            v=x.get('r'+str(h));k=(x['date'],h)
            if finite(v) and k in med:x['ar'+str(h)]=float(v)-med[k]
    groups={'foreign':{}}
    for st in ('STRONG_SELL','SELL','NEUTRAL','BUY','STRONG_BUY'):
        a=[x for x in obs if x['foreignState']==st];groups['foreign'][st]={'n':len(a),'horizons':{str(h):stat([x.get('ar'+str(h)) for x in a]) for h in H}}
    adequate=sum(z['n']>=250 for z in groups['foreign'].values());rawTotal=sum(len(a) for a in valid.values());nonzero=sum(abs(float(r.get('foreignNetValue',0) or 0))>1e-12 for a in valid.values() for r in a);quality={'foreign':{'usable':adequate>=3 and len(obs)>=8000,'adequateStates':adequate,'nonzeroShare':nonzero/max(1,rawTotal),'observations':rawTotal},'prop':{'usable':False,'adequateStates':0,'nonzeroShare':0.0,'observations':0}}
    cur={}
    for s,c in src_current.items():
        if not all(k in c for k in ('foreignZ60','foreignNet1','foreignNet5','foreignNet20')):continue
        st=fstate(float(c.get('foreignZ60') or 0));hist=groups['foreign'].get(st)
        if hist and hist.get('n',0)>=250:
            cur[s]={'foreign':{'state':st,'z60':c.get('foreignZ60'),'net1':c.get('foreignNet1'),'net5':c.get('foreignNet5'),'net20':c.get('foreignNet20'),'netRatio20':c.get('foreignNetRatio20'),'history':hist}}
            if 'foreignRoom' in c:cur[s]['foreign']['room']=c.get('foreignRoom')
    out={'version':'VMEWS-FLOW-STUDY-11.2.1','generatedAt':flow.get('generatedAt'),'sourceVersion':flow.get('version'),'sampledObservations':len(obs),'symbolsWithUsableForeignHistory':len(valid),'groups':groups,'current':cur,'typeQuality':quality,'governance':{'role':'separate historically tested evidence layer; it changes confidence only when the current state has at least 250 historical observations','minimumStateN':250,'displayRule':'Foreign flow is rendered only for symbols with genuine source observations and a historically populated state. Proprietary flow is suppressed when the source is degenerate.','overlappingOutcomeStudy':True}}
    (ROOT/'data/flow-v11.json').write_text(json.dumps(flow,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (ROOT/'data/flow-study-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'sourceCurrentForeign':flow['summary']['currentForeign'],'flowQuality':quality,'sampledObservations':len(obs),'usableSymbols':len(valid),'currentSymbols':len(cur),'states':{k:v['n'] for k,v in groups['foreign'].items()}},ensure_ascii=False))
if __name__=='__main__':main()
