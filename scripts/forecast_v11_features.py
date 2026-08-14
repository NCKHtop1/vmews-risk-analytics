import json, math
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen
import numpy as np

MIN_ROWS=520
FEATURES=['ret1','ret2','ret3','ret5','ret10','ret20','dd20','dd60','trend5','trend10','trend20','trend50','trend200','vol5','vol20','volPct','rsi14','macdNorm','volumeZ','range1','range5','technical','technicalDelta5']

def _finite(x):
    try:return math.isfinite(float(x))
    except:return False

def yahoo_adjusted(symbol, range_value='10y', timeout=18):
    ys=symbol if symbol.startswith('^') or '=' in symbol or symbol.endswith('.VN') else symbol+'.VN'
    last=None
    for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
        try:
            u=f'https://{host}/v8/finance/chart/{quote(ys,safe="")}?range={range_value}&interval=1d&includePrePost=false&events=div%2Csplits'
            with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS-Forecast/11','Accept':'application/json'}),timeout=timeout) as r:p=json.loads(r.read().decode())
            z=(p.get('chart',{}).get('result') or [None])[0]
            if not z:raise RuntimeError(str(p.get('chart',{}).get('error')))
            ts=z.get('timestamp') or []; ind=z.get('indicators') or {};q=(ind.get('quote') or [{}])[0];adj=(ind.get('adjclose') or [{}])[0].get('adjclose') or []
            rows=[]
            for i,t in enumerate(ts):
                try:
                    c=float((q.get('close') or [])[i]);a=float(adj[i]) if i<len(adj) and _finite(adj[i]) and float(adj[i])>0 else c
                    if not(_finite(c) and c>0 and _finite(a) and a>0):continue
                    f=a/c
                    def val(k,d):
                        try:
                            x=float((q.get(k) or [])[i]);return x if _finite(x) else d
                        except:return d
                    o,h,l=val('open',c),val('high',c),val('low',c);v=max(0.,val('volume',0.))
                    rows.append({'date':datetime.fromtimestamp(int(t),timezone.utc).date().isoformat(),'open':o*f,'high':h*f,'low':l*f,'close':c,'modelClose':a,'adjClose':a,'volume':v,'adjustmentFactor':f})
                except:pass
            d={x['date']:x for x in rows};rows=[d[k] for k in sorted(d)]
            if len(rows)<250:raise RuntimeError(f'{ys}: short history {len(rows)}')
            return rows,{'provider':host,'adjusted':len(adj)>0,'symbol':ys}
        except Exception as e:last=e
    raise RuntimeError(f'{ys}: {last}')

def sanitize(rows):
    out=[]
    for r in rows or []:
        try:
            raw=float(r.get('close'));mc=float(r.get('modelClose',r.get('adjClose',raw)))
            if not(_finite(raw) and raw>0 and _finite(mc) and mc>0):continue
            fac=mc/raw
            o=float(r.get('open',raw))*fac;h=float(r.get('high',raw))*fac;l=float(r.get('low',raw))*fac
            if not all(_finite(x) and x>0 for x in (o,h,l)):o=h=l=mc
            hi=max(h,o,l,mc);lo=min(h,o,l,mc)
            out.append({'date':str(r.get('date'))[:10],'open':o,'high':hi,'low':lo,'close':raw,'modelClose':mc,'volume':max(0.,float(r.get('volume') or 0))})
        except:pass
    d={x['date']:x for x in out};return [d[k] for k in sorted(d)]

def ema(a,n):
    k=2/(n+1);e=None;out=[]
    for v in a:e=float(v) if e is None else k*float(v)+(1-k)*e;out.append(e)
    return np.asarray(out,float)

def rsi(c,i):
    d=np.diff(c[i-14:i+1]);g=float(np.maximum(d,0).mean());l=float(np.maximum(-d,0).mean())
    return 100. if l<1e-12 else 100-100/(1+g/l)

def rank(v,h):
    a=np.asarray([x for x in h if _finite(x)],float);return float(np.mean(a<=v)) if len(a) else .5

def stock_features(raw):
    rows=sanitize(raw)
    if len(rows)<MIN_ROWS:return rows,[]
    c=np.asarray([r['modelClose'] for r in rows],float);hi=np.asarray([r['high'] for r in rows],float);lo=np.asarray([r['low'] for r in rows],float);vol=np.asarray([r['volume'] for r in rows],float)
    lr=np.zeros(len(c));lr[1:]=np.log(c[1:]/c[:-1]);e12,e26=ema(c,12),ema(c,26);mac=e12-e26;sig=ema(mac,9);v20=np.zeros(len(c))
    for i in range(1,len(c)):
        x=lr[max(1,i-19):i+1];v20[i]=(float(np.std(x,ddof=1)) if len(x)>1 else 0.)*math.sqrt(252)
    fs=[];techByI={}
    for i in range(200,len(rows)):
        def ret(k):return math.log(c[i]/c[i-k])
        def sma(k):return max(1e-12,float(np.mean(c[i-k+1:i+1])))
        dd20=c[i]/max(c[i-19:i+1])-1;dd60=c[i]/max(c[i-59:i+1])-1;tr={k:c[i]/sma(k)-1 for k in (5,10,20,50,200)}
        vp=rank(v20[i],v20[max(200,i-252):i]);rv=vol[max(1,i-20):i];rv=rv[rv>0];vz=(vol[i]-float(rv.mean()))/(float(rv.std(ddof=1)) if len(rv)>1 and rv.std(ddof=1)>1e-12 else 1.) if vol[i]>0 and len(rv) else 0.
        rs=rsi(c,i);mn=(mac[i]-sig[i])/c[i];mom=ret(20)
        p=[min(1,max(0,-dd60/.22)),min(1,max(0,-mom/.14)),min(1,max(0,-tr[50]/.12)),min(1,max(0,-tr[200]/.18)),min(1,max(0,(vp-.45)/.55)),min(1,max(0,(45-rs)/20)),min(1,max(0,-mn/.025)),min(1,max(0,vz/3))*min(1,max(0,-lr[i]/.05))]
        tech=100*(.18*p[0]+.16*p[1]+.14*p[2]+.10*p[3]+.16*p[4]+.10*p[5]+.08*p[6]+.08*p[7]);ranges=[(hi[j]-lo[j])/c[j] for j in range(i-4,i+1)]
        f={'i':i,'date':rows[i]['date'],'ret1':float(lr[i]),'ret2':ret(2),'ret3':ret(3),'ret5':ret(5),'ret10':ret(10),'ret20':ret(20),'dd20':float(dd20),'dd60':float(dd60),'trend5':tr[5],'trend10':tr[10],'trend20':tr[20],'trend50':tr[50],'trend200':tr[200],'vol5':float(np.std(lr[i-4:i+1],ddof=1))*math.sqrt(252),'vol20':float(v20[i]),'volPct':vp,'rsi14':rs/100.,'macdNorm':float(mn),'volumeZ':float(vz),'range1':float((hi[i]-lo[i])/c[i]),'range5':float(np.mean(ranges)),'technical':float(tech)}
        if not all(_finite(f[k]) for k in FEATURES if k!='technicalDelta5'):raise RuntimeError(f'non-finite feature {rows[i]["date"]}')
        techByI[i]=tech;fs.append(f)
    for f in fs:f['technicalDelta5']=float((f['technical']-techByI.get(f['i']-5,f['technical']))/100.)
    return rows,fs
