import json, math, glob, os
from pathlib import Path
import numpy as np
ALPHAS=[0.1,1.0,10.0,100.0,1000.0]
HORIZONS=(3,4,5)
MIN_ROWS=700
MAX_SYMBOLS=120

def features(rows):
    c=np.array([float(r['close']) for r in rows],dtype=float); v=np.array([float(r.get('volume') or 0) for r in rows],dtype=float); h=np.array([float(r.get('high') or r['close']) for r in rows],dtype=float); l=np.array([float(r.get('low') or r['close']) for r in rows],dtype=float)
    lr=np.zeros(len(c)); lr[1:]=np.log(c[1:]/c[:-1]); out=[]
    for i in range(60,len(rows)-5):
        ret=lambda k: math.log(c[i]/c[i-k]); rsiw=lr[i-13:i+1]; gains=np.maximum(rsiw,0).mean(); losses=np.maximum(-rsiw,0).mean(); rsi=100 if losses==0 else 100-100/(1+gains/losses)
        vw=v[i-19:i+1]; vm=vw[:-1].mean() if len(vw)>1 else 0; vs=vw[:-1].std(ddof=1) if len(vw)>2 else 0; vz=(v[i]-vm)/vs if vs>1e-9 else 0
        vol5=lr[i-4:i+1].std(ddof=1)*math.sqrt(252); vol20=lr[i-19:i+1].std(ddof=1)*math.sqrt(252)
        sma5=c[i-4:i+1].mean(); sma10=c[i-9:i+1].mean(); sma20=c[i-19:i+1].mean(); sma50=c[i-49:i+1].mean(); dd20=c[i]/c[i-19:i+1].max()-1; dd60=c[i]/c[i-59:i+1].max()-1; tr=(h[i]-l[i])/c[i] if c[i] else 0
        x=[lr[i],lr[i-1],lr[i-2],lr[i-3],lr[i-4],ret(3),ret(5),ret(10),ret(20),vol5,vol20,c[i]/sma5-1,c[i]/sma10-1,c[i]/sma20-1,c[i]/sma50-1,dd20,dd60,(rsi-50)/50,vz,tr]
        out.append((i,np.array(x,dtype=float)))
    return out

def ridge_fit(X,y,alpha):
    mu=X.mean(0); sd=X.std(0); sd[sd<1e-9]=1; Z=(X-mu)/sd; Z=np.c_[np.ones(len(Z)),Z]; pen=np.eye(Z.shape[1]); pen[0,0]=0
    try:b=np.linalg.solve(Z.T@Z+alpha*pen,Z.T@y)
    except np.linalg.LinAlgError:b=np.linalg.pinv(Z.T@Z+alpha*pen)@(Z.T@y)
    return mu,sd,b

def ridge_pred(m,X):
    mu,sd,b=m; Z=(X-mu)/sd; return np.c_[np.ones(len(Z)),Z]@b

def nw_t(d,lag):
    d=np.asarray(d,float); n=len(d)
    if n<20:return 0.0
    m=d.mean(); e=d-m; var=(e@e)/n
    for k in range(1,min(lag,n-1)+1):
        var+=2*(1-k/(lag+1))*((e[k:]@e[:-k])/n)
    se=math.sqrt(max(var,1e-18)/n); return m/se if se>0 else 0.0

def metrics(y,p):
    y=np.asarray(y); p=np.asarray(p); mid=len(y)//2
    r2=1-np.sum((y-p)**2)/max(np.sum(y*y),1e-18); da=np.mean(np.sign(y)==np.sign(p)); pos=np.mean(y>0); maj=max(pos,1-pos); dm=nw_t(y*y-(y-p)**2,4)
    half=lambda a,b:1-np.sum((a-b)**2)/max(np.sum(a*a),1e-18) if len(a) else -999
    return {'mae':float(np.mean(np.abs(y-p))),'rmse':float(math.sqrt(np.mean((y-p)**2))),'r2':float(r2),'da':float(da),'majority':float(maj),'dm':float(dm),'half1':float(half(y[:mid],p[:mid])),'half2':float(half(y[mid:],p[mid:]))}

def run_symbol(path):
    data=json.load(open(path,encoding='utf-8')); rows=data.get('history') or []
    if len(rows)<MIN_ROWS:return None
    F=features(rows)
    if len(F)<500:return None
    idx=np.array([i for i,_ in F]); X=np.vstack([x for _,x in F]); res={}
    for horizon in HORIZONS:
        y=np.array([math.log(rows[i+horizon]['close']/rows[i]['close']) for i in idx]); n=len(y); a=int(n*.60); b=int(n*.80)
        dev=np.arange(0,max(0,a-horizon)); val=np.arange(a,min(b-horizon,n)); test=np.arange(b,n)
        if len(dev)<200 or len(val)<80 or len(test)<80:continue
        best=None
        for alpha in ALPHAS:
            m=ridge_fit(X[dev],y[dev],alpha); mm=metrics(y[val],ridge_pred(m,X[val])); score=mm['r2']+0.25*(mm['da']-mm['majority'])-0.02*math.log10(alpha+1)
            if best is None or score>best[0]:best=(score,alpha)
        alpha=best[1]; train=np.arange(0,max(0,b-horizon)); m=ridge_fit(X[train],y[train],alpha); mt=metrics(y[test],ridge_pred(m,X[test]))
        mt.update({'alpha':alpha,'n':int(len(test)),'pass':bool(mt['r2']>0 and mt['da']>=max(.515,mt['majority']-.02) and mt['dm']>1.0 and min(mt['half1'],mt['half2'])>-.05)})
        res[str(horizon)]=mt
    return ((data.get('symbol') or Path(path).stem),res) if res else None

def main(root):
    files=sorted(glob.glob(str(Path(root)/'data/deep-alerts/*.json')))
    if len(files)>MAX_SYMBOLS:
        take=np.linspace(0,len(files)-1,MAX_SYMBOLS,dtype=int); files=[files[i] for i in take]
    results={}; summary={str(h):{'symbols':0,'passes':0,'r2':[],'da':[]} for h in HORIZONS}
    for p in files:
        try:r=run_symbol(p)
        except Exception:continue
        if not r:continue
        sym,rr=r; results[sym]=rr
        for h,m in rr.items():
            s=summary[h]; s['symbols']+=1; s['passes']+=int(m['pass']); s['r2'].append(m['r2']); s['da'].append(m['da'])
    final={}
    for h,s in summary.items():
        final[h]={'symbols':s['symbols'],'passRate':s['passes']/s['symbols'] if s['symbols'] else 0,'medianR2':float(np.median(s['r2'])) if s['r2'] else None,'positiveR2Rate':float(np.mean(np.array(s['r2'])>0)) if s['r2'] else None,'medianDirectionalAccuracy':float(np.median(s['da'])) if s['da'] else None}
    out={'version':'VMEWS-FORECAST-VALIDATION-1.0','summary':final,'results':results}; Path(root,'forecast-validation-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(final,indent=2))
    if sum(x['symbols'] for x in final.values())<30:raise SystemExit('insufficient validation coverage')
if __name__=='__main__':main(os.environ.get('GITHUB_WORKSPACE','.'))
