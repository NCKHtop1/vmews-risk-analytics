import json, math, os, importlib.util
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import balanced_accuracy_score, matthews_corrcoef, brier_score_loss
from forecast_v11_features import stock_features, yahoo_adjusted, FEATURES as LOCAL

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'))
MANIFEST=ROOT/'data/hose-fallbacks/manifest.json'
VERSION='VMEWS-FORECAST-11.0.0';HORIZONS=(1,2,3,4,5)
CROSS=['mret1','mret5','mret20','breadth1','breadth5','breadth20','disp1','disp5','disp20','csad1','csad5','csad20','riskShare','volumeBreadth','highVolShare','herdingCompression','turnoverConcentration','leadershipSpread']
FEATURES=LOCAL+CROSS
DEV=((.48,.60),(.60,.70),(.70,.80));CAL=(.80,.90);AUD=(.90,1.0)

def _finite(x):
    try:return math.isfinite(float(x))
    except:return False

def load_core():
    p=ROOT/'api/stocks.py';sp=importlib.util.spec_from_file_location('v11core',p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
CORE=load_core()

def local_rows(sym):
    p=ROOT/f'data/hose-fallbacks/{sym}.json'
    if not p.exists():return []
    try:
        raw=json.loads(p.read_text(encoding='utf-8')).get('history') or []
        return [{**r,'modelClose':r.get('close')} for r in raw]
    except:return []

def one(sym):
    source='YAHOO_ADJUSTED'
    try:raw,_=yahoo_adjusted(sym,'10y',15)
    except Exception:
        raw=local_rows(sym);source='LOCAL_RAW_FALLBACK'
    rows,fs=stock_features(raw)
    if len(rows)<520 or len(fs)<260:return sym,[],None
    out=[]
    for f in fs:
        i=f['i'];z={'symbol':sym,'source':source,**f,'avgTurnover30':float(np.mean([rows[j]['modelClose']*rows[j]['volume'] for j in range(max(0,i-29),i+1)]))}
        for h in HORIZONS:z['y'+str(h)]=float(math.log(rows[i+h]['modelClose']/rows[i]['modelClose'])) if i+h<len(rows) else np.nan
        out.append(z)
    return sym,out,{'symbol':sym,'source':source,'rows':rows,'feature':out[-1]}

def build_panel():
    m=json.loads(MANIFEST.read_text(encoding='utf-8'));items=[s for s,r in (m.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520];P=[];latest={};used=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs={ex.submit(one,s):s for s in items}
        for f in as_completed(fs):
            s,a,l=f.result()
            if a:P.extend(a);used.append(s);latest[s]=l
    dates=sorted(set(x['date'] for x in P));keep=set(dates[::5]);P=[x for x in P if x['date'] in keep]
    by={}
    for x in P:by.setdefault(x['date'],[]).append(x)
    for d,a in by.items():
        def vals(k):return np.asarray([x[k] for x in a if _finite(x.get(k))],float)
        r1,r5,r20=vals('ret1'),vals('ret5'),vals('ret20');m1,m5,m20=[float(np.median(v)) if len(v) else 0. for v in (r1,r5,r20)]
        disp=[float(np.std(v)) if len(v)>1 else 0. for v in (r1,r5,r20)];cs=[float(np.mean(np.abs(v-m))) if len(v) else 0. for v,m in zip((r1,r5,r20),(m1,m5,m20))]
        turn=np.asarray([max(0.,x.get('avgTurnover30',0.)) for x in a],float);tot=float(turn.sum());conc=float(np.sort(turn)[-max(1,int(.1*len(turn))):].sum()/tot) if tot>0 else 0.
        leader=float(np.quantile(r20,.9)-np.median(r20)) if len(r20)>=10 else 0.;risk=float(np.mean([x['technical']>=50 for x in a]));vb=float(np.mean([x['volumeZ']>0 for x in a]));hv=float(np.mean([x['volPct']>=.8 for x in a]));hc=float(abs(m20)/(cs[2]+1e-6))
        z={'mret1':m1,'mret5':m5,'mret20':m20,'breadth1':float(np.mean(r1>0)) if len(r1) else .5,'breadth5':float(np.mean(r5>0)) if len(r5) else .5,'breadth20':float(np.mean(r20>0)) if len(r20) else .5,'disp1':disp[0],'disp5':disp[1],'disp20':disp[2],'csad1':cs[0],'csad5':cs[1],'csad20':cs[2],'riskShare':risk,'volumeBreadth':vb,'highVolShare':hv,'herdingCompression':hc,'turnoverConcentration':conc,'leadershipSpread':leader}
        for x in a:x.update(z)
    # Current cross-sectional state uses each symbol's latest completed EOD; align to modal latest date.
    cur=[v['feature'] for v in latest.values() if v]
    if cur:
        modal=max(set(x['date'] for x in cur),key=lambda d:sum(y['date']==d for y in cur));cur=[x for x in cur if x['date']==modal]
        if len(cur)>=50:
            tmp={modal:cur}
            # reuse same formulas by building a miniature date block
            a=cur
            r1=np.asarray([x['ret1'] for x in a]);r5=np.asarray([x['ret5'] for x in a]);r20=np.asarray([x['ret20'] for x in a]);m1,m5,m20=map(float,(np.median(r1),np.median(r5),np.median(r20)));disp=[float(np.std(v)) for v in (r1,r5,r20)];cs=[float(np.mean(np.abs(v-m))) for v,m in zip((r1,r5,r20),(m1,m5,m20))];turn=np.asarray([max(0.,x.get('avgTurnover30',0.)) for x in a]);tot=float(turn.sum());cross={'mret1':m1,'mret5':m5,'mret20':m20,'breadth1':float(np.mean(r1>0)),'breadth5':float(np.mean(r5>0)),'breadth20':float(np.mean(r20>0)),'disp1':disp[0],'disp5':disp[1],'disp20':disp[2],'csad1':cs[0],'csad5':cs[1],'csad20':cs[2],'riskShare':float(np.mean([x['technical']>=50 for x in a])),'volumeBreadth':float(np.mean([x['volumeZ']>0 for x in a])),'highVolShare':float(np.mean([x['volPct']>=.8 for x in a])),'herdingCompression':float(abs(m20)/(cs[2]+1e-6)),'turnoverConcentration':float(np.sort(turn)[-max(1,int(.1*len(turn))):].sum()/tot) if tot>0 else 0.,'leadershipSpread':float(np.quantile(r20,.9)-np.median(r20))}
            for s,v in latest.items():
                if v and v['feature']['date']==modal:v['feature'].update(cross)
    print(json.dumps({'symbols':len(used),'rows':len(P),'dates':len(keep),'current':len(latest)},ensure_ascii=False))
    if len(used)<300 or len(P)<120000:raise RuntimeError('V11 panel below production coverage floor')
    return P,latest

def split(dates,D,ok,h,fold):
    n=len(dates);a=max(1,int(fold[0]*n));b=min(n,int(fold[1]*n));cut=max(0,a-h);tr=ok&(D<dates[cut]);te=ok&(D>=dates[a])&(D<(dates[b] if b<n else '9999-99-99'));return tr,te

def prep(X,tr):
    imp=np.nanmedian(X[tr],axis=0);imp=np.where(np.isfinite(imp),imp,0.);Z=np.where(np.isfinite(X),X,imp);mu=Z[tr].mean(0);sd=Z[tr].std(0);sd=np.where(sd<1e-9,1.,sd);return imp,mu,sd

def apply(X,p):
    imp,mu,sd=p;return (np.where(np.isfinite(X),X,imp)-mu)/sd

def rank_stats(y,p,D):
    ics=[];sp=[]
    for d in sorted(set(D)):
        q=np.where(D==d)[0]
        if len(q)<12:continue
        z=spearmanr(y[q],p[q]).statistic
        if _finite(z):ics.append(float(z))
        ord=np.argsort(p[q]);k=max(1,len(q)//5);sp.append(float(np.mean(y[q][ord[-k:]])-np.mean(y[q][ord[:k]])))
    return {'ic':float(np.mean(ics)) if ics else 0.,'spread':float(np.mean(sp)) if sp else 0.}

def ece(y,p,bins=10):
    q=np.linspace(0,1,bins+1);s=0.;n=len(y)
    for a,b in zip(q[:-1],q[1:]):
        m=(p>=a)&(p<(b if b<1 else 1.000001))
        if m.any():s+=m.sum()*abs(float(np.mean(y[m]))-float(np.mean(p[m])))
    return s/max(1,n)

def model(kind,task,params=None):
    params=params or {}
    if task=='reg':
        return Ridge(alpha=params.get('alpha',100.)) if kind=='RIDGE' else HistGradientBoostingRegressor(loss='squared_error',max_depth=3,learning_rate=.05,max_iter=180,l2_regularization=2.,random_state=31)
    return LogisticRegression(C=params.get('C',.2),max_iter=1200,class_weight='balanced') if kind=='LINEAR' else HistGradientBoostingClassifier(max_depth=3,learning_rate=.05,max_iter=160,l2_regularization=2.,random_state=37)

def fit_predict(X,y,D,dates,h,fold,kind,task):
    ok=np.isfinite(y);tr,te=split(dates,D,ok,h,fold);pr=prep(X,tr);Z=apply(X,pr);m=model(kind,task);m.fit(Z[tr],y[tr] if task=='reg' else y[tr]>0);p=m.predict(Z[te]) if task=='reg' else m.predict_proba(Z[te])[:,1];return np.where(te)[0],p

def choose(X,y,alpha,D,dates,h):
    rows=[]
    for reg in ('RIDGE','HGB'):
        for cls in ('LINEAR','HGB'):
            vals=[]
            for f in DEV:
                i,p=fit_predict(X,alpha,D,dates,h,f,reg,'reg');j,dp=fit_predict(X,y,D,dates,h,f,cls,'cls');assert np.array_equal(i,j);rs=rank_stats(alpha[i],p,D[i]);ba=balanced_accuracy_score(y[i]>0,dp>=.5);mc=matthews_corrcoef(y[i]>0,dp>=.5);vals.append((rs['ic'],rs['spread'],ba,mc))
            z={'reg':reg,'cls':cls,'ic':float(np.mean([x[0] for x in vals])),'spread':float(np.mean([x[1] for x in vals])),'ba':float(np.mean([x[2] for x in vals])),'mcc':float(np.mean([x[3] for x in vals]))};z['objective']=z['ic']+.15*z['spread']+.08*(z['ba']-.5)+.03*z['mcc'];rows.append(z)
    rows.sort(key=lambda z:z['objective'],reverse=True);return rows[0],rows

def train_block(X,y,alpha,D,dates,h,fold,choice):
    ok=np.isfinite(y);tr,te=split(dates,D,ok,h,fold);pr=prep(X,tr);Z=apply(X,pr);rg=model(choice['reg'],'reg');cl=model(choice['cls'],'cls');rg.fit(Z[tr],alpha[tr]);cl.fit(Z[tr],y[tr]>0);return np.where(te)[0],rg.predict(Z[te]),cl.predict_proba(Z[te])[:,1]

def buckets(y,score,n=10):
    qs=np.unique(np.quantile(score,np.linspace(0,1,n+1)));out=[]
    for j in range(len(qs)-1):
        m=(score>=qs[j])&(score<=qs[j+1] if j==len(qs)-2 else score<qs[j+1])
        if m.sum()<50:continue
        z=y[m];out.append({'lo':float(qs[j]),'hi':float(qs[j+1]),'n':int(m.sum()),'positiveRate':float(np.mean(z>0)),'meanReturn':float(np.mean(z)),'medianReturn':float(np.median(z)),'q20':float(np.quantile(z,.2)),'q80':float(np.quantile(z,.8))})
    return out

def bfind(bs,x):
    if not bs:return None
    for b in bs:
        if x>=b['lo'] and x<=b['hi']:return b
    return bs[0] if x<bs[0]['lo'] else bs[-1]

def audit(y,alpha,ap,dp,D,calBuckets):
    rs=rank_stats(alpha,ap,D);mapped=[bfind(calBuckets,x) for x in dp];prob=np.asarray([b['positiveRate'] for b in mapped]);med=np.asarray([b['medianReturn'] for b in mapped]);lo=np.asarray([b['q20'] for b in mapped]);hi=np.asarray([b['q80'] for b in mapped]);yy=y>0;base=np.full(len(y),np.mean(yy));ba=float(balanced_accuracy_score(yy,prob>=.5));mc=float(matthews_corrcoef(yy,prob>=.5));brier=float(brier_score_loss(yy,prob));b0=float(brier_score_loss(yy,base));mae=float(np.mean(abs(y-med)));mae0=float(np.mean(abs(y)));coverage=float(np.mean((y>=lo)&(y<=hi)));rho=spearmanr(med,y).statistic;return {'n':len(y),'alphaIC':rs['ic'],'alphaSpread':rs['spread'],'balancedAccuracy':ba,'mcc':mc,'brierSkill':1-brier/b0 if b0 else 0.,'ece':ece(yy.astype(float),prob),'scenarioMAEImprove':1-mae/(mae0 or 1e-12),'scenarioRankIC':float(rho) if _finite(rho) else 0.,'coverage20_80':coverage}

def risk_status(f):
    weak=f['ret20']<0 or f['trend50']<0;daily=f['vol20']/math.sqrt(252);flags=[f['dd60']<=-.18,f['ret20']<=-.10,f['trend50']<=-.10,f['trend200']<=-.15,f['rsi14']<=.35,f['macdNorm']<=-.008,daily>=.04,f['ret1']<=-.04 and f['volumeZ']>=1.5];n=sum(flags);s=f['technical'];return ('RED' if s>=78 and weak and n>=3 else 'YELLOW' if s>=65 and weak and n>=2 else 'WATCH' if s>=50 and weak and n>=1 else 'GREEN'),n

def main():
    P,latest=build_panel();D=np.asarray([x['date'] for x in P]);dates=np.asarray(sorted(set(D)));X=np.asarray([[x.get(k,np.nan) for k in FEATURES] for x in P],float);out={'version':VERSION,'createdAt':datetime.now(timezone.utc).isoformat(),'featureNames':FEATURES,'universe':{'symbols':len(set(x['symbol'] for x in P)),'rows':len(P),'dates':len(dates),'start':str(dates[0]),'end':str(dates[-1])},'horizons':{},'governance':{'design':'direct T+1..T+5; model family selected only on chronological DEV; calibration on CAL; final metrics on sealed AUD','price':'Yahoo adjusted close is primary. Raw-price fallback is not used to manufacture corporate-action corrections.','marketPsychology':'breadth, dispersion/CSAD, risk breadth, volume breadth, turnover concentration and leadership are measured cross-sectionally','newsFlow':'news/event and foreign flow are separate evidence layers until their own PIT ablation gates pass','actionAuthority':'none'}}
    current={}
    for h in HORIZONS:
        y=np.asarray([x.get('y'+str(h),np.nan) for x in P],float);mr={d:float(np.nanmedian(y[D==d])) for d in dates};alpha=np.asarray([y[i]-mr.get(D[i],np.nan) for i in range(len(y))]);choice,cands=choose(X,y,alpha,D,dates,h);ci,cap,cdp=train_block(X,y,alpha,D,dates,h,CAL,choice);cal=buckets(y[ci],cdp,10);ai,aap,adp=train_block(X,y,alpha,D,dates,h,AUD,choice);A=audit(y[ai],alpha[ai],aap,adp,D[ai],cal)
        gates={'ranking':A['alphaIC']>.02 and A['alphaSpread']>.0015,'direction':A['balancedAccuracy']>.515 and A['mcc']>.02 and A['brierSkill']>-.03,'scenario':len(cal)>=7 and .50<=A['coverage20_80']<=.72 and A['scenarioRankIC']>.01}
        out['horizons'][str(h)]={'status':'PASS' if all(gates.values()) else 'REVIEW','choice':choice,'candidates':cands,'calibration':cal,'sealedAudit':A,'gates':gates}
        # Production fit uses all mature labels after the sealed methodology is fixed.
        ok=np.isfinite(y);pr=prep(X,ok);Z=apply(X,pr);rg=model(choice['reg'],'reg');cl=model(choice['cls'],'cls');rg.fit(Z[ok],alpha[ok]);cl.fit(Z[ok],y[ok]>0)
        for s,v in latest.items():
            if not v or not all(k in v['feature'] for k in CROSS):continue
            f=v['feature'];xx=np.asarray([[f.get(k,np.nan) for k in FEATURES]],float);zz=apply(xx,pr);ap=float(rg.predict(zz)[0]);dp=float(cl.predict_proba(zz)[0,1]);b=bfind(cal,dp)
            current.setdefault(s,{'symbol':s,'date':f['date'],'close':float(v['rows'][-1]['close']),'modelClose':float(v['rows'][-1]['modelClose']),'source':v['source'],'technical':float(f['technical']),'ret20':float(f['ret20']),'trend20':float(f['trend20']),'trend50':float(f['trend50']),'vol20':float(f['vol20']),'volumeZ':float(f['volumeZ']),'avgTurnover30':float(f.get('avgTurnover30',0.)),'market':{k:float(f[k]) for k in CROSS}});current[s].setdefault('horizons',{})[str(h)]={'alpha':ap,'rawDirectionScore':dp,'historicalUpRate':b['positiveRate'] if b else None,'medianReturn':b['medianReturn'] if b else None,'meanReturn':b['meanReturn'] if b else None,'q20':b['q20'] if b else None,'q80':b['q80'] if b else None,'n':b['n'] if b else 0,'status':out['horizons'][str(h)]['status']}
    for s,z in current.items():z['riskStatus'],z['stressCount']=risk_status(z|{'dd60':latest[s]['feature']['dd60'],'rsi14':latest[s]['feature']['rsi14'],'macdNorm':latest[s]['feature']['macdNorm'],'ret1':latest[s]['feature']['ret1'],'trend200':latest[s]['feature']['trend200']})
    out['promotion']={'status':'PASS' if sum(out['horizons'][str(h)]['status']=='PASS' for h in HORIZONS)>=4 else 'REVIEW','directHorizons':[h for h in HORIZONS if out['horizons'][str(h)]['status']=='PASS'],'exactTargetPrice':False,'scenarioDistribution':True}
    (ROOT/'data/forecast-model-v11.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');(ROOT/'data/forecast-current-v11.json').write_text(json.dumps({'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'symbols':current,'count':len(current)},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'version':VERSION,'promotion':out['promotion'],'universe':out['universe'],'current':len(current),'audit':{h:out['horizons'][str(h)]['sealedAudit'] for h in HORIZONS}},ensure_ascii=False))
if __name__=='__main__':main()
