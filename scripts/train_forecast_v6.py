import os, json, glob, math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from sklearn.linear_model import Ridge, ElasticNet, LogisticRegression
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import balanced_accuracy_score, matthews_corrcoef
from scipy.stats import spearmanr
from forecast_v4_features import stock_features, external, aligned
VERSION='VMEWS-FORECAST-6.0.0-RESEARCH'; HORIZONS=(3,5)
BASE=['ret1','ret2','ret3','ret5','ret10','ret20','dd20','dd60','trend5','trend10','trend20','trend50','trend200','vol5','vol20','volPct','rsi14','macdNorm','volumeZ','range1','range5','technical','technicalDelta5']
CROSS=['relRet1','relRet5','relRet20','rankRet5','rankRet20','rankTechnical','breadth1','breadth5','breadth20','trend20Share','riskShare','csad1','csad5','dispersion20','marketRet1','marketRet5','marketRet20','marketTechnical']
MACRO=['vixLevel','vixRet20','usdVndRet20','dxyRet20','us10yRet20','brentRet20']; FEATURES=BASE+CROSS+MACRO

def finite(x):
 try:return math.isfinite(float(x))
 except:return False

def rank_pct(a):
 a=np.asarray(a,float);o=np.argsort(a,kind='mergesort');r=np.empty(len(a));r[o]=np.arange(len(a));return r/max(1,len(a)-1)
def prior(series,d,default=np.nan):
 keys,vals=series if series else ([],[])
 if not keys:return default
 import bisect;i=bisect.bisect_left(keys,d)-1
 return vals[i] if i>=0 else default

def build_panel(root='.'):
 paths={}
 for p in sorted(glob.glob(str(Path(root)/'data/hose-fallbacks/*.json'))+glob.glob(str(Path(root)/'data/deep-alerts/*.json'))):paths.setdefault(Path(p).stem,p)
 ext=external();P=[];used=0
 for sym,p in paths.items():
  try:d=json.load(open(p,encoding='utf-8'));rows,fs=stock_features(d.get('history') or [])
  except Exception:continue
  if len(rows)<520 or len(fs)<260:continue
  used+=1
  for f in fs:
   i=f['i'];z={'symbol':d.get('symbol') or sym,**f};dt=f['date']
   for h in HORIZONS:z['y'+str(h)]=math.log(rows[i+h]['modelClose']/rows[i]['modelClose']) if i+h<len(rows) else np.nan
   z['marketTechnical']=aligned(ext.get('marketTechnical'),dt,50)
   z['vixLevel']=prior(ext.get('vixLevel'),dt);z['vixRet20']=prior(ext.get('vixRet20'),dt);z['usdVndRet20']=prior(ext.get('usdVndRet20'),dt);z['dxyRet20']=prior(ext.get('dxyRet20'),dt);z['us10yRet20']=prior(ext.get('us10yRet20'),dt);z['brentRet20']=prior(ext.get('brentRet20'),dt);P.append(z)
 by={}
 for x in P:by.setdefault(x['date'],[]).append(x)
 for dt,a in by.items():
  if len(a)<8:continue
  r1=np.array([x['ret1'] for x in a]);r5=np.array([x['ret5'] for x in a]);r20=np.array([x['ret20'] for x in a]);tech=np.array([x['technical'] for x in a]);m1=float(np.median(r1));m5=float(np.median(r5));m20=float(np.median(r20));rr5=rank_pct(r5);rr20=rank_pct(r20);rt=rank_pct(tech);b1=float(np.mean(r1>0));b5=float(np.mean(r5>0));b20=float(np.mean(r20>0));t20=float(np.mean([x['trend20']>0 for x in a]));rs=float(np.mean(tech>=50));c1=float(np.mean(np.abs(r1-m1)));c5=float(np.mean(np.abs(r5-m5)));disp=float(np.std(r20,ddof=1)) if len(a)>1 else 0.
  for j,x in enumerate(a):x.update({'relRet1':x['ret1']-m1,'relRet5':x['ret5']-m5,'relRet20':x['ret20']-m20,'rankRet5':float(rr5[j]),'rankRet20':float(rr20[j]),'rankTechnical':float(rt[j]),'breadth1':b1,'breadth5':b5,'breadth20':b20,'trend20Share':t20,'riskShare':rs,'csad1':c1,'csad5':c5,'dispersion20':disp,'marketRet1':m1,'marketRet5':m5,'marketRet20':m20})
 return [x for x in P if 'relRet5' in x],used

def prep_fit(X,m):
 A=np.array(X[m],float,copy=True);imp=np.nanmedian(A,0);imp=np.nan_to_num(imp,nan=0.,posinf=0.,neginf=0.);bad=~np.isfinite(A);A[bad]=np.take(imp,np.where(bad)[1]);mu=A.mean(0);sd=A.std(0);sd[sd<1e-9]=1.;return imp,mu,sd
def prep_apply(X,imp,mu,sd):
 A=np.array(X,float,copy=True);bad=~np.isfinite(A);A[bad]=np.take(imp,np.where(bad)[1]);return (A-mu)/sd

def rank_stats(y,p,d):
 ic=[];spr=[];top=[];bot=[];avg=[]
 for day in sorted(set(d)):
  q=np.where(d==day)[0]
  if len(q)<8:continue
  yy=y[q];pp=p[q];z=spearmanr(yy,pp).statistic
  if finite(z):ic.append(float(z))
  lo,hi=np.quantile(pp,[.2,.8]);a=yy[pp<=lo];b=yy[pp>=hi]
  if len(a) and len(b):spr.append(float(b.mean()-a.mean()));top.append(float(b.mean()));bot.append(float(a.mean()));avg.append(float(yy.mean()))
 return {'ic':float(np.mean(ic)) if ic else 0.,'spread':float(np.mean(spr)) if spr else 0.,'top':float(np.mean(top)) if top else 0.,'bottom':float(np.mean(bot)) if bot else 0.,'mean':float(np.mean(avg)) if avg else 0.}
def calib_bins(y,p,n=8):
 qs=np.unique(np.quantile(p,np.linspace(0,1,n+1)));out=[]
 for i in range(len(qs)-1):
  m=(p>=qs[i])&(p<=qs[i+1] if i==len(qs)-2 else p<qs[i+1])
  if m.sum()>=20:out.append({'lo':float(qs[i]),'hi':float(qs[i+1]),'n':int(m.sum()),'predMean':float(p[m].mean()),'actualMean':float(y[m].mean()),'actualMedian':float(np.median(y[m])),'positiveRate':float(np.mean(y[m]>0))})
 return out
def metric(y,p,d,qlo=None,qhi=None):
 y=np.asarray(y);p=np.asarray(p);e=y-p;mse=float(np.mean(e*e));mse0=float(np.mean(y*y));mae=float(np.mean(abs(e)));mae0=float(np.mean(abs(y)));cs=rank_stats(y,p,d);z={'n':len(y),'r2':1-mse/(mse0 or 1e-18),'mae':mae,'maeImprove':1-mae/(mae0 or 1e-18),'balancedDirection':float(balanced_accuracy_score(y>0,p>0)),'mcc':float(matthews_corrcoef(y>0,p>0)),'csIC':cs['ic'],'csSpread':cs['spread'],'topReturn':cs['top'],'bottomReturn':cs['bottom'],'marketMean':cs['mean'],'topLift':cs['top']-cs['mean'],'topNet30bps':cs['top']-.003,'calibrationBins':calib_bins(y,p)}
 if qlo is not None:z['intervalCoverage']=float(np.mean((y>=p+qlo)&(y<=p+qhi)));z['intervalWidth']=float(qhi-qlo)
 X=np.c_[np.ones(len(p)),p];c=np.linalg.lstsq(X,y,rcond=None)[0];z['calibrationIntercept']=float(c[0]);z['calibrationSlope']=float(c[1]);return z
def bootstrap(y,p,d,reps=200):
 rng=np.random.default_rng(42);days=np.array(sorted(set(d)));A=[]
 for _ in range(reps):
  s=rng.choice(days,len(days),replace=True);idx=np.concatenate([np.where(d==x)[0] for x in s]);m=metric(y[idx],p[idx],d[idx]);A.append([m['balancedDirection'],m['csIC'],m['csSpread'],m['topLift']])
 A=np.array(A);names=['balancedDirection','csIC','csSpread','topLift'];return {n:{'lo':float(np.quantile(A[:,j],.025)),'hi':float(np.quantile(A[:,j],.975))} for j,n in enumerate(names)}
def regimes(y,p,d,idx,P):
 disp=np.array([P[i]['dispersion20'] for i in idx]);med=np.nanmedian(disp);defs={'bear':np.array([P[i]['marketRet20']<0 for i in idx]),'bull':np.array([P[i]['marketRet20']>=0 for i in idx]),'highDispersion':disp>=med,'lowDispersion':disp<med,'riskElevated':np.array([P[i]['riskShare']>=.35 for i in idx]),'riskNormal':np.array([P[i]['riskShare']<.35 for i in idx])};return {k:metric(y[m],p[m],d[m]) for k,m in defs.items() if m.sum()>=200}

def model(name,a):
 if name=='ridge':return Ridge(alpha=a)
 if name=='elastic':return ElasticNet(alpha=a,l1_ratio=.15,max_iter=6000)
 if name=='hgb':return HistGradientBoostingRegressor(max_iter=160,max_leaf_nodes=15,l2_regularization=a,learning_rate=.04,random_state=13)
 if name=='mlp':return MLPRegressor(hidden_layer_sizes=(32,16),alpha=a,max_iter=180,early_stopping=True,validation_fraction=.12,n_iter_no_change=10,random_state=13)
def objective(m):return .25*m['r2']+.18*m['maeImprove']+.17*(m['balancedDirection']-.5)+.22*m['csIC']+.10*np.clip(m['topLift']/0.01,-1,1)+.08*np.clip(m['csSpread']/0.01,-1,1)
def ser(m,n):return {'type':n,'coef':[float(x) for x in m.coef_],'intercept':float(m.intercept_)}
def serlog(m):return {'coef':[float(x) for x in m.coef_[0]],'intercept':float(m.intercept_[0])}

def train(root='.'):
 P,ns=build_panel(root);dates=np.array(sorted(set(x['date'] for x in P)));D=np.array([x['date'] for x in P]);X0=np.array([[x.get(k,np.nan) for k in FEATURES] for x in P]);a60=int(.60*len(dates));a80=int(.80*len(dates));rep={'version':VERSION,'createdAt':datetime.now(timezone.utc).isoformat(),'universe':{'symbols':ns,'rows':len(P),'dates':len(dates),'start':str(dates[0]),'end':str(dates[-1])},'horizons':{}};dep={'version':VERSION,'modelDate':str(dates[-1]),'featureNames':FEATURES,'universe':rep['universe'],'horizons':{},'governance':{'preprocessing':'train-fold only','macroTiming':'strictly prior global close','sentimentInNumericalModel':False,'foreignFlowInNumericalModel':False}}
 for h in HORIZONS:
  y=np.array([x.get('y'+str(h),np.nan) for x in P]);ok=np.isfinite(y);devEnd=max(1,a60-h);valEnd=max(a60+1,a80-h);dev=ok&(D<dates[devEnd]);val=ok&(D>=dates[a60])&(D<dates[valEnd]);test=ok&(D>=dates[a80]);imp,mu,sd=prep_fit(X0,dev);X=prep_apply(X0,imp,mu,sd);C=[];grids={'ridge':[1,10,100,1000],'elastic':[1e-5,5e-5,1e-4,5e-4],'hgb':[.1,1,5],'mlp':[1e-5,1e-4,1e-3]}
  for n,g in grids.items():
   best=None
   for a in g:
    try:
     mm=model(n,a);mm.fit(X[dev],y[dev]);pv=mm.predict(X[val]);mt=metric(y[val],pv,D[val]);sc=objective(mt)
     if best is None or sc>best[0]:best=(sc,a,mm,mt)
    except Exception:pass
   if best:C.append({'name':n,'score':best[0],'param':best[1],'model':best[2],'validation':best[3]})
  C.sort(key=lambda z:z['score'],reverse=True);research=C[0];deploy=max([c for c in C if c['name'] in {'ridge','elastic'}],key=lambda z:z['score']);vp=deploy['model'].predict(X[val]);res=y[val]-vp;q10,q90=np.quantile(res,[.1,.9]);tp=deploy['model'].predict(X[test]);sealed=metric(y[test],tp,D[test],float(q10),float(q90));boot=bootstrap(y[test],tp,D[test]);reg=regimes(y[test],tp,D[test],np.where(test)[0],P);clf=LogisticRegression(C=.2,max_iter=1000,class_weight='balanced').fit(X[dev],y[dev]>0);prob=clf.predict_proba(X[test])[:,1];dirbal=float(balanced_accuracy_score(y[test]>0,prob>=.5));dirmcc=float(matthews_corrcoef(y[test]>0,prob>=.5));b=sealed['calibrationBins'];actual=[x['actualMean'] for x in b];mono=float(spearmanr(np.arange(len(actual)),actual).statistic) if len(actual)>=4 else 0.;checks={'r2Positive':sealed['r2']>0,'rankIC':sealed['csIC']>.012,'topLiftPositive':sealed['topLift']>0,'direction':sealed['balancedDirection']>.51,'directionClassifier':dirbal>.51,'intervalCoverage':.72<=sealed.get('intervalCoverage',0)<=.88,'calibrationMonotonic':finite(mono) and mono>.45,'bootstrapIC':boot['csIC']['lo']>-.003,'bootstrapTopLift':boot['topLift']['lo']>-.002};passed=sum(checks.values())>=7 and checks['r2Positive'] and checks['rankIC'] and checks['intervalCoverage']
  train80=ok&(D<dates[valEnd]);i8,m8,s8=prep_fit(X0,train80);X8=prep_apply(X0,i8,m8,s8);dm=model(deploy['name'],deploy['param']).fit(X8[train80],y[train80]);dc=LogisticRegression(C=.2,max_iter=1000,class_weight='balanced').fit(X8[train80],y[train80]>0);rep['horizons'][str(h)]={'status':'PASS' if passed else 'REVIEW','selectedForDeployment':deploy['name'],'researchChampion':research['name'],'candidateValidation':[{k:v for k,v in c.items() if k!='model'} for c in C],'sealed':sealed,'bootstrap95':boot,'regimes':reg,'directionClassifier':{'balancedAccuracy':dirbal,'mcc':dirmcc},'magnitudeMonotonicity':mono,'checks':checks,'split':{'devEnd':str(dates[devEnd-1]),'validationStart':str(dates[a60]),'validationEnd':str(dates[valEnd-1]),'sealedStart':str(dates[a80])}};dep['horizons'][str(h)]={'status':'PASS' if passed else 'REVIEW','model':ser(dm,deploy['name']),'directionModel':serlog(dc),'impute':i8.tolist(),'mean':m8.tolist(),'std':s8.tolist(),'q10':float(q10),'q90':float(q90),'sealed':sealed,'bootstrap95':boot,'magnitudeMonotonicity':mono,'researchChampion':research['name'],'selectedModel':deploy['name']}
 n=sum(dep['horizons'][str(h)]['status']=='PASS' for h in HORIZONS);dep['promotion']={'status':'PASS' if n==2 else 'REVIEW','passed':n,'required':2};rep['promotion']=dep['promotion'];Path(root,'data/forecast-model-v6.json').write_text(json.dumps(dep,ensure_ascii=False,separators=(',',':')),encoding='utf-8');Path(root,'forecast-validation-v6.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'promotion':dep['promotion'],'universe':rep['universe'],'horizons':{h:{'status':rep['horizons'][h]['status'],'deploy':rep['horizons'][h]['selectedForDeployment'],'research':rep['horizons'][h]['researchChampion'],'sealed':{k:rep['horizons'][h]['sealed'][k] for k in ['r2','maeImprove','balancedDirection','mcc','csIC','csSpread','topLift','topNet30bps','intervalCoverage','calibrationSlope']},'directionClassifier':rep['horizons'][h]['directionClassifier'],'checks':rep['horizons'][h]['checks']} for h in rep['horizons']}},ensure_ascii=False,indent=2))
if __name__=='__main__':train(os.environ.get('GITHUB_WORKSPACE','.'))
