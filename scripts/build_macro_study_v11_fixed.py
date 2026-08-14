import json,math,os
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import quote
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));VERSION='VMEWS-MACRO-STUDY-11.4.0';H=(1,2,3,4,5);SPECS={'vix':'^VIX','usdVnd':'USDVND=X','dxy':'DX-Y.NYB','us10y':'^TNX','brent':'BZ=F'}

def fetch(sym,rg='10y'):
    for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
        try:
            u=f'https://{host}/v8/finance/chart/{quote(sym,safe="")}?range={rg}&interval=1d&includePrePost=false';p=json.loads(urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS-Macro/11.4'}),timeout=12).read().decode());z=(p.get('chart',{}).get('result') or [None])[0]
            if not z:continue
            ts=z.get('timestamp') or [];q=(z.get('indicators',{}).get('quote') or [{}])[0];out=[]
            for i,t in enumerate(ts):
                try:c=float((q.get('close') or [])[i]);d=datetime.fromtimestamp(t,timezone.utc).date().isoformat()
                except:continue
                if math.isfinite(c) and c>0:out.append((d,c))
            if len(out)>100:return dict(out),[x[0] for x in out]
        except:pass
    return {},[]

def panel_benchmark():
    p=ROOT/'data/market-benchmark-v11.json'
    if not p.exists():return {},[]
    try:z=json.loads(p.read_text(encoding='utf-8'));rows=z.get('series') or [];vals={str(x['date']):float(x['level']) for x in rows if x.get('date') and float(x.get('level',0))>0};days=sorted(vals);return vals,days
    except:return {},[]

def stock_returns(sym):
    vals,days=fetch(sym+'.VN','10y');out={}
    for a,b in zip(days[:-1],days[1:]):
        try:r=math.log(vals[b]/vals[a])
        except:continue
        if math.isfinite(r) and abs(r)<.35:out[b]=r
    return out

def dynamic_hose_benchmark():
    try:man=json.loads((ROOT/'data/hose-fallbacks/manifest.json').read_text(encoding='utf-8'));syms=[s for s,r in (man.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520][:140]
    except:return {},[]
    ret={}
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs={ex.submit(stock_returns,s):s for s in syms}
        for f in as_completed(fs):
            try:z=f.result()
            except:z={}
            for d,r in z.items():ret.setdefault(d,[]).append(r)
    days=sorted(d for d,a in ret.items() if len(a)>=25);level=1000.;vals={}
    for d in days:
        level*=math.exp(float(np.median(ret[d])));vals[d]=level
    return vals,days

def ret_before(vals,dates,d,k=20):
    # all macro information must be available strictly before Vietnam date T
    import bisect
    j=bisect.bisect_left(dates,d);ds=dates[:j]
    if len(ds)<k+1:return None
    a,b=ds[-1],ds[-k-1];return math.log(vals[a]/vals[b])

def zscore(a,x):
    v=np.asarray(a[-252:],float)
    if len(v)<30:return 0.
    return float((x-v.mean())/(v.std(ddof=1) or 1))

def stat(a):
    x=np.asarray(a,float)
    return {'n':len(x),'mean':float(x.mean()),'median':float(np.median(x)),'positiveRate':float(np.mean(x>0)),'q20':float(np.quantile(x,.2)),'q80':float(np.quantile(x,.8))} if len(x) else None

def main():
    m={k:fetch(s) for k,s in SPECS.items()};vni,vd=fetch('^VNINDEX');source='YAHOO_VNINDEX'
    if len(vd)<800:vni,vd=fetch('^VNINDEX.VN');source='YAHOO_VNINDEX_VN'
    if len(vd)<1500:
        pv,pd=panel_benchmark()
        if len(pd)>=1500:vni,vd=pv,pd;source='HOSE_EQUAL_WEIGHT_MEDIAN_RETURN'
    if len(vd)<1500:vni,vd=dynamic_hose_benchmark();source='HOSE_CROSS_SECTION_MEDIAN_RETURN'
    if len(vd)<1500:raise RuntimeError(f'HOSE macro benchmark unavailable: {len(vd)} rows')
    available={k:v for k,v in m.items() if len(v[1])>=800}
    if len(available)<4:raise RuntimeError(f'macro factor coverage too low: {list(available)}')
    weights={'vix':.32,'dxy':.18,'us10y':.18,'usdVnd':.18,'brent':.14};rows=[];hist=[]
    for i,d in enumerate(vd):
        if i<260:continue
        f={};used=[]
        for k,(vals,ds) in available.items():
            r=ret_before(vals,ds,d,20)
            if r is not None:f[k+'Ret20']=r;used.append(k)
        if len(used)<4:continue
        den=sum(weights[k] for k in used);score=sum(weights[k]*(abs(f[k+'Ret20']) if k=='brent' else f[k+'Ret20']) for k in used)/den;hist.append(score);zs=zscore(hist,score);state='STRESS' if zs>=.8 else 'SUPPORTIVE' if zs<=-.8 else 'NEUTRAL';z={'date':d,'score':score,'z':zs,'state':state,'factorCount':len(used),**f}
        for h in H:
            if i+h<len(vd):z['r'+str(h)]=math.log(vni[vd[i+h]]/vni[d])
        rows.append(z)
    groups={}
    for st in ('SUPPORTIVE','NEUTRAL','STRESS'):
        a=[x for x in rows if x['state']==st];groups[st]={'n':len(a),'horizons':{str(h):stat([x['r'+str(h)] for x in a if 'r'+str(h) in x]) for h in H}}
    cur=rows[-1] if rows else None;out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'pointInTimeRule':'For Vietnam date T, cross-market macro closes are restricted to dates strictly earlier than T. Market outcomes use VNINDEX when available, otherwise the persisted V11 HOSE panel benchmark, otherwise a contemporaneous HOSE cross-sectional median-return benchmark.','benchmarkSource':source,'features':list(available),'current':cur,'groups':groups,'observations':len(rows)}
    (ROOT/'data/macro-study-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps({'observations':len(rows),'benchmarkSource':source,'features':list(available),'current':cur,'groups':{k:v['n'] for k,v in groups.items()}},ensure_ascii=False))
if __name__=='__main__':main()
