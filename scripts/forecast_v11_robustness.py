import json, math, os, importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import balanced_accuracy_score, matthews_corrcoef
import train_forecast_v10 as v
from forecast_v4_features import stock_features

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));MANIFEST=ROOT/'data/hose-fallbacks/manifest.json';OUT=ROOT/'data/forecast-v11-robustness.json'
BASE=list(v.BASE)
GROUPS={
 'momentumTrend':['ret1','ret2','ret3','ret5','ret10','ret20','trend5','trend10','trend20','trend50','trend200'],
 'drawdownRisk':['dd20','dd60','technical','technicalDelta5'],
 'volatilityLiquidity':['vol5','vol20','volPct','volumeZ','range1','range5'],
 'oscillators':['rsi14','macdNorm']
}

def core():
 p=ROOT/'api/stocks.py';s=importlib.util.spec_from_file_location('c',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
CORE=core()
def one(sym):
 p=ROOT/f'data/hose-fallbacks/{sym}.json';raw=None
 if p.exists():
  try:raw=json.loads(p.read_text(encoding='utf-8')).get('history') or None
  except:pass
 if not raw:
  try:raw,_,_=CORE.yahoo_chart(sym,'10y',5)
  except:return []
 try:
  rows,fs=stock_features(raw)
  if len(rows)<520 or len(fs)<260:return []
  out=[]
  for f in fs:
   i=f['i'];z={'symbol':sym,**f}
   for h in (3,5):z['y'+str(h)]=math.log(rows[i+h]['modelClose']/rows[i]['modelClose']) if i+h<len(rows) else np.nan
   out.append(z)
  return out
 except:return []
def panel():
 m=json.loads(MANIFEST.read_text(encoding='utf-8'));syms=[s for s,r in (m.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520];P=[]
 with ThreadPoolExecutor(max_workers=10) as ex:
  fs=[ex.submit(one,s) for s in syms]
  for f in as_completed(fs):P.extend(f.result())
 dates=sorted(set(x['date'] for x in P));keep=set(dates[::5]);P=[x for x in P if x['date'] in keep];by={}
 for x in P:by.setdefault(x['date'],[]).append(x)
 for a in by.values():
  mr=float(np.median([x['ret20'] for x in a]));rs=float(np.mean([x['technical']>=50 for x in a]))
  for x in a:x['marketRet20']=mr;x['riskShare']=rs
 return P,np.array(sorted(keep))
def market_map(P,D,y):
 out={}
 for d in sorted(set(D)):
  z=y[D==d];z=z[np.isfinite(z)]
  if len(z)>=8:out[d]=float(np.median(z))
 return out
def prep(X,tr):
 return v.prep_fit(X,tr)
def apply(X,p):return v.prep_apply(X,*p)
def rank(y,p,D):return v.rank_stats(y,p,D)
def expanding(P,dates,h,features,alpha,C):
 D=np.array([x['date'] for x in P]);X=np.asarray([[x.get(k,np.nan) for k in features] for x in P],float);y=np.asarray([x.get('y'+str(h),np.nan) for x in P],float);mm=market_map(P,D,y);a=np.asarray([y[i]-mm.get(D[i],np.nan) for i in range(len(P))]);blocks=[(.55,.66),(.66,.77),(.77,.88),(.88,1.0)];out=[]
 for lo,hi in blocks:
  n=len(dates);ia=max(1,int(lo*n));ib=min(n,int(hi*n));cut=max(1,ia-h);tr=np.isfinite(a)&(D<dates[cut]);te=np.isfinite(a)&(D>=dates[ia])&(D<(dates[ib] if ib<n else '9999-99-99'))
  if tr.sum()<5000 or te.sum()<500:continue
  pp=prep(X,tr);Z=apply(X,pp);r=Ridge(alpha=alpha).fit(Z[tr],a[tr]);c=LogisticRegression(C=C,max_iter=1500,class_weight='balanced').fit(Z[tr],y[tr]>0);ap=r.predict(Z[te]);dp=c.predict_proba(Z[te])[:,1];s=rank(a[te],ap,D[te]);out.append({'start':str(min(D[te])),'end':str(max(D[te])),'n':int(te.sum()),'ic':float(s['ic']),'spread':float(s['spread']),'balancedAccuracy':float(balanced_accuracy_score(y[te]>0,dp>=.5)),'mcc':float(matthews_corrcoef(y[te]>0,dp>=.5))})
 return out
def audit_prediction(P,dates,h,features,alpha,C):
 D=np.array([x['date'] for x in P]);X=np.asarray([[x.get(k,np.nan) for k in features] for x in P],float);y=np.asarray([x.get('y'+str(h),np.nan) for x in P],float);mm=market_map(P,D,y);a=np.asarray([y[i]-mm.get(D[i],np.nan) for i in range(len(P))]);n=len(dates);ia=int(.91*n);cut=max(1,ia-h);tr=np.isfinite(a)&(D<dates[cut]);te=np.isfinite(a)&(D>=dates[ia]);pp=prep(X,tr);Z=apply(X,pp);r=Ridge(alpha=alpha).fit(Z[tr],a[tr]);c=LogisticRegression(C=C,max_iter=1500,class_weight='balanced').fit(Z[tr],y[tr]>0);idx=np.where(te)[0];ap=r.predict(Z[te]);dp=c.predict_proba(Z[te])[:,1];return a[idx],y[idx],ap,dp,D[idx],np.array([P[i]['symbol'] for i in idx])
def permutation(y,p,D,reps=300):
 obs=rank(y,p,D);rng=np.random.default_rng(1117);ics=[];spr=[]
 for _ in range(reps):
  yy=y.copy()
  for d in np.unique(D):
   q=np.where(D==d)[0];yy[q]=rng.permutation(yy[q])
  s=rank(yy,p,D);ics.append(s['ic']);spr.append(s['spread'])
 return {'reps':reps,'observedIC':float(obs['ic']),'observedSpread':float(obs['spread']),'icP':float((1+sum(x>=obs['ic'] for x in ics))/(reps+1)),'spreadP':float((1+sum(x>=obs['spread'] for x in spr))/(reps+1))}
def daily_spreads(y,p,D):
 out=[]
 for d in sorted(set(D)):
  q=np.where(D==d)[0]
  if len(q)<20:continue
  o=q[np.argsort(p[q])];k=max(1,len(o)//5);out.append(float(np.mean(y[o[-k:]])-np.mean(y[o[:k]])))
 return np.asarray(out,float)
def cost_audit(y,p,D):
 a=daily_spreads(y,p,D);gross=float(np.mean(a)) if len(a) else 0.;return {'days':len(a),'grossSpread':gross,'netSpread15bps':gross-.0030,'netSpread30bps':gross-.0060,'netSpread50bps':gross-.0100,'note':'Conservative full-rebalance long-short cost deduction; not a claim of executable portfolio returns.'}
def ablations(P,dates,h,model):
 full=BASE;alpha=float(model['development']['selectedAlpha']);C=float(model['development']['selectedC']);ya,yr,ap,dp,D,S=audit_prediction(P,dates,h,full,alpha,C);base=rank(ya,ap,D);out={'FULL':{'ic':float(base['ic']),'spread':float(base['spread']),'direction':float(balanced_accuracy_score(yr>0,dp>=.5))}}
 for g,drop in GROUPS.items():
  fs=[x for x in full if x not in drop];a,y,p,d,DD,_=audit_prediction(P,dates,h,fs,alpha,C);s=rank(a,p,DD);out['minus_'+g]={'features':len(fs),'ic':float(s['ic']),'spread':float(s['spread']),'direction':float(balanced_accuracy_score(y>0,d>=.5)),'deltaIC':float(s['ic']-base['ic']),'deltaSpread':float(s['spread']-base['spread'])}
 return out

def main():
 model=json.loads((ROOT/'data/forecast-model-v10.json').read_text(encoding='utf-8'));P,dates=panel();out={'version':'VMEWS-FORECAST-ROBUSTNESS-11.0.0','modelVersion':model['version'],'rows':len(P),'symbols':len(set(x['symbol'] for x in P)),'dates':len(dates),'horizons':{}}
 for h in (3,5):
  z=model['horizons'][str(h)];alpha=float(z['development']['selectedAlpha']);C=float(z['development']['selectedC']);a,y,p,d,D,S=audit_prediction(P,dates,h,BASE,alpha,C);multi=expanding(P,dates,h,BASE,alpha,C);perm=permutation(a,p,D);cost=cost_audit(a,p,D);abl=ablations(P,dates,h,z);positive=sum(x['ic']>0 and x['spread']>0 for x in multi);out['horizons'][str(h)]={'multiWindow':multi,'positiveWindows':positive,'permutation':perm,'costStress':cost,'ablations':abl,'gates':{'multiWindow':positive>=3,'permutation':perm['icP']<.05 and perm['spreadP']<.05,'grossEconomicRanking':cost['grossSpread']>0,'exactMagnitudeStillWithheld':True}}
 out['status']='PASS' if all(z['gates']['multiWindow'] and z['gates']['permutation'] for z in out['horizons'].values()) else 'REVIEW';OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
