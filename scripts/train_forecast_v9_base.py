import os,json,math
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge,LogisticRegression
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score,matthews_corrcoef
from train_forecast_v6 import build_panel,FEATURES,prep_fit,prep_apply,rank_stats
VERSION='VMEWS-FORECAST-9.0.0';H=(3,5);DEV=((.50,.61),(.61,.72),(.72,.82));CAL=(.82,.91);AUD=(.91,1.0)
MARKET_FEATURES=['marketRet1','marketRet5','marketRet20','breadth1','breadth5','breadth20','trend20Share','riskShare','csad1','csad5','dispersion20','marketTechnical','vixLevel','vixRet20','usdVndRet20','dxyRet20','us10yRet20','brentRet20']
def amodel(n):return Ridge(alpha=100) if n=='ridge' else HistGradientBoostingRegressor(max_iter=180,max_leaf_nodes=15,l2_regularization=1,learning_rate=.04,random_state=91)
def cmodel(n):return LogisticRegression(C=.2,max_iter=1200,class_weight='balanced') if n=='logit' else HistGradientBoostingClassifier(max_iter=180,max_leaf_nodes=15,l2_regularization=1,learning_rate=.04,random_state=91)
def split(dates,D,ok,h,f):
 n=len(dates);a=max(1,int(f[0]*n));b=min(n,int(f[1]*n));e=max(1,a-h);return ok&(D<dates[e]),ok&(D>=dates[a])&(D<(dates[b] if b<n else '9999-99-99'))
def market_panel(P,D,dates,y):
 X=[];Y=[]
 for d in dates:
  idx=np.where(D==d)[0];z=y[idx];ok=np.isfinite(z)
  if ok.sum()<8:X.append([np.nan]*len(MARKET_FEATURES));Y.append(np.nan);continue
  X.append([P[idx[0]].get(k,np.nan) for k in MARKET_FEATURES]);Y.append(float(np.median(z[ok])))
 return np.asarray(X,float),np.asarray(Y,float)
def fitpred(X,y,D,dates,h,f,name,kind='reg'):
 ok=np.isfinite(y);tr,te=split(dates,D,ok,h,f);imp,mu,sd=prep_fit(X,tr);Z=prep_apply(X,imp,mu,sd);m=(amodel(name) if kind=='reg' else cmodel(name)).fit(Z[tr],y[tr] if kind=='reg' else y[tr]>0);p=m.predict(Z[te]) if kind=='reg' else m.predict_proba(Z[te])[:,1];return np.where(te)[0],p,m,(imp,mu,sd)
def market_fitpred(X,y,dates,h,f,name,kind='cls'):
 n=len(dates);a=max(1,int(f[0]*n));b=min(n,int(f[1]*n));e=max(1,a-h);ok=np.isfinite(y);tr=ok&(np.arange(n)<e);te=ok&(np.arange(n)>=a)&(np.arange(n)<b);imp,mu,sd=prep_fit(X,tr);Z=prep_apply(X,imp,mu,sd);m=(amodel(name) if kind=='reg' else cmodel(name)).fit(Z[tr],y[tr] if kind=='reg' else y[tr]>0);p=m.predict(Z[te]) if kind=='reg' else m.predict_proba(Z[te])[:,1];return np.where(te)[0],p,m,(imp,mu,sd)
def select(X,y,alpha,D,dates,M,my,h):
 A=[]
 for n in ('ridge','hgb'):
  q=[]
  for f in DEV:
   i,p,_,_=fitpred(X,alpha,D,dates,h,f,n);s=rank_stats(alpha[i],p,D[i]);q.append((s['ic'],s['spread']))
  A.append({'name':n,'ic':float(np.mean([x[0] for x in q])),'spread':float(np.mean([x[1] for x in q]))})
 A.sort(key=lambda z:z['ic']+.15*z['spread'],reverse=True)
 C=[]
 for n in ('logit','hgbc'):
  q=[]
  for f in DEV:
   i,p,_,_=fitpred(X,y,D,dates,h,f,n,'cls');q.append((balanced_accuracy_score(y[i]>0,p>=.5),matthews_corrcoef(y[i]>0,p>=.5)))
  C.append({'name':n,'balancedAccuracy':float(np.mean([x[0] for x in q])),'mcc':float(np.mean([x[1] for x in q]))})
 C.sort(key=lambda z:z['balancedAccuracy']+.2*z['mcc'],reverse=True)
 MC=[]
 for n in ('logit','hgbc'):
  q=[]
  for f in DEV:
   i,p,_,_=market_fitpred(M,my,dates,h,f,n);q.append((balanced_accuracy_score(my[i]>0,p>=.5),matthews_corrcoef(my[i]>0,p>=.5)))
  MC.append({'name':n,'balancedAccuracy':float(np.mean([x[0] for x in q])),'mcc':float(np.mean([x[1] for x in q]))})
 MC.sort(key=lambda z:z['balancedAccuracy']+.2*z['mcc'],reverse=True);return A,C,MC
def mmap(dates,idx,p):return {str(dates[i]):float(v) for i,v in zip(idx,p)}
def thresholds(y,ap,sp,mp,risk,side):
 base=float(np.mean(y>0)) if side=='pos' else float(np.mean(y<0));best=None
 for av in np.quantile(ap,[.55,.65,.75,.85,.90,.95]):
  for ps in (.50,.53,.55,.58,.60):
   for pm in (.45,.48,.50,.52,.55):
    for rg in (.35,.45,.55,.65):
     m=(ap>=av)&(sp>=ps)&(mp>=pm)&(risk<=rg) if side=='pos' else (ap<=-abs(av))&(sp<=1-ps)&(mp<=1-pm)&(risk>=1-rg);n=int(m.sum())
     if n<60:continue
     prec=float(np.mean(y[m]>0)) if side=='pos' else float(np.mean(y[m]<0));mean=float(np.mean(y[m]));score=(prec-base)*math.sqrt(n)+25*(mean if side=='pos' else -mean)
     if best is None or score>best['score']:best={'alphaThreshold':float(av),'stockPThreshold':ps,'marketPThreshold':pm,'riskShareMax':rg,'n':n,'precision':prec,'baseRate':base,'lift':prec-base,'meanReturn':mean,'medianReturn':float(np.median(y[m])),'score':score}
 return best
def maskrule(r,ap,sp,mp,risk,side):
 if not r:return np.zeros(len(ap),bool)
 av=r['alphaThreshold'];ps=r['stockPThreshold'];pm=r['marketPThreshold'];rg=r['riskShareMax'];return (ap>=av)&(sp>=ps)&(mp>=pm)&(risk<=rg) if side=='pos' else (ap<=-abs(av))&(sp<=1-ps)&(mp<=1-pm)&(risk>=1-rg)
def evalrule(r,y,ap,sp,mp,risk,side):
 m=maskrule(r,ap,sp,mp,risk,side);n=int(m.sum());base=float(np.mean(y>0)) if side=='pos' else float(np.mean(y<0));prec=float(np.mean(y[m]>0)) if side=='pos' and n else (float(np.mean(y[m]<0)) if n else 0.);mean=float(np.mean(y[m])) if n else 0.;return {'n':n,'precision':prec,'baseRate':base,'lift':prec-base,'meanReturn':mean,'medianReturn':float(np.median(y[m])) if n else 0.,'approved':bool(n>=40 and prec>=base+.05 and ((mean>.0025) if side=='pos' else mean<-.0025))}
def abins(y,ap,n=8):
 qs=np.unique(np.quantile(ap,np.linspace(0,1,n+1)));o=[]
 for j in range(len(qs)-1):
  m=(ap>=qs[j])&(ap<=qs[j+1] if j==len(qs)-2 else ap<qs[j+1])
  if m.sum()>=30:o.append({'lo':float(qs[j]),'hi':float(qs[j+1]),'n':int(m.sum()),'meanReturn':float(np.mean(y[m])),'medianReturn':float(np.median(y[m])),'positiveRate':float(np.mean(y[m]>0)),'q20':float(np.quantile(y[m],.2)),'q80':float(np.quantile(y[m],.8))})
 return o
def binfor(bs,x):
 for b in bs:
  if x>=b['lo'] and x<=b['hi']:return b
 return bs[0] if x<bs[0]['lo'] else bs[-1]
def linear(m):return {'coef':[float(x) for x in m.coef_],'intercept':float(m.intercept_)}
def logit(m):return {'coef':[float(x) for x in m.coef_[0]],'intercept':float(m.intercept_[0])}
def train(root='.'):
 P,ns=build_panel(root);D=np.array([x['date'] for x in P]);dates=np.array(sorted(set(D)));X=np.array([[x.get(k,np.nan) for k in FEATURES] for x in P],float);out={'version':VERSION,'createdAt':datetime.now(timezone.utc).isoformat(),'universe':{'symbols':ns,'rows':len(P),'dates':len(dates),'start':str(dates[0]),'end':str(dates[-1])},'featureNames':FEATURES,'marketFeatureNames':MARKET_FEATURES,'horizons':{},'governance':{'magnitude':'historical conditional bucket, not exact target','foreignFlow':'live corroboration only','sentiment':'DL context only until PIT archive matures','risk':'canonical VMEWS risk gates recommendation','validation':'DEV model selection, CAL threshold/bucket selection, final AUD historical audit; future immutable live predictions required for post-freeze proof'}}
 for h in H:
  y=np.array([x.get('y'+str(h),np.nan) for x in P],float);M,my=market_panel(P,D,dates,y);ym={str(d):float(v) for d,v in zip(dates,my)};alpha=np.array([y[i]-ym.get(str(D[i]),np.nan) for i in range(len(P))]);A,C,MC=select(X,y,alpha,D,dates,M,my,h);an=A[0]['name'];dn=C[0]['name'];mn=MC[0]['name'];ci,cap,_,_=fitpred(X,alpha,D,dates,h,CAL,an);_,csp,_,_=fitpred(X,y,D,dates,h,CAL,dn,'cls');mi,cmp,_,_=market_fitpred(M,my,dates,h,CAL,mn);mm=mmap(dates,mi,cmp);cm=np.array([mm.get(str(D[i]),.5) for i in ci]);risk=np.array([P[i].get('riskShare',.5) for i in ci]);bs=abins(y[ci],cap);pr=thresholds(y[ci],cap,csp,cm,risk,'pos');nr=thresholds(y[ci],cap,csp,cm,risk,'neg');ai,aap,_,_=fitpred(X,alpha,D,dates,h,AUD,an);_,asp,_,_=fitpred(X,y,D,dates,h,AUD,dn,'cls');mi,amp,_,_=market_fitpred(M,my,dates,h,AUD,mn);mm=mmap(dates,mi,amp);am=np.array([mm.get(str(D[i]),.5) for i in ai]);ar=np.array([P[i].get('riskShare',.5) for i in ai]);cs=rank_stats(alpha[ai],aap,D[ai]);ds={'balancedAccuracy':float(balanced_accuracy_score(y[ai]>0,asp>=.5)),'mcc':float(matthews_corrcoef(y[ai]>0,asp>=.5))};marketY=np.array([ym.get(str(D[i]),0) for i in ai]);ms={'balancedAccuracy':float(balanced_accuracy_score(marketY>0,am>=.5))};pe=evalrule(pr,y[ai],aap,asp,am,ar,'pos');ne=evalrule(nr,y[ai],aap,asp,am,ar,'neg');mapped=[binfor(bs,x) for x in aap];bp=np.array([b['meanReturn'] for b in mapped]);mono=float(spearmanr(np.arange(len(bs)),[b['meanReturn'] for b in bs]).statistic) if len(bs)>=4 else 0.;calMae=1-np.mean(abs(y[ai]-bp))/(np.mean(abs(y[ai])) or 1e-18);g={'rankingApproved':bool(cs['ic']>.02 and cs['spread']>.002),'directionApproved':bool(ds['balancedAccuracy']>.515 and ds['mcc']>.02),'marketGateApproved':bool(ms['balancedAccuracy']>.505),'magnitudeBucketApproved':bool(mono>.45 and calMae>-.08),'positiveRecommendationApproved':pe['approved'],'negativeRecommendationApproved':ne['approved']};valid=np.isfinite(y)&np.isfinite(alpha);imp,mu,sd=prep_fit(X,valid);Z=prep_apply(X,imp,mu,sd);af=Ridge(alpha=100).fit(Z[valid],alpha[valid]);df=LogisticRegression(C=.2,max_iter=1200,class_weight='balanced').fit(Z[valid],y[valid]>0);mok=np.isfinite(my);mimp,mmu,msd=prep_fit(M,mok);MZ=prep_apply(M,mimp,mmu,msd);mf=LogisticRegression(C=.2,max_iter=1200,class_weight='balanced').fit(MZ[mok],my[mok]>0);out['horizons'][str(h)]={'status':'PASS' if g['rankingApproved'] and g['directionApproved'] else 'REVIEW','development':{'alphaCandidates':A,'stockDirectionCandidates':C,'marketDirectionCandidates':MC,'researchAlpha':an,'researchStockDirection':dn,'researchMarketDirection':mn},'gates':g,'historicalAudit':{'alphaIC':cs['ic'],'alphaSpread':cs['spread'],'stockDirection':ds,'marketDirection':ms,'positiveRule':pe,'negativeRule':ne,'bucketMonotonicity':mono,'bucketMAEImprove':float(calMae),'calibrationBuckets':bs},'positiveRule':pr,'negativeRule':nr,'alphaModel':linear(af),'stockDirectionModel':logit(df),'marketDirectionModel':logit(mf),'impute':[float(x) for x in imp],'mean':[float(x) for x in mu],'std':[float(x) for x in sd],'marketImpute':[float(x) for x in mimp],'marketMean':[float(x) for x in mmu],'marketStd':[float(x) for x in msd],'calibrationBuckets':bs}
 out['promotion']={'status':'PASS' if all(out['horizons'][str(h)]['gates']['rankingApproved'] for h in H) else 'REVIEW','actionableT3':bool(out['horizons']['3']['gates']['positiveRecommendationApproved']),'exactMagnitude':False};Path(root,'data/forecast-model-v9.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'version':VERSION,'universe':out['universe'],'promotion':out['promotion'],'horizons':{h:{'status':out['horizons'][h]['status'],'gates':out['horizons'][h]['gates'],'audit':out['horizons'][h]['historicalAudit']} for h in out['horizons']}},ensure_ascii=False,indent=2))
if __name__=='__main__':train(os.environ.get('GITHUB_WORKSPACE','.'))