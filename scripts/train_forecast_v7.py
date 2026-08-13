import json, math, os
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge, ElasticNet, LogisticRegression
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import balanced_accuracy_score, matthews_corrcoef
from train_forecast_v6 import build_panel, FEATURES, prep_fit, prep_apply, rank_stats
VERSION='VMEWS-FORECAST-7.0.0';HORIZONS=(3,5);FOLDS=((.52,.62),(.62,.72),(.72,.82),(.82,.91),(.91,1.0))
def alpha_model(n):
 if n=='ridge':return Ridge(alpha=100)
 if n=='elastic':return ElasticNet(alpha=1e-4,l1_ratio=.15,max_iter=7000)
 if n=='hgb':return HistGradientBoostingRegressor(max_iter=180,max_leaf_nodes=15,l2_regularization=1,learning_rate=.04,random_state=23)
def dir_model(n):
 if n=='logit':return LogisticRegression(C=.2,max_iter=1200,class_weight='balanced')
 if n=='hgbc':return HistGradientBoostingClassifier(max_iter=180,max_leaf_nodes=15,l2_regularization=1,learning_rate=.04,random_state=23)
def lexp(m,n):return {'type':n,'coef':[float(x) for x in m.coef_],'intercept':float(m.intercept_)}
def dexp(m):return {'type':'logit','coef':[float(x) for x in m.coef_[0]],'intercept':float(m.intercept_[0])}
def mkt_target(y,D):
 med={}
 for d in sorted(set(D)):
  z=y[D==d];z=z[np.isfinite(z)]
  if len(z):med[d]=float(np.median(z))
 return np.array([med.get(d,np.nan) for d in D])
def masks(dates,D,ok,h,f):
 n=len(dates);i=max(1,int(f[0]*n));j=min(n,int(f[1]*n));e=max(1,i-h);tr=ok&(D<dates[e]);te=ok&(D>=dates[i])&(D<(dates[j] if j<n else '9999-99-99'));return tr,te,{'trainEnd':str(dates[e-1]),'testStart':str(dates[i]),'testEnd':str(dates[j-1])}
def astat(y,p,D):
 z=rank_stats(y,p,D);return {'ic':z['ic'],'spread':z['spread']}
def dstat(y,p):return {'balancedAccuracy':float(balanced_accuracy_score(y>0,p>=.5)),'mcc':float(matthews_corrcoef(y>0,p>=.5)),'meanPUp':float(np.mean(p))}
def signal(pr,ap,sc):return 1.35*(pr-.5)+.55*np.tanh(ap/max(sc,1e-6))
def bins(y,p,n=8):
 qs=np.unique(np.quantile(p,np.linspace(0,1,n+1)));o=[]
 for i in range(len(qs)-1):
  m=(p>=qs[i])&(p<=qs[i+1] if i==len(qs)-2 else p<qs[i+1])
  if m.sum()>=30:o.append({'n':int(m.sum()),'predMean':float(np.mean(p[m])),'actualMean':float(np.mean(y[m])),'actualMedian':float(np.median(y[m])),'positiveRate':float(np.mean(y[m]>0)),'gt1Pct':float(np.mean(y[m]>.01)),'ltMinus1Pct':float(np.mean(y[m]<-.01))})
 return o
def magstat(y,p,D,q10,q90):
 e=y-p;cs=rank_stats(y,p,D);bb=bins(y,p);aa=[x['actualMean'] for x in bb];mono=float(spearmanr(np.arange(len(aa)),aa).statistic) if len(aa)>=4 else 0.;X=np.c_[np.ones(len(p)),p];c=np.linalg.lstsq(X,y,rcond=None)[0];mse=float(np.mean(e*e));m0=float(np.mean(y*y));mae=float(np.mean(abs(e)));a0=float(np.mean(abs(y)));return {'n':len(y),'r2':1-mse/(m0 or 1e-18),'mae':mae,'maeImprove':1-mae/(a0 or 1e-18),'balancedDirection':float(balanced_accuracy_score(y>0,p>0)),'mcc':float(matthews_corrcoef(y>0,p>0)),'csIC':cs['ic'],'csSpread':cs['spread'],'topReturn':cs['top'],'marketMean':cs['mean'],'topLift':cs['top']-cs['mean'],'topNet30bps':cs['top']-.003,'intervalCoverage':float(np.mean((y>=p+q10)&(y<=p+q90))),'intervalWidth':q90-q10,'calibrationIntercept':float(c[0]),'calibrationSlope':float(c[1]),'magnitudeMonotonicity':mono,'calibrationBins':bb}
def boot(y,p,D,reps=250):
 days=np.array(sorted(set(D)));rng=np.random.default_rng(77);A=[]
 for _ in range(reps):
  s=rng.choice(days,len(days),replace=True);idx=np.concatenate([np.where(D==x)[0] for x in s]);cs=rank_stats(y[idx],p[idx],D[idx]);A.append([cs['ic'],cs['spread'],cs['top']-cs['mean'],balanced_accuracy_score(y[idx]>0,p[idx]>0)])
 A=np.asarray(A);nn=('csIC','csSpread','topLift','balancedDirection');return {n:{'lo':float(np.quantile(A[:,i],.025)),'hi':float(np.quantile(A[:,i],.975))} for i,n in enumerate(nn)}
def events(y,pr,er):
 out={}
 for k,m in [('positive_watch',(pr>=.55)&(er>=.004)),('positive_strong',(pr>=.58)&(er>=.008)),('negative_watch',(pr<=.45)&(er<=-.004)),('negative_strong',(pr<=.42)&(er<=-.008))]:
  n=int(m.sum());z={'n':n}
  if n>=20:
   z.update({'directionPrecision':float(np.mean(y[m]>0)) if 'positive' in k else float(np.mean(y[m]<0)),'onePctPrecision':float(np.mean(y[m]>.01)) if 'positive' in k else float(np.mean(y[m]<-.01)),'meanReturn':float(np.mean(y[m])),'medianReturn':float(np.median(y[m]))})
  out[k]=z
 return out
def fpred(X0,y,ya,D,dates,h,fold,an,dn):
 tr,te,meta=masks(dates,D,np.isfinite(y)&np.isfinite(ya),h,fold);im,mu,sd=prep_fit(X0,tr);X=prep_apply(X0,im,mu,sd);am=alpha_model(an).fit(X[tr],ya[tr]);dm=dir_model(dn).fit(X[tr],y[tr]>0);idx=np.where(te)[0];return idx,am.predict(X[te]),dm.predict_proba(X[te])[:,1],float(np.std(ya[tr])) or .01,meta
def choose(X0,y,ya,D,dates,h):
 A=[]
 for n in ('ridge','elastic','hgb'):
  z=[]
  for f in FOLDS[:3]:
   i,p,_,_,_=fpred(X0,y,ya,D,dates,h,f,n,'logit');z.append(astat(ya[i],p,D[i]))
  A.append({'name':n,'ic':float(np.mean([x['ic'] for x in z])),'spread':float(np.mean([x['spread'] for x in z]))})
 A.sort(key=lambda x:x['ic']+.2*x['spread'],reverse=True);ra=A[0]['name'];da=max([x for x in A if x['name'] in ('ridge','elastic')],key=lambda x:x['ic']+.2*x['spread'])['name'];Q=[]
 for n in ('logit','hgbc'):
  z=[]
  for f in FOLDS[:3]:
   i,_,p,_,_=fpred(X0,y,ya,D,dates,h,f,'ridge',n);z.append(dstat(y[i],p))
  Q.append({'name':n,'balancedAccuracy':float(np.mean([x['balancedAccuracy'] for x in z])),'mcc':float(np.mean([x['mcc'] for x in z]))})
 Q.sort(key=lambda x:x['balancedAccuracy']+.2*x['mcc'],reverse=True);return ra,da,Q[0]['name'],A,Q
def train(root='.'):
 P,ns=build_panel(root);D=np.array([x['date'] for x in P]);dates=np.array(sorted(set(D)));X0=np.array([[x.get(k,np.nan) for k in FEATURES] for x in P],float);rep={'version':VERSION,'createdAt':datetime.now(timezone.utc).isoformat(),'universe':{'symbols':ns,'rows':len(P),'dates':len(dates),'start':str(dates[0]),'end':str(dates[-1])},'protocol':'3 development walk-forward folds choose model; fold 4 calibrates; fold 5 historical audit; future live archive is untouched validation','horizons':{}};dep={'version':VERSION,'modelDate':str(dates[-1]),'featureNames':FEATURES,'universe':rep['universe'],'horizons':{},'governance':{'exactPriceTarget':False,'output':'calibrated conditional return + direction probability + empirical interval','preprocessing':'training data only inside each fold','macroTiming':'strictly prior global close','historicalForeignFlow':False,'sentimentNumericalFeature':False}}
 for h in HORIZONS:
  y=np.array([x.get('y'+str(h),np.nan) for x in P]);ym=mkt_target(y,D);ya=y-ym;ra,da,rd,adev,ddev=choose(X0,y,ya,D,dates,h);ci,cap,cpr,csc,cm=fpred(X0,y,ya,D,dates,h,FOLDS[3],da,'logit');cr=signal(cpr,cap,csc);iso=IsotonicRegression(out_of_bounds='clip').fit(cr,y[ci]);cp=iso.predict(cr);res=y[ci]-cp;q10,q90=[float(x) for x in np.quantile(res,[.1,.9])];ai,aap,apr,asc,am=fpred(X0,y,ya,D,dates,h,FOLDS[4],da,'logit');ar=signal(apr,aap,asc);er=iso.predict(ar);mag=magstat(y[ai],er,D[ai],q10,q90);ast=astat(ya[ai],aap,D[ai]);dst=dstat(y[ai],apr);bs=boot(y[ai],er,D[ai]);ev=events(y[ai],apr,er);ck={'direction':dst['balancedAccuracy']>.515,'directionMCC':dst['mcc']>.02,'alphaRank':ast['ic']>.012,'magnitudeMonotonic':mag['magnitudeMonotonicity']>.45,'topLift':mag['topLift']>0,'intervalCoverage':.70<=mag['intervalCoverage']<=.90,'bootstrapRank':bs['csIC']['lo']>-.005,'positiveStrongPrecision':ev.get('positive_strong',{}).get('directionPrecision',1)>.52 if ev.get('positive_strong',{}).get('n',0)>=20 else True};passed=sum(ck.values())>=7 and ck['direction'] and ck['alphaRank'] and ck['magnitudeMonotonic'];valid=np.isfinite(y)&np.isfinite(ya);im,mu,sd=prep_fit(X0,valid);X=prep_apply(X0,im,mu,sd);af=alpha_model(da).fit(X[valid],ya[valid]);df=dir_model('logit').fit(X[valid],y[valid]>0);sc=float(np.std(ya[valid])) or .01;O=[];Y=[]
  for f in FOLDS[2:]:
   i,xap,xpr,xsc,_=fpred(X0,y,ya,D,dates,h,f,da,'logit');O.extend(signal(xpr,xap,xsc));Y.extend(y[i])
  O=np.asarray(O);Y=np.asarray(Y);fi=IsotonicRegression(out_of_bounds='clip').fit(O,Y);rr=Y-fi.predict(O);oq10,oq90=[float(x) for x in np.quantile(rr,[.1,.9])];rep['horizons'][str(h)]={'status':'PASS' if passed else 'REVIEW','development':{'alphaCandidates':adev,'directionCandidates':ddev,'researchAlphaChampion':ra,'deployAlpha':da,'researchDirectionChampion':rd},'calibrationFold':cm,'auditFold':am,'historicalAudit':{'magnitude':mag,'alpha':ast,'direction':dst,'bootstrap95':bs,'events':ev},'checks':ck};dep['horizons'][str(h)]={'status':'PASS' if passed else 'REVIEW','alphaModel':lexp(af,da),'directionModel':dexp(df),'impute':[float(x) for x in im],'mean':[float(x) for x in mu],'std':[float(x) for x in sd],'alphaScale':sc,'calibration':{'x':[float(x) for x in fi.X_thresholds_],'y':[float(x) for x in fi.y_thresholds_]},'q10':oq10,'q90':oq90,'audit':rep['horizons'][str(h)]['historicalAudit']}
 p=sum(dep['horizons'][str(h)]['status']=='PASS' for h in HORIZONS);dep['promotion']={'status':'PASS' if p==2 else 'REVIEW','passed':p,'required':2};rep['promotion']=dep['promotion'];Path(root,'data/forecast-model-v7.json').write_text(json.dumps(dep,ensure_ascii=False,separators=(',',':')),encoding='utf-8');Path(root,'forecast-validation-v7.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'promotion':dep['promotion'],'universe':rep['universe'],'horizons':{h:{'status':rep['horizons'][h]['status'],'development':rep['horizons'][h]['development'],'audit':rep['horizons'][h]['historicalAudit'],'checks':rep['horizons'][h]['checks']} for h in rep['horizons']}},ensure_ascii=False,indent=2))
if __name__=='__main__':train(os.environ.get('GITHUB_WORKSPACE','.'))