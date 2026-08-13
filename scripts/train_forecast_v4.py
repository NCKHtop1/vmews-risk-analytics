import os, json, glob, math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from forecast_v4_features import FEATURE_NAMES, stock_features, external, aligned

VERSION='VMEWS-FORECAST-4.0.0'; H=[1,2,3,4,5]; SEED=1907

def load_panel(root):
    paths={}
    for p in sorted(glob.glob(str(Path(root)/'data/hose-fallbacks/*.json'))+glob.glob(str(Path(root)/'data/deep-alerts/*.json'))):paths.setdefault(Path(p).stem,p)
    ext=external(); panel=[]; used=0
    for sym,p in paths.items():
        try:d=json.load(open(p,encoding='utf-8')); rows,fs=stock_features(d.get('history') or [])
        except Exception:continue
        if len(rows)<520 or len(fs)<260:continue
        used+=1
        for f in fs:
            z={'symbol':d.get('symbol') or sym,**f}; dt=f['date']; z['marketTechnical']=aligned(ext.get('marketTechnical'),dt,50); z['vixLevel']=aligned(ext.get('vixLevel'),dt); z['vixRet20']=aligned(ext.get('vixRet20'),dt); z['usdVndRet20']=aligned(ext.get('usdVndRet20'),dt); z['dxyRet20']=aligned(ext.get('dxyRet20'),dt); z['us10yRet20']=aligned(ext.get('us10yRet20'),dt); z['brentRet20']=aligned(ext.get('brentRet20'),dt)
            for h in H:z['y'+str(h)]=math.log(rows[f['i']+h]['modelClose']/rows[f['i']]['modelClose']) if f['i']+h<len(rows) else np.nan
            panel.append(z)
    return panel,used

def rank(a):
    o=np.argsort(a,kind='mergesort');r=np.empty(len(a));r[o]=np.arange(len(a));return r

def rho(y,p):
    if len(y)<3:return 0.
    a,b=rank(np.asarray(y)),rank(np.asarray(p));return float(np.corrcoef(a,b)[0,1]) if np.std(a)>0 and np.std(b)>0 else 0.

def metric(y,p):
    y=np.asarray(y);p=np.asarray(p);e=y-p;m=len(y);mid=m//2
    def spread(yy,pp):
        if len(yy)<20:return 0.
        q1,q2=np.quantile(pp,[.2,.8]);a=yy[pp<=q1];b=yy[pp>=q2];return float(b.mean()-a.mean()) if len(a) and len(b) else 0.
    pos=float(np.mean(y>0));base=max(pos,1-pos);mae=float(np.mean(abs(e)));mae0=float(np.mean(abs(y)));mse=float(np.mean(e*e));mse0=float(np.mean(y*y))
    return {'n':m,'r2':1-mse/(mse0 or 1e-18),'mae':mae,'maeImprove':1-mae/(mae0 or 1e-18),'direction':float(np.mean((y>=0)==(p>=0))),'majority':base,'spearman':rho(y,p),'spread':spread(y,p),'half1Spread':spread(y[:mid],p[:mid]),'half2Spread':spread(y[mid:],p[mid:])}

def score(m):return .32*m['r2']+.20*m['maeImprove']+.23*(m['direction']-m['majority'])+.25*m['spearman']

def models():
    x=[]
    for a in (.1,1,10,100,1000):x.append(('R',{'alpha':a}))
    for l in (16,32,64):x.append(('H',{'leaf':l}))
    return x

def fit(kind,p,X,y):
    if kind=='R':return Ridge(alpha=p['alpha']).fit(X,y)
    return HistGradientBoostingRegressor(max_iter=120,learning_rate=.04,max_leaf_nodes=15,min_samples_leaf=p['leaf'],l2_regularization=1.,loss='squared_error',random_state=SEED).fit(X,y)

def export(m,kind):
    if kind=='R':return {'type':'ridge','coef':[float(x) for x in m.coef_],'intercept':float(m.intercept_)}
    # HistGradientBoosting is retained for competition only. Live export falls back to a ridge student fitted to its predictions.
    return None

def train(root='.'):
    P,ns=load_panel(root)
    if len(P)<15000:raise SystemExit('panel too small')
    dates=sorted(set(x['date'] for x in P)); d60=dates[int(.60*len(dates))]; d80=dates[int(.80*len(dates))]; D=np.array([x['date'] for x in P]);X0=np.array([[x.get(k,np.nan) for k in FEATURE_NAMES] for x in P],float);med=np.nanmedian(X0,0);ii=np.where(~np.isfinite(X0));X0[ii]=np.take(med,ii[1]);mu=X0.mean(0);sd=X0.std(0);sd[sd<1e-9]=1;X=(X0-mu)/sd
    out={'version':VERSION,'trainedAt':datetime.now(timezone.utc).isoformat(),'featureNames':FEATURE_NAMES,'impute':med.tolist(),'mean':mu.tolist(),'std':sd.tolist(),'universe':{'symbols':ns,'rows':len(P),'dates':len(dates),'start':dates[0],'end':dates[-1]},'horizons':{}}
    report={}
    for h in H:
        y=np.array([x['y'+str(h)] for x in P],float);ok=np.isfinite(y);i60=max(1,int(.60*len(dates))-h);i80=max(i60+1,int(.80*len(dates))-h);dev=ok&(D<dates[i60]);val=ok&(D>=d60)&(D<dates[i80]);test=ok&(D>=d80)
        if dev.sum()<5000 or val.sum()<1000 or test.sum()<1000:continue
        cand=[]
        for kind,p in models():
            m=fit(kind,p,X[dev],y[dev]); mt=metric(y[val],m.predict(X[val]));cand.append((score(mt),kind,p,mt))
        cand.sort(reverse=True,key=lambda z:z[0]);best=cand[0];kind,p=best[1],best[2];trainmask=ok&(D<dates[i80]);m=fit(kind,p,X[trainmask],y[trainmask]);pred=m.predict(X[test]);mt=metric(y[test],pred)
        # A forecast is promoted only when it has cross-sectional ordering value, non-negative economic spread in both sealed halves, and no material error deterioration.
        checks={'rank':mt['spearman']>.012,'spread':mt['spread']>.001,'stability':mt['half1Spread']>=0 and mt['half2Spread']>=0,'mae':mt['maeImprove']>-.01,'direction':mt['direction']>=mt['majority']-.003,'r2':mt['r2']>-.015};passed=sum(checks.values())>=4 and checks['rank'] and checks['stability']
        # Export a deterministic ridge live model. If a nonlinear challenger wins validation, distill it on all labelled panel rows so browser inference remains small and reproducible.
        allmask=ok
        if kind=='R':live=fit('R',p,X[allmask],y[allmask]);live_note='ridge champion'
        else:
            teacher=fit('H',p,X[allmask],y[allmask]);pseudo=teacher.predict(X[allmask]);alpha=10.;live=Ridge(alpha=alpha).fit(X[allmask],pseudo);live_note='ridge student of nonlinear validation champion'
        pv=m.predict(X[val]) if len(X[val]) else np.array([]);resid=y[val]-pv if len(pv) else y[test]-pred;q10,q90=np.quantile(resid,[.10,.90])
        out['horizons'][str(h)]={'status':'PASS' if passed else 'REVIEW','sealed':mt,'checks':checks,'q10':float(q10),'q90':float(q90),'live':export(live,'R'),'liveNote':live_note};report[str(h)]={'status':'PASS' if passed else 'REVIEW',**mt}
    core=sum(out['horizons'].get(str(h),{}).get('status')=='PASS' for h in (3,4,5));out['promotion']={'status':'PASS' if core>=2 else 'REVIEW','passedCore':core};Path(root,'data/forecast-model-v4.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');Path(root,'forecast-validation-v4.json').write_text(json.dumps({'version':VERSION,'promotion':out['promotion'],'universe':out['universe'],'horizons':report},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'promotion':out['promotion'],'universe':out['universe'],'horizons':{k:{'status':v['status'],'r2':v['r2'],'maeImprove':v['maeImprove'],'direction':v['direction'],'spearman':v['spearman'],'spread':v['spread']} for k,v in report.items()}},indent=2))
    if out['promotion']['status']!='PASS':raise SystemExit('MODEL_REVIEW_REQUIRED')
if __name__=='__main__':train(os.environ.get('GITHUB_WORKSPACE','.'))
