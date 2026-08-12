"""Independent robustness audit for the frozen VMEWS pooled HOSE champion.

The model specification is NOT changed by this script. It reconstructs the
same panel and sealed test used by VMEWS-POOLED-HOSE-1.2.0, then asks whether
the predictive ranking survives dependence-aware resampling and sub-period
checks. Absolute probability calibration is audited separately. These
post-freeze diagnostics may only downgrade evidence; they are not a tuning set.
"""
import importlib.util
import json
import math
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'pooled-hose'
VERSION='VMEWS-POOLED-ROBUSTNESS-1.1.0'
SEED=20260812
REPS=200


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

V2=load('vmews_pool_v2_audit',ROOT/'scripts'/'train_pooled_hose_model_v2.py')
B=V2.B


def ap(y,p):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    return float(average_precision_score(y,p)) if y.sum() and y.sum()<len(y) else None

def auc(y,p):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    return float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None

def brier_skill(y,p):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float);base=float(y.mean())
    br=float(brier_score_loss(y,p));bb=float(brier_score_loss(y,np.full(len(y),base)))
    return float(1-br/bb) if bb>0 else None

def metrics(frame,p):
    y=frame['crash'].to_numpy(dtype=int);base=float(y.mean())
    return {'n':int(len(y)),'symbols':int(frame.symbol.nunique()),'events':int(y.sum()),'baseRate':base,
            'prAuc':ap(y,p),'rocAuc':auc(y,p),'brierSkill':brier_skill(y,p)}

def moving_date_block_ci(frame,p,block_dates=4,reps=REPS):
    frame=frame.reset_index(drop=True);p=np.asarray(p,dtype=float)
    dates=sorted(frame['date'].drop_duplicates().tolist());by={d:frame.index[frame.date==d].to_numpy() for d in dates}
    if len(dates)<20:return None
    rng=np.random.default_rng(SEED+11);vals=[];starts=np.arange(0,max(1,len(dates)-block_dates+1));blocks=math.ceil(len(dates)/block_dates)
    for _ in range(reps):
        chosen=[]
        for st in rng.choice(starts,size=blocks,replace=True):chosen.extend(dates[int(st):int(st)+block_dates])
        chosen=chosen[:len(dates)];ids=np.concatenate([by[d] for d in chosen]);y=frame.iloc[ids].crash.to_numpy(dtype=int)
        if 0<y.sum()<len(y):vals.append(float(average_precision_score(y,p[ids])))
    if not vals:return None
    return {'low':float(np.quantile(vals,.025)),'high':float(np.quantile(vals,.975)),'median':float(np.median(vals)),
            'reps':len(vals),'blockPanelDates':block_dates,'tradingSessionsEquivalent':block_dates*B.SAMPLE_STEP,
            'unit':'moving contiguous sampled-date blocks; each date retains its full cross-section'}

def symbol_cluster_ci(frame,p,reps=REPS):
    frame=frame.reset_index(drop=True);p=np.asarray(p,dtype=float);syms=sorted(frame.symbol.unique());by={s:frame.index[frame.symbol==s].to_numpy() for s in syms}
    rng=np.random.default_rng(SEED+29);vals=[]
    for _ in range(reps):
        chosen=rng.choice(syms,size=len(syms),replace=True);ids=np.concatenate([by[s] for s in chosen]);y=frame.iloc[ids].crash.to_numpy(dtype=int)
        if 0<y.sum()<len(y):vals.append(float(average_precision_score(y,p[ids])))
    if not vals:return None
    return {'low':float(np.quantile(vals,.025)),'high':float(np.quantile(vals,.975)),'median':float(np.median(vals)),
            'reps':len(vals),'unit':'security-cluster bootstrap; complete time history retained per sampled security'}

def calibration_bins(y,p,bins=10):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float);order=np.argsort(p);parts=np.array_split(order,bins);out=[];ece=0.0
    for j,ids in enumerate(parts,1):
        if not len(ids):continue
        mp=float(p[ids].mean());obs=float(y[ids].mean());w=len(ids)/len(y);ece+=w*abs(mp-obs)
        out.append({'bin':j,'n':int(len(ids)),'meanProbability':mp,'observedRate':obs,'absoluteGap':abs(mp-obs)})
    return {'ece':float(ece),'bins':out}

def risk_buckets(y,p,buckets=10):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float);base=float(y.mean());order=np.argsort(p);parts=np.array_split(order,buckets);out=[]
    for j,ids in enumerate(parts,1):
        if not len(ids):continue
        rate=float(y[ids].mean());out.append({'bucket':j,'percentileFrom':(j-1)/buckets,'percentileTo':j/buckets,
            'n':int(len(ids)),'events':int(y[ids].sum()),'eventRate':rate,'liftVsBase':float(rate/base) if base>0 else None,
            'minCalibratedScore':float(p[ids].min()),'maxCalibratedScore':float(p[ids].max())})
    return out

def main():
    validation=json.load(open(OUT/'validation.json',encoding='utf-8'))
    assert validation['version']=='VMEWS-POOLED-HOSE-1.2.0',validation['version']
    assert validation['champion']=='logistic_l2','Audit is frozen to the promoted champion; update only through a new model version.'

    universe=B.hose_universe();hist={};errors=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        fut={ex.submit(B.fetch_one,m):m for m in universe}
        for f in as_completed(fut):
            sym,rows,_,err=f.result()
            if rows:hist[sym]=rows
            else:errors.append({'symbol':sym,'error':err})
    if len(hist)/len(universe)<.90:raise RuntimeError(f'History coverage too low for audit: {len(hist)}/{len(universe)}')
    panel_rows=[]
    for sym,rows in hist.items():
        samples,_,_=B.build_symbol_panel(sym,rows);panel_rows.extend(samples)
    panel=B.add_cross_section(pd.DataFrame(panel_rows),labelled=True)
    dates=sorted(panel.date.drop_duplicates().tolist());sealed_idx=int(len(dates)*.85)
    tr,ca,te,split=V2.sealed_split(panel,dates,sealed_idx)
    m,model,cal,p=V2.eval_split('logistic_l2',tr,ca,te)

    ref=validation['sealedTest']
    if abs(m['prAuc']-ref['prAuc'])>.01 or abs(m['baseRate']-ref['baseRate'])>.01:
        raise RuntimeError(f"Audit reconstruction drifted: PR {m['prAuc']} vs {ref['prAuc']}; base {m['baseRate']} vs {ref['baseRate']}")

    mb=moving_date_block_ci(te,p,block_dates=max(2,V2.PURGE_DATES));sc=symbol_cluster_ci(te,p)
    unique=sorted(te.date.unique());cut=unique[len(unique)//2];mask1=(te.date<cut).to_numpy();mask2=~mask1
    halves=[metrics(te.loc[mask1],p[mask1]),metrics(te.loc[mask2],p[mask2])]
    halves[0]['period']={'from':str(te.loc[mask1].date.min().date()),'to':str(te.loc[mask1].date.max().date())}
    halves[1]['period']={'from':str(te.loc[mask2].date.min().date()),'to':str(te.loc[mask2].date.max().date())}
    caldiag=calibration_bins(te.crash.to_numpy(dtype=int),p,10);buckets=risk_buckets(te.crash.to_numpy(dtype=int),p,10)

    base=m['baseRate'];rank_reasons=[]
    if not mb or mb['low']<=base:rank_reasons.append('moving-date-block PR-AUC lower 95% bound is not above sealed base rate')
    if not sc or sc['low']<=base:rank_reasons.append('security-cluster PR-AUC lower 95% bound is not above sealed base rate')
    for i,h in enumerate(halves,1):
        if h['prAuc'] is None or h['prAuc']<=h['baseRate']:rank_reasons.append(f'sealed half {i} PR-AUC does not exceed its own base rate')
        if h['rocAuc'] is None or h['rocAuc']<.55:rank_reasons.append(f'sealed half {i} ROC-AUC < 0.55')
    rank_robust=len(rank_reasons)==0

    prob_reasons=[]
    if m.get('brierSkill') is None or m['brierSkill']<=0:prob_reasons.append('full sealed Brier skill is not positive')
    for i,h in enumerate(halves,1):
        if h.get('brierSkill') is None or h['brierSkill']<=0:prob_reasons.append(f'sealed half {i} Brier skill is not positive')
    if caldiag['ece']>.05:prob_reasons.append('sealed equal-count-bin expected calibration error exceeds 5%')
    absolute_prob=rank_robust and not prob_reasons

    rank_grade='MODERATE' if rank_robust else 'LIMITED'
    if rank_robust and m['prAuc']>=2*base and mb['low']>=1.25*base and sc['low']>=1.25*base:rank_grade='STRONG_RANKING'
    payload={'version':VERSION,'modelVersion':validation['version'],'generatedAt':datetime.now(timezone.utc).isoformat(),
             'purpose':'Independent post-freeze robustness audit; model and threshold are not retuned.',
             'historyCoverage':len(hist)/len(universe),'sealedReconstruction':m,'movingDateBlockPrAucCI95':mb,
             'securityClusterPrAucCI95':sc,'sealedSubperiods':halves,'calibrationDiagnostics':caldiag,'riskBuckets':buckets,
             'rankRobustnessGate':{'passed':rank_robust,'grade':rank_grade,'reasons':rank_reasons,
                'rule':'Both dependence-aware PR-AUC lower bounds > sealed base; each sealed half PR-AUC > own base and ROC-AUC >=0.55.'},
             'absoluteProbabilityGate':{'passed':absolute_prob,'status':'USABLE' if absolute_prob else 'WITHHELD_CALIBRATION_STABILITY',
                'reasons':prob_reasons,'rule':'Rank robustness plus positive Brier skill in the full sealed block and each sealed half; ECE <=5%.'},
             'notes':['Moving-date blocks preserve approximately one 20-session label horizon of serial dependence.',
                      'Security-cluster bootstrap preserves each sampled security time history.',
                      'Risk buckets report empirical sealed event frequency by pooled risk rank and are not point forecasts.',
                      'Post-freeze diagnostics may downgrade ranking/probability evidence, never retune the existing sealed model.'],
             'fetchErrors':errors[:30]}
    (OUT/'robustness.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'rankRobustnessPassed':rank_robust,'rankGrade':rank_grade,'absoluteProbabilityPassed':absolute_prob,
        'probabilityReasons':prob_reasons,'movingDateCI':mb,'symbolCI':sc,'subperiods':halves,'ece':caldiag['ece'],
        'topRiskBucket':buckets[-1] if buckets else None,'rankReasons':rank_reasons},ensure_ascii=False,indent=2))
    if not rank_robust:raise RuntimeError('Frozen pooled rank robustness audit did not pass: '+' | '.join(rank_reasons))

if __name__=='__main__':main()
