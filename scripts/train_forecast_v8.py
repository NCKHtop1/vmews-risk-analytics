import os,json,math
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge,LogisticRegression
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score,matthews_corrcoef
from train_forecast_v6 import build_panel,FEATURES,prep_fit,prep_apply,rank_stats
VERSION='VMEWS-FORECAST-8.0.0';H=(3,5);FOLDS=((.50,.61),(.61,.72),(.72,.82),(.82,.91),(.91,1.0))
MF=['marketRet1','marketRet5','marketRet20','breadth1','breadth5','breadth20','trend20Share','riskShare','csad1','csad5','dispersion20','marketTechnical','vixLevel','vixRet20','usdVndRet20','dxyRet20','us10yRet20','brentRet20']
def safe_corr(a,b):
 if len(a)<4 or np.std(a)<1e-12 or np.std(b)<1e-12:return 0.
 z=spearmanr(a,b).statistic;return float(z) if math.isfinite(float(z)) else 0.
def linexp(m):return {'coef':[float(x) for x in m.coef_],'intercept':float(m.intercept_)}
def logexp(m):return {'coef':[float(x) for x in m.coef_[0]],'intercept':float(m.intercept_[0])}
def model(n,kind='reg'):
 if kind=='reg':return Ridge(alpha=100) if n=='ridge' else HistGradientBoostingRegressor(max_iter=180,max_leaf_nodes=15,l2_regularization=1,learning_rate=.04,random_state=38)
 return LogisticRegression(C=.2,max_iter=1200,class_weight='balanced') if n=='logit' else HistGradientBoostingClassifier(max_iter=180,max_leaf_nodes=15,l2_regularization=1,learning_rate=.04,random_state=38)
def market_rows(P,D,dates,y):
 rows=[];yt=[]
 for d in dates:
  idx=np.where(D==d)[0];z=y[idx];ok=np.isfinite(z)
  if ok.sum()<8:continue
  x=P[idx[0]];rows.append([x.get(k,np.nan) for k in MF]);yt.append(float(np.median(z[ok])))
 A=np.array(rows,float);Y=np.array(yt,float)
 # deltas encode change in market psychology, not just levels
 base=A.copy();delta=np.zeros_like(base)
 for i in range(5,len(A)):delta[i]=base[i]-base[i-5]
 return np.c_[A,delta],Y
MFD=MF+[k+'Delta5' for k in MF]
def split(dates,D,ok,h,f):
 n=len(dates);a=max(1,int(f[0]*n));b=min(n,int(f[1]*n));e=max(1,a-h);tr=ok&(D<dates[e]);te=ok&(D>=dates[a])&(D<(dates[b] if b<n else '9999-99-99'));return tr,te,a,b,e
def msplit(n,h,f):
 a=max(1,int(f[0]*n));b=min(n,int(f[1]*n));e=max(1,a-h);tr=np.arange(n)<e;te=(np.arange(n)>=a)&(np.arange(n)<b);return tr,te,a,b,e
def market_fit_predict(M,Y,h,f,rn,dn):
 tr,te,a,b,e=msplit(len(Y),h,f);imp,mu,sd=prep_fit(M,tr);X=prep_apply(M,imp,mu,sd);rm=model(rn).fit(X[tr],Y[tr]);dm=model(dn,'cls').fit(X[tr],Y[tr]>0);return np.where(te)[0],rm.predict(X[te]),dm.predict_proba(X[te])[:,1],(imp,mu,sd),{'trainEndIndex':e-1,'testStartIndex':a,'testEndIndex':b-1}
def stock_fit_predict(X0,y,ya,D,dates,h,f,an,dn):
 tr,te,a,b,e=split(dates,D,np.isfinite(y)&np.isfinite(ya),h,f);imp,mu,sd=prep_fit(X0,tr);X=prep_apply(X0,imp,mu,sd);am=model(an).fit(X[tr],ya[tr]);dm=model(dn,'cls').fit(X[tr],y[tr]>0);idx=np.where(te)[0];return idx,am.predict(X[te]),dm.predict_proba(X[te])[:,1],(imp,mu,sd),{'trainEnd':str(dates[e-1]),'testStart':str(dates[a]),'testEnd':str(dates[b-1])}
def map_market(dates,mid,p):return {str(dates[i]):float(v) for i,v in zip(mid,p)}
def alpha_metric(y,p,D):
 s=rank_stats(y,p,D);return {'ic':s['ic'],'spread':s['spread']}
def dir_metric(y,p):return {'balancedAccuracy':float(balanced_accuracy_score(y>0,p>=.5)),'mcc':float(matthews_corrcoef(y>0,p>=.5))}
def choose(P,X0,M,Ym,y,ya,D,dates,h):
 A=[]
 for n in ('ridge','hgb'):
  z=[]
  for f in FOLDS[:3]:
   idx,p,_,_,_=stock_fit_predict(X0,y,ya,D,dates,h,f,n,'logit');z.append(alpha_metric(ya[idx],p,D[idx]))
  A.append({'name':n,'ic':float(np.mean([x['ic'] for x in z])),'spread':float(np.mean([x['spread'] for x in z]))})
 A.sort(key=lambda x:x['ic']+.15*x['spread'],reverse=True)
 MR=[];MD=[]
 for rn in ('ridge','hgb'):
  q=[]
  for f in FOLDS[:3]:
   idx,p,_,_,_=market_fit_predict(M,Ym,h,f,rn,'logit');q.append({'r2':1-np.mean((Ym[idx]-p)**2)/(np.mean(Ym[idx]**2) or 1e-18),'dir':balanced_accuracy_score(Ym[idx]>0,p>0)})
  MR.append({'name':rn,'r2':float(np.mean([x['r2'] for x in q])),'direction':float(np.mean([x['dir'] for x in q]))})
 MR.sort(key=lambda x:x['r2']+.15*(x['direction']-.5),reverse=True)
 for dn in ('logit','hgbc'):
  q=[]
  for f in FOLDS[:3]:
   idx,_,p,_,_=market_fit_predict(M,Ym,h,f,'ridge',dn);q.append(dir_metric(Ym[idx],p))
  MD.append({'name':dn,'balancedAccuracy':float(np.mean([x['balancedAccuracy'] for x in q])),'mcc':float(np.mean([x['mcc'] for x in q]))})
 MD.sort(key=lambda x:x['balancedAccuracy']+.2*x['mcc'],reverse=True)
 SD=[]
 for dn in ('logit','hgbc'):
  q=[]
  for f in FOLDS[:3]:
   idx,_,p,_,_=stock_fit_predict(X0,y,ya,D,dates,h,f,'ridge',dn);q.append(dir_metric(y[idx],p))
  SD.append({'name':dn,'balancedAccuracy':float(np.mean([x['balancedAccuracy'] for x in q])),'mcc':float(np.mean([x['mcc'] for x in q]))})
 SD.sort(key=lambda x:x['balancedAccuracy']+.2*x['mcc'],reverse=True)
 return {'alpha':A,'marketReg':MR,'marketDir':MD,'stockDir':SD,'researchAlpha':A[0]['name'],'researchMarketReg':MR[0]['name'],'researchMarketDir':MD[0]['name'],'researchStockDir':SD[0]['name'],'deployAlpha':'ridge','deployMarketReg':'ridge','deployMarketDir':'logit','deployStockDir':'logit'}
def fold_components(P,X0,M,Ym,y,ya,D,dates,h,f,cfg):
 si,ap,sp,_,smeta=stock_fit_predict(X0,y,ya,D,dates,h,f,cfg['deployAlpha'],cfg['deployStockDir']);mi,mp,md,_,mmeta=market_fit_predict(M,Ym,h,f,cfg['deployMarketReg'],cfg['deployMarketDir']);mmap=map_market(dates,mi,mp);pdmap=map_market(dates,mi,md);mPred=np.array([mmap.get(str(D[i]),0.) for i in si]);mProb=np.array([pdmap.get(str(D[i]),.5) for i in si]);return si,mPred,ap,mProb,sp,smeta,mmeta
def fit_meta(y,m,a,mp,sp):
 X=np.c_[m,a,mp-.5,sp-.5];r=Ridge(alpha=10).fit(X,y);c=LogisticRegression(C=.4,max_iter=1200,class_weight='balanced').fit(X,y>0);return r,c
def apply_meta(r,c,m,a,mp,sp):
 X=np.c_[m,a,mp-.5,sp-.5];return r.predict(X),c.predict_proba(X)[:,1]
def cal_bins(y,p,n=8):
 qs=np.unique(np.quantile(p,np.linspace(0,1,n+1)));o=[]
 for j in range(len(qs)-1):
  m=(p>=qs[j])&(p<=qs[j+1] if j==len(qs)-2 else p<qs[j+1])
  if m.sum()>=30:o.append({'n':int(m.sum()),'predMean':float(p[m].mean()),'actualMean':float(y[m].mean()),'actualMedian':float(np.median(y[m])),'positiveRate':float(np.mean(y[m]>0)),'gt1Pct':float(np.mean(y[m]>.01)),'ltMinus1Pct':float(np.mean(y[m]<-.01))})
 return o
def audit(y,p,prob,D,q10,q90):
 e=y-p;cs=rank_stats(y,p,D);bb=cal_bins(y,p);actual=[x['actualMean'] for x in bb];mono=safe_corr(np.arange(len(actual)),actual) if len(actual)>=4 else 0.;X=np.c_[np.ones(len(p)),p];coef=np.linalg.lstsq(X,y,rcond=None)[0];return {'n':len(y),'r2':1-np.mean(e*e)/(np.mean(y*y) or 1e-18),'maeImprove':1-np.mean(abs(e))/(np.mean(abs(y)) or 1e-18),'balancedDirection':float(balanced_accuracy_score(y>0,prob>=.5)),'mcc':float(matthews_corrcoef(y>0,prob>=.5)),'csIC':cs['ic'],'csSpread':cs['spread'],'topReturn':cs['top'],'marketMean':cs['mean'],'topLift':cs['top']-cs['mean'],'topNet30bps':cs['top']-.003,'coverage':float(np.mean((y>=p+q10)&(y<=p+q90))),'width':float(q90-q10),'calibrationIntercept':float(coef[0]),'calibrationSlope':float(coef[1]),'monotonicity':mono,'bins':bb}
def select_rules(y,p,prob,market,marketProb,side):
 base=float(np.mean(y>0)) if side=='pos' else float(np.mean(y<0));best=None
 for pt in (.52,.55,.58,.60,.62,.65):
  for er in (.0025,.005,.0075,.01,.015):
   for mt in (-.0075,-.005,-.0025,0.):
    m=(prob>=pt)&(p>=er)&(market>=mt)&(marketProb>=.48) if side=='pos' else (prob<=1-pt)&(p<=-er)&(market<=-mt)&(marketProb<=.52)
    n=int(m.sum())
    if n<50:continue
    prec=float(np.mean(y[m]>0)) if side=='pos' else float(np.mean(y[m]<0));mean=float(np.mean(y[m]));score=(prec-base)*math.sqrt(n)+(.4*mean if side=='pos' else -.4*mean)
    if best is None or score>best['score']:best={'pThreshold':pt,'returnThreshold':er,'marketThreshold':mt,'n':n,'precision':prec,'baseRate':base,'lift':prec-base,'meanReturn':mean,'score':score}
 return best
def eval_rule(rule,y,p,prob,market,marketProb,side):
 if not rule:return {'n':0,'approved':False}
 pt=rule['pThreshold'];er=rule['returnThreshold'];mt=rule['marketThreshold'];m=(prob>=pt)&(p>=er)&(market>=mt)&(marketProb>=.48) if side=='pos' else (prob<=1-pt)&(p<=-er)&(market<=-mt)&(marketProb<=.52);n=int(m.sum());base=float(np.mean(y>0)) if side=='pos' else float(np.mean(y<0));prec=float(np.mean(y[m]>0)) if side=='pos' and n else (float(np.mean(y[m]<0)) if n else 0.);mean=float(np.mean(y[m])) if n else 0.;approved=n>=35 and prec>=base+.05 and ((mean>.0025) if side=='pos' else (mean<-.0025));return {'n':n,'precision':prec,'baseRate':base,'lift':prec-base,'meanReturn':mean,'approved':approved}
def train(root='.'):
 P,ns=build_panel(root);D=np.array([x['date'] for x in P]);dates=np.array(sorted(set(D)));X0=np.array([[x.get(k,np.nan) for k in FEATURES] for x in P],float);rep={'version':VERSION,'createdAt':datetime.now(timezone.utc).isoformat(),'universe':{'symbols':ns,'rows':len(P),'dates':len(dates),'start':str(dates[0]),'end':str(dates[-1])},'horizons':{}};dep={'version':VERSION,'modelDate':str(dates[-1]),'featureNames':FEATURES,'marketFeatureNames':MFD,'universe':rep['universe'],'horizons':{},'governance':{'pointEstimate':'shown only when magnitude gate passes','foreignFlow':'current corroboration only, not historical feature','sentiment':'current DL corroboration only until PIT archive matures','macroTiming':'strictly prior date for global close data','recommendation':'absolute market regime + stock alpha + direction + risk + uncertainty'}}
 for h in H:
  y=np.array([x.get('y'+str(h),np.nan) for x in P],float);M,Ym=market_rows(P,D,dates,y);ymap={str(d):float(v) for d,v in zip(dates,Ym)};ya=np.array([y[i]-ymap.get(str(D[i]),np.nan) for i in range(len(P))]);cfg=choose(P,X0,M,Ym,y,ya,D,dates,h);ci,cm,ca,cmp,csp,_,_=fold_components(P,X0,M,Ym,y,ya,D,dates,h,FOLDS[3],cfg);mr,mc=fit_meta(y[ci],cm,ca,cmp,csp);cp,cprob=apply_meta(mr,mc,cm,ca,cmp,csp);res=y[ci]-cp;q10,q90=[float(x) for x in np.quantile(res,[.1,.9])];posRule=select_rules(y[ci],cp,cprob,cm,cmp,'pos');negRule=select_rules(y[ci],cp,cprob,cm,cmp,'neg');ai,am,aa,amp,asp,smeta,mmeta=fold_components(P,X0,M,Ym,y,ya,D,dates,h,FOLDS[4],cfg);ap,aprob=apply_meta(mr,mc,am,aa,amp,asp);au=audit(y[ai],ap,aprob,D[ai],q10,q90);posAudit=eval_rule(posRule,y[ai],ap,aprob,am,amp,'pos');negAudit=eval_rule(negRule,y[ai],ap,aprob,am,amp,'neg');alphaAudit=alpha_metric(ya[ai],aa,D[ai]);marketAudit={'r2':1-np.mean((Ym[int(.91*len(Ym)):]-np.array([ymap.get(str(d),0) for d in dates[int(.91*len(dates)):]]))**2)/(np.mean(Ym[int(.91*len(Ym)):]**2) or 1e-18)};magnitudeApproved=au['r2']>0 and au['maeImprove']>-.005 and au['monotonicity']>.55 and .55<=au['calibrationSlope']<=1.65 and .70<=au['coverage']<=.90;directionApproved=au['balancedDirection']>.515 and au['mcc']>.02;rankingApproved=alphaAudit['ic']>.02 and au['csIC']>.025 and au['topLift']>0;status='PASS' if directionApproved and rankingApproved else 'REVIEW';rep['horizons'][str(h)]={'status':status,'development':cfg,'calibrationFold':{'stock':smeta,'market':mmeta},'audit':{'metrics':au,'alpha':alphaAudit,'positiveRule':posAudit,'negativeRule':negAudit},'gates':{'directionApproved':directionApproved,'rankingApproved':rankingApproved,'magnitudeApproved':magnitudeApproved,'positiveRecommendationApproved':posAudit['approved'],'negativeRecommendationApproved':negAudit['approved']}}
  # final linear deploy models trained on all historical data; meta parameters and rules remain frozen from calibration/audit protocol
  valid=np.isfinite(y)&np.isfinite(ya);si,_,_,_=split(dates,D,valid,h,(0.,1.));simp,smu,ssd=prep_fit(X0,valid);SX=prep_apply(X0,simp,smu,ssd);salpha=Ridge(alpha=100).fit(SX[valid],ya[valid]);sdir=LogisticRegression(C=.2,max_iter=1200,class_weight='balanced').fit(SX[valid],y[valid]>0);mvalid=np.isfinite(Ym);mimp,mmu,msd=prep_fit(M,mvalid);MX=prep_apply(M,mimp,mmu,msd);mreg=Ridge(alpha=100).fit(MX[mvalid],Ym[mvalid]);mdir=LogisticRegression(C=.2,max_iter=1200,class_weight='balanced').fit(MX[mvalid],Ym[mvalid]>0);dep['horizons'][str(h)]={'status':status,'gates':rep['horizons'][str(h)]['gates'],'stockAlphaModel':linexp(salpha),'stockDirectionModel':logexp(sdir),'stockImpute':[float(x) for x in simp],'stockMean':[float(x) for x in smu],'stockStd':[float(x) for x in ssd],'marketModel':linexp(mreg),'marketDirectionModel':logexp(mdir),'marketImpute':[float(x) for x in mimp],'marketMean':[float(x) for x in mmu],'marketStd':[float(x) for x in msd],'metaMagnitude':linexp(mr),'metaDirection':logexp(mc),'q10':q10,'q90':q90,'positiveRule':posRule,'negativeRule':negRule,'audit':rep['horizons'][str(h)]['audit']}
 p=sum(dep['horizons'][str(h)]['status']=='PASS' for h in H);dep['promotion']={'status':'PASS' if p==2 else 'REVIEW','passed':p,'required':2};rep['promotion']=dep['promotion'];Path(root,'data/forecast-model-v8.json').write_text(json.dumps(dep,ensure_ascii=False,separators=(',',':')),encoding='utf-8');Path(root,'forecast-validation-v8.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'promotion':dep['promotion'],'universe':rep['universe'],'horizons':{h:{'status':rep['horizons'][h]['status'],'gates':rep['horizons'][h]['gates'],'audit':rep['horizons'][h]['audit']} for h in rep['horizons']}},ensure_ascii=False,indent=2))
if __name__=='__main__':train(os.environ.get('GITHUB_WORKSPACE','.'))