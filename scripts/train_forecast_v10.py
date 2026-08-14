import json, math, os
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import balanced_accuracy_score, matthews_corrcoef
from train_forecast_v6 import build_panel, BASE, CROSS, prep_fit, prep_apply, rank_stats

VERSION='VMEWS-FORECAST-10.0.0'
HORIZONS=(3,5)
# Only features that have the same definition in historical training and browser inference.
FEATURES=BASE+[x for x in CROSS if x!='marketTechnical']
DEV=((.50,.61),(.61,.72),(.72,.82))
CAL=(.82,.91)
AUD=(.91,1.0)


def split(dates,D,ok,h,f):
    n=len(dates); a=max(1,int(f[0]*n)); b=min(n,int(f[1]*n)); purge=max(1,a-h)
    tr=ok&(D<dates[purge])
    te=ok&(D>=dates[a])&(D<(dates[b] if b<n else '9999-99-99'))
    return tr,te

def fit_reg(X,y,D,dates,h,f,alpha):
    ok=np.isfinite(y);tr,te=split(dates,D,ok,h,f);imp,mu,sd=prep_fit(X,tr);Z=prep_apply(X,imp,mu,sd)
    m=Ridge(alpha=alpha).fit(Z[tr],y[tr]);return np.where(te)[0],m.predict(Z[te]),m,(imp,mu,sd)

def fit_cls(X,y,D,dates,h,f,C):
    ok=np.isfinite(y);tr,te=split(dates,D,ok,h,f);imp,mu,sd=prep_fit(X,tr);Z=prep_apply(X,imp,mu,sd)
    m=LogisticRegression(C=C,max_iter=1500,class_weight='balanced').fit(Z[tr],y[tr]>0)
    return np.where(te)[0],m.predict_proba(Z[te])[:,1],m,(imp,mu,sd)

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

def buckets(y,p,n=8):
    qs=np.unique(np.quantile(p,np.linspace(0,1,n+1)));out=[]
    for j in range(len(qs)-1):
        m=(p>=qs[j])&(p<=qs[j+1] if j==len(qs)-2 else p<qs[j+1])
        if m.sum()<30:continue
        z=y[m]
        out.append({'lo':float(qs[j]),'hi':float(qs[j+1]),'n':int(m.sum()),'meanReturn':float(np.mean(z)),'medianReturn':float(np.median(z)),'positiveRate':float(np.mean(z>0)),'q20':float(np.quantile(z,.2)),'q80':float(np.quantile(z,.8))})
    return out

def by_bucket(bs,x):
    for b in bs:
        if x>=b['lo'] and x<=b['hi']:return b
    return bs[0] if x<bs[0]['lo'] else bs[-1]

def date_bootstrap(y,p,D,reps=300):
    days=np.array(sorted(set(D)));rng=np.random.default_rng(1007);vals=[]
    for _ in range(reps):
        chosen=rng.choice(days,len(days),replace=True);idx=np.concatenate([np.where(D==d)[0] for d in chosen]);s=rank_stats(y[idx],p[idx],D[idx]);vals.append((s['ic'],s['spread']))
    A=np.asarray(vals,float)
    return {'ic95':[float(np.quantile(A[:,0],.025)),float(np.quantile(A[:,0],.975))],'spread95':[float(np.quantile(A[:,1],.025)),float(np.quantile(A[:,1],.975))]}

def segment_metrics(y,ap,dp,D,mask):
    q=np.where(mask)[0]
    if len(q)<100:return None
    s=rank_stats(y[q],ap[q],D[q]);yy=y[q]>0
    return {'n':int(len(q)),'alphaIC':float(s['ic']),'alphaSpread':float(s['spread']),'balancedAccuracy':float(balanced_accuracy_score(yy,dp[q]>=.5)),'mcc':float(matthews_corrcoef(yy,dp[q]>=.5))}

def serialize_linear(m):return {'coef':[float(x) for x in m.coef_],'intercept':float(m.intercept_)}
def serialize_logit(m):return {'coef':[float(x) for x in m.coef_[0]],'intercept':float(m.intercept_[0])}

def train(root='.'):
    P,ns=build_panel(root);D=np.array([x['date'] for x in P]);dates=np.array(sorted(set(D)));symbols=sorted(set(str(x['symbol']) for x in P))
    X=np.asarray([[x.get(k,np.nan) for k in FEATURES] for x in P],float)
    out={'version':VERSION,'createdAt':datetime.now(timezone.utc).isoformat(),'universe':{'symbols':ns,'symbolList':symbols,'rows':len(P),'dates':len(dates),'start':str(dates[0]),'end':str(dates[-1])},'featureNames':FEATURES,'horizons':{},'governance':{'target':'cross-sectional relative return over T+3/T+5','probabilityDisplay':False,'directionOutput':'model score only; not calibrated probability','magnitude':'historical CAL bucket distribution; not a point target','featureParity':'macro and marketTechnical excluded because historical/live definitions were not identical','flow':'not used; free production source failed audit','news':'event-study context only; not numerical model input','validation':'chronological DEV -> CAL -> sealed AUD with horizon purge; day-block bootstrap and regime checks','actionAuthority':'none'}}
    for h in HORIZONS:
        y=np.asarray([x.get('y'+str(h),np.nan) for x in P],float);mr=market_return_map(P,D,dates,y);alpha=np.asarray([y[i]-mr.get(str(D[i]),np.nan) for i in range(len(P))],float)
        bestA,candA=choose_alpha(X,alpha,D,dates,h);bestC,candC=choose_C(X,y,D,dates,h)
        ci,cap,_,_=fit_reg(X,alpha,D,dates,h,CAL,bestA['alpha']);bs=buckets(y[ci],cap)
        ai,aap,_,_=fit_reg(X,alpha,D,dates,h,AUD,bestA['alpha']);di,adp,_,_=fit_cls(X,y,D,dates,h,AUD,bestC['C']);assert np.array_equal(ai,di)
        yy=y[ai];DD=D[ai];cs=rank_stats(alpha[ai],aap,DD);bal=float(balanced_accuracy_score(yy>0,adp>=.5));mcc=float(matthews_corrcoef(yy>0,adp>=.5));boot=date_bootstrap(alpha[ai],aap,DD)
        mapped=[by_bucket(bs,x) for x in aap];bucketMean=np.asarray([b['meanReturn'] for b in mapped]);mae=float(np.mean(abs(yy-bucketMean)));mae0=float(np.mean(abs(yy)));maeImprove=1-mae/(mae0 or 1e-18);mono=float(spearmanr(np.arange(len(bs)),[b['meanReturn'] for b in bs]).statistic) if len(bs)>=4 else 0.
        mom=np.asarray([P[i].get('ret5',0.) for i in ai],float);momcs=rank_stats(alpha[ai],mom,DD);mombal=float(balanced_accuracy_score(yy>0,mom>=0))
        ud=np.array(sorted(set(DD)));mid=ud[len(ud)//2];half1=DD<=mid;half2=DD>mid
        mret=np.asarray([P[i].get('marketRet20',0.) for i in ai],float);risk=np.asarray([P[i].get('riskShare',0.) for i in ai],float);rmed=float(np.median(risk))
        segments={'firstHalf':segment_metrics(alpha[ai],aap,adp,DD,half1),'secondHalf':segment_metrics(alpha[ai],aap,adp,DD,half2),'bear':segment_metrics(alpha[ai],aap,adp,DD,mret<0),'bull':segment_metrics(alpha[ai],aap,adp,DD,mret>=0),'higherRiskBreadth':segment_metrics(alpha[ai],aap,adp,DD,risk>=rmed),'lowerRiskBreadth':segment_metrics(alpha[ai],aap,adp,DD,risk<rmed)}
        gates={'rankingApproved':bool(cs['ic']>.02 and cs['spread']>.002 and boot['ic95'][0]>-.005),'directionSupportive':bool(bal>.515 and mcc>.02),'bucketApproved':bool(len(bs)>=6 and mono>.45 and maeImprove>-.08),'betterThanMomentumRank':bool(cs['ic']>momcs['ic'])}
        valid=np.isfinite(alpha)&np.isfinite(y);imp,mu,sd=prep_fit(X,valid);Z=prep_apply(X,imp,mu,sd);areg=Ridge(alpha=bestA['alpha']).fit(Z[valid],alpha[valid]);dclf=LogisticRegression(C=bestC['C'],max_iter=1500,class_weight='balanced').fit(Z[valid],y[valid]>0)
        out['horizons'][str(h)]={'status':'PASS' if gates['rankingApproved'] and gates['bucketApproved'] else 'REVIEW','gates':gates,'development':{'alphaCandidates':candA,'directionCandidates':candC,'selectedAlpha':bestA['alpha'],'selectedC':bestC['C']},'sealedAudit':{'n':int(len(ai)),'start':str(min(DD)),'end':str(max(DD)),'alphaIC':float(cs['ic']),'alphaSpread':float(cs['spread']),'directionBalancedAccuracy':bal,'directionMCC':mcc,'bootstrap':boot,'bucketMonotonicity':mono,'bucketMAEImprove':float(maeImprove),'momentumBaseline':{'alphaIC':float(momcs['ic']),'alphaSpread':float(momcs['spread']),'directionBalancedAccuracy':mombal},'segments':segments},'calibrationBuckets':bs,'alphaModel':serialize_linear(areg),'directionModel':serialize_logit(dclf),'impute':[float(x) for x in imp],'mean':[float(x) for x in mu],'std':[float(x) for x in sd]}
    out['promotion']={'status':'PASS' if all(out['horizons'][str(h)]['status']=='PASS' for h in HORIZONS) else 'REVIEW','actionable':False,'exactMagnitude':False}
    Path(root,'data/forecast-model-v10.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'version':VERSION,'universe':out['universe'],'promotion':out['promotion'],'audit':{h:out['horizons'][h]['sealedAudit'] for h in out['horizons']}},ensure_ascii=False,indent=2))
if __name__=='__main__':train(os.environ.get('GITHUB_WORKSPACE','.'))
