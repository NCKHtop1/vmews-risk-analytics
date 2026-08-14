import json, math, os
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import balanced_accuracy_score, matthews_corrcoef
from train_forecast_v6 import build_panel, BASE, CROSS, prep_fit, prep_apply, rank_stats

VERSION='VMEWS-FORECAST-10.1.0'
HORIZONS=(3,5)
FEATURES=BASE+[x for x in CROSS if x!='marketTechnical']
DEV=((.50,.61),(.61,.72),(.72,.82))
CAL=(.82,.91)
AUD=(.91,1.0)


def split(dates,D,ok,h,f):
    n=len(dates);a=max(1,int(f[0]*n));b=min(n,int(f[1]*n));purge=max(1,a-h)
    tr=ok&(D<dates[purge]);te=ok&(D>=dates[a])&(D<(dates[b] if b<n else '9999-99-99'))
    return tr,te

def fit_reg(X,y,D,dates,h,f,alpha):
    ok=np.isfinite(y);tr,te=split(dates,D,ok,h,f);imp,mu,sd=prep_fit(X,tr);Z=prep_apply(X,imp,mu,sd);m=Ridge(alpha=alpha).fit(Z[tr],y[tr]);return np.where(te)[0],m.predict(Z[te]),m,(imp,mu,sd)

def fit_cls(X,y,D,dates,h,f,C):
    ok=np.isfinite(y);tr,te=split(dates,D,ok,h,f);imp,mu,sd=prep_fit(X,tr);Z=prep_apply(X,imp,mu,sd);m=LogisticRegression(C=C,max_iter=1500,class_weight='balanced').fit(Z[tr],y[tr]>0);return np.where(te)[0],m.predict_proba(Z[te])[:,1],m,(imp,mu,sd)

def market_return_map(P,D,dates,y):
    out={}
    for d in dates:
        q=np.where(D==d)[0];z=y[q];z=z[np.isfinite(z)]
        if len(z)>=8:out[str(d)]=float(np.median(z))
    return out

def choose_alpha(X,alpha,D,dates,h):
    rows=[]
    for a in (10.,100.,1000.):
        vals=[]
        for f in DEV:
            i,p,_,_=fit_reg(X,alpha,D,dates,h,f,a);s=rank_stats(alpha[i],p,D[i]);vals.append((s['ic'],s['spread']))
        rows.append({'alpha':a,'ic':float(np.mean([z[0] for z in vals])),'spread':float(np.mean([z[1] for z in vals]))})
    rows.sort(key=lambda z:z['ic']+.15*z['spread'],reverse=True);return rows[0],rows

def choose_C(X,y,D,dates,h):
    rows=[]
    for C in (.05,.2,1.0):
        vals=[]
        for f in DEV:
            i,p,_,_=fit_cls(X,y,D,dates,h,f,C);yy=y[i]>0;vals.append((balanced_accuracy_score(yy,p>=.5),matthews_corrcoef(yy,p>=.5)))
        rows.append({'C':C,'balancedAccuracy':float(np.mean([z[0] for z in vals])),'mcc':float(np.mean([z[1] for z in vals]))})
    rows.sort(key=lambda z:z['balancedAccuracy']+.2*z['mcc'],reverse=True);return rows[0],rows

def make_buckets(target,pred,n=8):
    target=np.asarray(target,float);pred=np.asarray(pred,float);qs=np.unique(np.quantile(pred,np.linspace(0,1,n+1)));out=[]
    for j in range(len(qs)-1):
        m=(pred>=qs[j])&(pred<=qs[j+1] if j==len(qs)-2 else pred<qs[j+1])
        if m.sum()<30:continue
        z=target[m]
        out.append({'lo':float(qs[j]),'hi':float(qs[j+1]),'n':int(m.sum()),'meanReturn':float(np.mean(z)),'medianReturn':float(np.median(z)),'positiveRate':float(np.mean(z>0)),'q20':float(np.quantile(z,.2)),'q80':float(np.quantile(z,.8))})
    return out

def by_bucket(bs,x):
    for b in bs:
        if x>=b['lo'] and x<=b['hi']:return b
    return bs[0] if x<bs[0]['lo'] else bs[-1]

def fixed_bucket_audit(target,pred,bs):
    target=np.asarray(target,float);pred=np.asarray(pred,float);rows=[];prob=np.zeros(len(target));covered=np.zeros(len(target),bool)
    for j,b in enumerate(bs):
        m=(pred>=b['lo'])&(pred<=b['hi'] if j==len(bs)-1 else pred<b['hi'])
        if not m.any():continue
        z=target[m];rows.append({'index':j,'n':int(m.sum()),'calPositiveRate':float(b['positiveRate']),'actualPositiveRate':float(np.mean(z>0)),'actualMeanReturn':float(np.mean(z)),'actualMedianReturn':float(np.median(z))});prob[m]=float(b['positiveRate']);covered[m]=True
    valid=[x for x in rows if x['n']>=30]
    def mono(k):
        if len(valid)<4:return 0.
        z=spearmanr([x['index'] for x in valid],[x[k] for x in valid]).statistic
        return float(z) if math.isfinite(float(z)) else 0.
    yy=(target[covered]>0).astype(float);pp=prob[covered]
    base=float(np.mean(yy)) if len(yy) else .5;brier=float(np.mean((yy-pp)**2)) if len(yy) else None;brier0=float(np.mean((yy-base)**2)) if len(yy) else None
    ece=(sum(x['n']*abs(x['actualPositiveRate']-x['calPositiveRate']) for x in rows)/sum(x['n'] for x in rows)) if rows else None
    return {'rows':rows,'populatedBins':len(valid),'positiveRateMonotonicity':mono('actualPositiveRate'),'meanReturnMonotonicity':mono('actualMeanReturn'),'brier':brier,'brierSkill':(1-brier/brier0) if brier is not None and brier0 else None,'ece':float(ece) if ece is not None else None}

def alpha_bucket_audit(alpha,pred,bs):
    mapped=[by_bucket(bs,x) for x in pred];mu=np.asarray([b['meanReturn'] for b in mapped]);mae=float(np.mean(abs(alpha-mu)));mae0=float(np.mean(abs(alpha)));imp=1-mae/(mae0 or 1e-18);fixed=fixed_bucket_audit(alpha,pred,bs);fixed['maeImprove']=imp;return fixed

def date_bootstrap(y,p,D,reps=300):
    days=np.array(sorted(set(D)));rng=np.random.default_rng(1007);vals=[]
    for _ in range(reps):
        chosen=rng.choice(days,len(days),replace=True);idx=np.concatenate([np.where(D==d)[0] for d in chosen]);s=rank_stats(y[idx],p[idx],D[idx]);vals.append((s['ic'],s['spread']))
    A=np.asarray(vals,float);return {'ic95':[float(np.quantile(A[:,0],.025)),float(np.quantile(A[:,0],.975))],'spread95':[float(np.quantile(A[:,1],.025)),float(np.quantile(A[:,1],.975))]}

def segment_metrics(y,ap,dp,D,mask):
    q=np.where(mask)[0]
    if len(q)<100:return None
    s=rank_stats(y[q],ap[q],D[q]);yy=y[q]>0
    return {'n':int(len(q)),'alphaIC':float(s['ic']),'alphaSpread':float(s['spread']),'balancedAccuracy':float(balanced_accuracy_score(yy,dp[q]>=.5)),'mcc':float(matthews_corrcoef(yy,dp[q]>=.5))}

def serialize_linear(m):return {'coef':[float(x) for x in m.coef_],'intercept':float(m.intercept_)}
def serialize_logit(m):return {'coef':[float(x) for x in m.coef_[0]],'intercept':float(m.intercept_[0])}

def train(root='.'):
    P,ns=build_panel(root);D=np.array([x['date'] for x in P]);dates=np.array(sorted(set(D)));symbols=sorted(set(str(x['symbol']) for x in P));X=np.asarray([[x.get(k,np.nan) for k in FEATURES] for x in P],float)
    out={'version':VERSION,'createdAt':datetime.now(timezone.utc).isoformat(),'universe':{'symbols':ns,'symbolList':symbols,'rows':len(P),'dates':len(dates),'start':str(dates[0]),'end':str(dates[-1])},'featureNames':FEATURES,'horizons':{},'governance':{'target':'cross-sectional relative return over T+3/T+5 plus separate absolute-direction classifier','probabilityDisplay':False,'directionOutput':'raw classifier score is not displayed as a probability; empirical up-frequency comes only from an independent calibration period','magnitude':'absolute-return range comes from direction-score calibration buckets only when the sealed scenario gate passes','flow':'not used; free production source failed audit','news':'event-study context only; retrospective news is excluded from numerical forecast','validation':'chronological DEV -> independent CAL -> sealed AUD with horizon purge; day-block bootstrap and regime checks','actionAuthority':'none'}}
    for h in HORIZONS:
        y=np.asarray([x.get('y'+str(h),np.nan) for x in P],float);mr=market_return_map(P,D,dates,y);alpha=np.asarray([y[i]-mr.get(str(D[i]),np.nan) for i in range(len(P))],float);bestA,candA=choose_alpha(X,alpha,D,dates,h);bestC,candC=choose_C(X,y,D,dates,h)
        cai,cap,_,_=fit_reg(X,alpha,D,dates,h,CAL,bestA['alpha']);cdi,cdp,_,_=fit_cls(X,y,D,dates,h,CAL,bestC['C']);alphaBuckets=make_buckets(alpha[cai],cap);directionBuckets=make_buckets(y[cdi],cdp)
        ai,aap,_,_=fit_reg(X,alpha,D,dates,h,AUD,bestA['alpha']);di,adp,_,_=fit_cls(X,y,D,dates,h,AUD,bestC['C']);assert np.array_equal(ai,di)
        yy=y[ai];aa=alpha[ai];DD=D[ai];cs=rank_stats(aa,aap,DD);bal=float(balanced_accuracy_score(yy>0,adp>=.5));mcc=float(matthews_corrcoef(yy>0,adp>=.5));boot=date_bootstrap(aa,aap,DD);alphaCal=alpha_bucket_audit(aa,aap,alphaBuckets);directionCal=fixed_bucket_audit(yy,adp,directionBuckets)
        mom=np.asarray([P[i].get('ret5',0.) for i in ai],float);momcs=rank_stats(aa,mom,DD);mombal=float(balanced_accuracy_score(yy>0,mom>=0));ud=np.array(sorted(set(DD)));mid=ud[len(ud)//2];half1=DD<=mid;half2=DD>mid;mret=np.asarray([P[i].get('marketRet20',0.) for i in ai],float);risk=np.asarray([P[i].get('riskShare',0.) for i in ai],float);rmed=float(np.median(risk));segments={'firstHalf':segment_metrics(aa,aap,adp,DD,half1),'secondHalf':segment_metrics(aa,aap,adp,DD,half2),'bear':segment_metrics(aa,aap,adp,DD,mret<0),'bull':segment_metrics(aa,aap,adp,DD,mret>=0),'higherRiskBreadth':segment_metrics(aa,aap,adp,DD,risk>=rmed),'lowerRiskBreadth':segment_metrics(aa,aap,adp,DD,risk<rmed)}
        bskill=directionCal.get('brierSkill');gates={'rankingApproved':bool(cs['ic']>.02 and cs['spread']>.002 and boot['ic95'][0]>-.005),'directionApproved':bool(bal>.515 and mcc>.02 and directionCal['populatedBins']>=5 and directionCal['positiveRateMonotonicity']>.35 and (bskill is None or bskill>-.02)),'alphaCalibrationApproved':bool(len(alphaBuckets)>=6 and alphaCal['populatedBins']>=5 and alphaCal['meanReturnMonotonicity']>.45 and alphaCal['maeImprove']>-.08),'absoluteScenarioApproved':bool(len(directionBuckets)>=6 and directionCal['populatedBins']>=5 and directionCal['meanReturnMonotonicity']>.30 and directionCal['positiveRateMonotonicity']>.35),'betterThanMomentumRank':bool(cs['ic']>momcs['ic'])}
        valid=np.isfinite(alpha)&np.isfinite(y);imp,mu,sd=prep_fit(X,valid);Z=prep_apply(X,imp,mu,sd);areg=Ridge(alpha=bestA['alpha']).fit(Z[valid],alpha[valid]);dclf=LogisticRegression(C=bestC['C'],max_iter=1500,class_weight='balanced').fit(Z[valid],y[valid]>0);status='PASS' if gates['rankingApproved'] and gates['directionApproved'] and gates['alphaCalibrationApproved'] else 'REVIEW'
        out['horizons'][str(h)]={'status':status,'gates':gates,'development':{'alphaCandidates':candA,'directionCandidates':candC,'selectedAlpha':bestA['alpha'],'selectedC':bestC['C']},'sealedAudit':{'n':int(len(ai)),'start':str(min(DD)),'end':str(max(DD)),'alphaIC':float(cs['ic']),'alphaSpread':float(cs['spread']),'directionBalancedAccuracy':bal,'directionMCC':mcc,'bootstrap':boot,'alphaCalibration':alphaCal,'directionCalibration':directionCal,'momentumBaseline':{'alphaIC':float(momcs['ic']),'alphaSpread':float(momcs['spread']),'directionBalancedAccuracy':mombal},'segments':segments},'alphaCalibrationBuckets':alphaBuckets,'directionCalibrationBuckets':directionBuckets,'alphaModel':serialize_linear(areg),'directionModel':serialize_logit(dclf),'impute':[float(x) for x in imp],'mean':[float(x) for x in mu],'std':[float(x) for x in sd]}
    out['promotion']={'status':'PASS' if all(out['horizons'][str(h)]['status']=='PASS' for h in HORIZONS) else 'REVIEW','actionable':False,'exactMagnitude':False,'absoluteScenario':all(out['horizons'][str(h)]['gates']['absoluteScenarioApproved'] for h in map(str,HORIZONS))}
    Path(root,'data/forecast-model-v10.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'version':VERSION,'universe':out['universe'],'promotion':out['promotion'],'audit':{h:out['horizons'][h]['sealedAudit'] for h in out['horizons']}},ensure_ascii=False,indent=2))
if __name__=='__main__':train(os.environ.get('GITHUB_WORKSPACE','.'))
