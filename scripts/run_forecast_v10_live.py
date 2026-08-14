import json, math, hashlib
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy.stats import spearmanr
from forecast_v4_features import stock_features

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'data/forecast-model-v10.json'
OUT=ROOT/'data/forecast-live-v10'
SNAP=OUT/'snapshots'
VERSION='VMEWS-FORECAST-LIVE-10.0.0'
H=('3','5')

def load(p,default=None):
    try:return json.loads(Path(p).read_text(encoding='utf-8'))
    except:return {} if default is None else default

def dump(p,z):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(z,ensure_ascii=False,indent=2),encoding='utf-8')

def finite(x):
    try:return math.isfinite(float(x))
    except:return False

def lin(m,x):return float(m.get('intercept') or 0)+sum(float(a or 0)*float(b) for a,b in zip(m.get('coef') or [],x))
def sigmoid(x):return 1/(1+math.exp(-max(-35,min(35,float(x)))))
def bucket(bs,x):
    for b in bs or []:
        if x>=b['lo'] and x<=b['hi']:return b
    if not bs:return None
    return bs[0] if x<bs[0]['lo'] else bs[-1]

def predict(model,d):
    rows,fs=stock_features(d.get('history') or []);f=fs[-1] if fs else None
    if not f:return None
    out={}
    for h in H:
        z=model['horizons'][h];v=[]
        for i,k in enumerate(model['featureNames']):
            x=f.get(k,z['impute'][i]);x=float(x) if finite(x) else float(z['impute'][i]);sd=float(z['std'][i]);v.append((x-float(z['mean'][i]))/(sd if abs(sd)>1e-12 else 1.0))
        a=lin(z['alphaModel'],v);ds=sigmoid(lin(z['directionModel'],v));ab=bucket(z.get('alphaCalibrationBuckets'),a);db=bucket(z.get('directionCalibrationBuckets'),ds)
        out[h]={'alpha':a,'directionScore':ds,'alphaBucket':{k:ab.get(k) for k in ('n','meanReturn','positiveRate','q20','q80')} if ab else None,'directionBucket':{k:db.get(k) for k in ('n','meanReturn','positiveRate','q20','q80')} if db else None}
    return {'date':f['date'],'close':float(rows[f['i']]['close']),'forecast':out}

def core_hash(z):
    q={k:v for k,v in z.items() if k not in {'createdAt','snapshotHash'}}
    return hashlib.sha256(json.dumps(q,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def realized(history,origin,h):
    rows=[x for x in history if x.get('date') and finite(x.get('close')) and float(x.get('close'))>0];dates=[str(x['date'])[:10] for x in rows]
    try:i=dates.index(origin)
    except ValueError:return None
    j=i+int(h)
    if j>=len(rows):return None
    return math.log(float(rows[j]['close'])/float(rows[i]['close']))

def evaluate(current):
    origins=[];summary={}
    for p in sorted(SNAP.glob('*.json')):
        s=load(p,{});origin=s.get('asOf');row={'asOf':origin,'horizons':{}}
        for h in H:
            obs=[]
            for pr in s.get('predictions') or []:
                d=current.get(pr.get('symbol'))
                if not d:continue
                r=realized(d.get('history') or [],origin,h)
                if r is None:continue
                f=(pr.get('forecast') or {}).get(h) or {};obs.append((float(f.get('alpha') or 0),float(f.get('directionScore') or .5),r))
            if len(obs)>=20:
                ret=np.array([x[2] for x in obs]);market=float(np.median(ret));actual=ret-market;alpha=np.array([x[0] for x in obs]);score=np.array([x[1] for x in obs]);ic=spearmanr(actual,alpha).statistic;ic=float(ic) if finite(ic) else None
                row['horizons'][h]={'n':len(obs),'marketReturn':market,'alphaIC':ic,'directionHitRate':float(np.mean((score>=.5)==(ret>0)))}
            else:row['horizons'][h]={'n':len(obs),'state':'IMMATURE'}
        origins.append(row)
    for h in H:
        mature=[x['horizons'][h] for x in origins if x['horizons'][h].get('n',0)>=20];summary[h]={'matureOrigins':len(mature),'nPredictions':sum(x['n'] for x in mature),'alphaIC':float(np.mean([x['alphaIC'] for x in mature if x.get('alphaIC') is not None])) if any(x.get('alphaIC') is not None for x in mature) else None,'directionHitRate':float(np.mean([x['directionHitRate'] for x in mature])) if mature else None,'evidenceState':'MATURE' if len(mature)>=20 else 'EARLY' if len(mature)>=5 else 'IMMATURE'}
    return {'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'method':'Immutable completed-EOD prequential test-then-score.','summary':summary,'origins':origins,'governance':{'automaticPromotion':False,'minimumMatureOrigins':20}}

def main():
    model=load(MODEL,{});assert model.get('version')=='VMEWS-FORECAST-10.1.0',model.get('version');allowed=set(model.get('universe',{}).get('symbolList') or []);current={};pred=[]
    for p in sorted((ROOT/'data/hose-fallbacks').glob('*.json')):
        if p.name=='manifest.json':continue
        d=load(p,{});s=str(d.get('symbol') or p.stem).upper()
        if allowed and s not in allowed:continue
        if len(d.get('history') or [])<520:continue
        current[s]=d
        try:
            z=predict(model,d)
            if z:pred.append({'symbol':s,**z})
        except:pass
    if len(pred)<250:raise RuntimeError(f'V10 live coverage below floor: {len(pred)}')
    dates=[x['date'] for x in pred];asof=max(set(dates),key=dates.count);pred=sorted([x for x in pred if x['date']==asof],key=lambda x:x['symbol'])
    if len(pred)<200:raise RuntimeError(f'V10 aligned EOD coverage below floor: {len(pred)}')
    SNAP.mkdir(parents=True,exist_ok=True);p=SNAP/f'{asof}.json';z={'version':VERSION,'createdAt':datetime.now(timezone.utc).isoformat(),'asOf':asof,'modelVersion':model['version'],'timeBasis':'COMPLETED_EOD_ONLY','symbols':len(pred),'predictions':pred};z['snapshotHash']=core_hash(z)
    status='CREATED'
    if p.exists():
        old=load(p,{})
        if old.get('snapshotHash')==z['snapshotHash']:status='EXISTING_IDENTICAL';z=old
        else:status='REVISION_DETECTED_PRESERVED_FIRST_ARCHIVE';z=old
    else:dump(p,z)
    bad=[]
    for x in SNAP.glob('*.json'):
        a=load(x,{});h=a.get('snapshotHash')
        if not h or core_hash(a)!=h:bad.append(x.name)
    ev=evaluate(current);dump(OUT/'evaluation.json',ev);manifest={'version':VERSION,'count':len(list(SNAP.glob('*.json'))),'latest':asof,'files':[x.name for x in sorted(SNAP.glob('*.json'))]};dump(OUT/'manifest.json',manifest);integrity={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS' if not bad else 'FAIL','asOf':asof,'archiveStatus':status,'symbols':len(pred),'modelVersion':model['version'],'timeBasis':'COMPLETED_EOD_ONLY','snapshotHash':z.get('snapshotHash'),'badHashes':bad};dump(OUT/'integrity.json',integrity);print(json.dumps({'integrity':integrity,'evaluation':ev['summary']},ensure_ascii=False,indent=2));assert not bad,bad
if __name__=='__main__':main()
