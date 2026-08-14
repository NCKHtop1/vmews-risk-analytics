import warnings,math,json
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from scipy.stats import spearmanr,ConstantInputWarning
from sklearn.metrics import balanced_accuracy_score,matthews_corrcoef,brier_score_loss
import train_forecast_v11 as m

warnings.filterwarnings('ignore',category=ConstantInputWarning)
warnings.filterwarnings('ignore',message='All-NaN slice encountered')
ROOT=Path('.')
CACHE={}

def safe_rank_stats(y,p,D):
    ics=[];sp=[]
    for d in sorted(set(D)):
        q=np.where(D==d)[0]
        if len(q)<12:continue
        yy=np.asarray(y[q],float);pp=np.asarray(p[q],float)
        if np.nanstd(yy)>1e-14 and np.nanstd(pp)>1e-14:
            z=spearmanr(yy,pp).statistic
            if z is not None and math.isfinite(float(z)):ics.append(float(z))
        order=np.argsort(pp);k=max(1,len(q)//5);sp.append(float(np.mean(yy[order[-k:]])-np.mean(yy[order[:k]])))
    return {'ic':float(np.mean(ics)) if ics else 0.,'spread':float(np.mean(sp)) if sp else 0.}

def save_market_benchmark(latest):
    """Persist a daily HOSE cross-sectional median-return index from the exact adjusted
    price histories already accepted by the numerical panel. This avoids a second
    network dependency and keeps the macro outcome benchmark contemporaneous/PIT."""
    by={}
    symbols=0
    for v in latest.values():
        if not v or not v.get('rows'):continue
        rows=v['rows'];symbols+=1;prev=None
        for r in rows:
            try:d=str(r.get('date'))[:10];c=float(r.get('modelClose',r.get('close')))
            except:continue
            if prev is not None and prev[1]>0 and c>0:
                rr=math.log(c/prev[1])
                if math.isfinite(rr) and abs(rr)<.35:by.setdefault(d,[]).append(rr)
            prev=(d,c)
    days=sorted(d for d,a in by.items() if len(a)>=30);level=1000.;series=[]
    for d in days:
        r=float(np.median(by[d]));level*=math.exp(r);series.append({'date':d,'return':r,'level':level,'n':len(by[d])})
    out={'version':'VMEWS-HOSE-MARKET-BENCHMARK-11.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'method':'Daily cross-sectional median log return from the same adjusted HOSE histories accepted by the V11 panel; minimum 30 securities per date.','symbols':symbols,'observations':len(series),'series':series}
    (ROOT/'data/market-benchmark-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    if len(series)<1500:raise RuntimeError(f'V11 market benchmark too short: {len(series)}')
    print(json.dumps({'marketBenchmark':'PASS','symbols':symbols,'observations':len(series),'start':series[0]['date'],'end':series[-1]['date']},ensure_ascii=False))

def broad_current_panel():
    P,latest=orig_build()
    save_market_benchmark(latest)
    # A stale symbol must never receive a market state observed after its own EOD.
    # Reuse the most recent sampled cross-sectional state on or before that symbol date.
    cross_by_date={}
    for x in P:
        if all(k in x for k in m.CROSS):
            cross_by_date.setdefault(str(x['date']),{k:float(x[k]) for k in m.CROSS})
    cross_dates=sorted(cross_by_date)
    for v in latest.values():
        if not v:continue
        f=v.get('feature') or {}
        if all(k in f for k in m.CROSS):
            f['crossContextDate']=str(f.get('date'))
            continue
        d=str(f.get('date') or '')
        eligible=[x for x in cross_dates if x<=d]
        if not eligible:continue
        use=eligible[-1]
        f.update(cross_by_date[use]);f['crossContextDate']=use
    CACHE['panel']=(P,latest)
    return P,latest

def ece(y,p,bins=10):
    q=np.linspace(0,1,bins+1);s=0.;n=len(y)
    for a,b in zip(q[:-1],q[1:]):
        z=(p>=a)&(p<(b if b<1 else 1.000001))
        if z.any():s+=z.sum()*abs(float(np.mean(y[z]))-float(np.mean(p[z])))
    return s/max(1,n)

def repaired_audit(y,alpha,ap,dp,D,dir_cal,scenario_cal):
    rs=safe_rank_stats(alpha,ap,D)
    md=[m.bfind(dir_cal,x) for x in dp];ms=[m.bfind(scenario_cal,x) for x in ap]
    prob=np.asarray([x['positiveRate'] for x in md],float);med=np.asarray([x['medianReturn'] for x in ms],float);lo=np.asarray([x['q20'] for x in ms],float);hi=np.asarray([x['q80'] for x in ms],float)
    yy=y>0;base=np.full(len(y),np.mean(yy));ba=float(balanced_accuracy_score(yy,prob>=.5));mc=float(matthews_corrcoef(yy,prob>=.5));br=float(brier_score_loss(yy,prob));b0=float(brier_score_loss(yy,base));mae=float(np.mean(abs(y-med)));mae0=float(np.mean(abs(y)));rho=spearmanr(med,y).statistic
    return {'n':len(y),'alphaIC':rs['ic'],'alphaSpread':rs['spread'],'balancedAccuracy':ba,'mcc':mc,'brierSkill':1-br/b0 if b0 else 0.,'ece':ece(yy.astype(float),prob),'scenarioMAEImprove':1-mae/(mae0 or 1e-12),'scenarioRankIC':float(rho) if rho is not None and math.isfinite(float(rho)) else 0.,'coverage20_80':float(np.mean((y>=lo)&(y<=hi)))}

def repair_calibration():
    P,latest=CACHE['panel'];D=np.asarray([x['date'] for x in P]);dates=np.asarray(sorted(set(D)));X=np.asarray([[x.get(k,np.nan) for k in m.FEATURES] for x in P],float)
    model=json.loads((ROOT/'data/forecast-model-v11.json').read_text(encoding='utf-8'));cur=json.loads((ROOT/'data/forecast-current-v11.json').read_text(encoding='utf-8'))
    for h in m.HORIZONS:
        key=str(h);z=model['horizons'][key];y=np.asarray([x.get('y'+key,np.nan) for x in P],float);mr={d:float(np.nanmedian(y[D==d])) for d in dates};alpha=np.asarray([y[i]-mr.get(D[i],np.nan) for i in range(len(y))]);choice=z['choice']
        ci,cap,cdp=m.train_block(X,y,alpha,D,dates,h,m.CAL,choice);dir_cal=z.get('calibration') or m.buckets(y[ci],cdp,10);scenario_cal=m.buckets(y[ci],cap,10)
        ai,aap,adp=m.train_block(X,y,alpha,D,dates,h,m.AUD,choice);A=repaired_audit(y[ai],alpha[ai],aap,adp,D[ai],dir_cal,scenario_cal)
        gates={'ranking':A['alphaIC']>.02 and A['alphaSpread']>.0015,'direction':A['balancedAccuracy']>.515 and A['mcc']>.02 and A['brierSkill']>-.03,'scenario':len(scenario_cal)>=7 and .45<=A['coverage20_80']<=.75 and A['scenarioRankIC']>.01}
        z['directionCalibration']=dir_cal;z['calibration']=scenario_cal;z['sealedAudit']=A;z['gates']=gates;z['status']='PASS' if all(gates.values()) else ('SCENARIO_PASS' if gates['ranking'] and gates['scenario'] else 'REVIEW')
        for s,c in cur['symbols'].items():
            hh=c.get('horizons',{}).get(key)
            if not hh:continue
            sb=m.bfind(scenario_cal,float(hh['alpha']));db=m.bfind(dir_cal,float(hh.get('rawDirectionScore',.5)))
            if sb:
                hh['historicalUpRate']=(db['positiveRate'] if gates['direction'] and db else sb['positiveRate']);hh['medianReturn']=sb['medianReturn'];hh['meanReturn']=sb['meanReturn'];hh['q20']=sb['q20'];hh['q80']=sb['q80'];hh['n']=sb['n'];hh['status']=z['status'];hh['directionValidated']=bool(gates['direction'])
    scenario_h=[h for h in m.HORIZONS if model['horizons'][str(h)]['gates']['ranking'] and model['horizons'][str(h)]['gates']['scenario']]
    direction_h=[h for h in m.HORIZONS if model['horizons'][str(h)]['gates']['direction']]
    model['promotion']={'status':'PASS' if len(scenario_h)>=4 and 3 in scenario_h and 5 in scenario_h else 'REVIEW','directHorizons':scenario_h,'directionHorizons':direction_h,'exactTargetPrice':False,'scenarioDistribution':True}
    model['governance']['magnitudeCalibration']='Absolute T+1..T+5 scenario distributions are calibrated on predicted cross-sectional alpha in CAL and audited only in the sealed AUD block.'
    model['governance']['currentCrossSection']='Each current symbol uses a same-day cross-section when available; otherwise the latest sampled cross-sectional state not later than that symbol EOD.'
    cur['generatedAt']=datetime.now(timezone.utc).isoformat();cur['count']=len(cur['symbols'])
    (ROOT/'data/forecast-model-v11.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8');(ROOT/'data/forecast-current-v11.json').write_text(json.dumps(cur,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'calibrationRepair':'PASS','current':cur['count'],'directHorizons':scenario_h,'directionHorizons':direction_h,'audit':{h:model['horizons'][str(h)]['sealedAudit'] for h in m.HORIZONS}},ensure_ascii=False))

orig_build=m.build_panel
m.rank_stats=safe_rank_stats
m._orig_risk=m.risk_status
m.risk_status=lambda f:(lambda z:(z[0],int(z[1])))(m._orig_risk(f))
m.build_panel=broad_current_panel
m.main()
repair_calibration()
