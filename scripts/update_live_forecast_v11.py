import json,hashlib,math,os
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from scipy.stats import spearmanr
ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));BASE=ROOT/'data/forecast-live-v11';ORI=BASE/'origins';OUT=BASE/'outcomes';ORI.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True);VERSION='VMEWS-LIVE-FORECAST-11.0.0'
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def hashv(x):return hashlib.sha256(canon(x)).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
 d=load(ROOT/'data/forecast-dashboard-v11.json');asof=d['asOf'];model=d['modelVersion'];pred={}
 for s,z in d['symbols'].items():
  hs={}
  for h,x in z.get('horizons',{}).items():
   if h in {'1','2','3','4','5'}:hs[h]={k:x.get(k) for k in ('alpha','historicalUpRate','medianReturn','meanReturn','q20','q80','n','status')}
  if len(hs)==5:pred[s]={'close':z.get('modelClose',z.get('close')),'riskStatus':z.get('riskStatus'),'technical':z.get('technical'),'horizons':hs}
 payload={'version':VERSION,'asOf':asof,'modelVersion':model,'createdAt':datetime.now(timezone.utc).isoformat(),'predictions':pred};payload['forecastHash']=hashv({'asOf':asof,'modelVersion':model,'predictions':pred});op=ORI/f'{asof}.json'
 if not op.exists():op.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 else:
  old=load(op);assert old.get('forecastHash')==hashv({'asOf':old['asOf'],'modelVersion':old['modelVersion'],'predictions':old['predictions']}),'immutable origin hash changed'
 # Mature existing origins from current chart histories without modifying the origin forecasts.
 summary={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'currentAsOf':asof,'modelVersion':model,'origins':0,'badHashes':[],'horizons':{str(h):{'n':0,'directionHits':[],'forecastMedian':[],'realized':[],'alpha':[]} for h in range(1,6)}}
 for p in sorted(ORI.glob('*.json')):
  o=load(p);summary['origins']+=1;hh=hashv({'asOf':o['asOf'],'modelVersion':o['modelVersion'],'predictions':o['predictions']})
  if hh!=o.get('forecastHash'):summary['badHashes'].append(p.name);continue
  outcomes={'origin':o['asOf'],'forecastHash':o['forecastHash'],'evaluatedAt':asof,'symbols':{}}
  for s,pr in o['predictions'].items():
   chart=d.get('charts',{}).get(s) or [];ix=next((i for i,x in enumerate(chart) if x.get('date')==o['asOf']),None)
   if ix is None:continue
   base=float(pr['close']);oz={}
   for h in range(1,6):
    if ix+h>=len(chart):continue
    actual=math.log(float(chart[ix+h]['close'])/base);fc=pr['horizons'][str(h)];med=fc.get('medianReturn');prob=fc.get('historicalUpRate');alpha=fc.get('alpha');oz[str(h)]={'actual':actual,'date':chart[ix+h]['date'],'directionHit':bool((actual>0)==(float(prob)>=.5)) if prob is not None else None,'inside20_80':bool(float(fc['q20'])<=actual<=float(fc['q80'])) if fc.get('q20') is not None and fc.get('q80') is not None else None};q=summary['horizons'][str(h)];q['n']+=1;q['realized'].append(actual);q['forecastMedian'].append(float(med));q['directionHits'].append(1 if oz[str(h)]['directionHit'] else 0);q['alpha'].append(float(alpha))
   if oz:outcomes['symbols'][s]=oz
  (OUT/f'{o["asOf"]}.json').write_text(json.dumps(outcomes,ensure_ascii=False,indent=2),encoding='utf-8')
 for h,q in summary['horizons'].items():
  n=q['n'];real=np.asarray(q.pop('realized'),float);med=np.asarray(q.pop('forecastMedian'),float);dh=q.pop('directionHits');alpha=np.asarray(q.pop('alpha'),float);q['directionAccuracy']=float(np.mean(dh)) if dh else None;q['medianMAE']=float(np.mean(abs(real-med))) if n else None;q['zeroMAE']=float(np.mean(abs(real))) if n else None;q['medianMAEImprove']=1-q['medianMAE']/q['zeroMAE'] if n and q['zeroMAE'] else None;rho=spearmanr(alpha,real).statistic if n>=20 else None;q['alphaRankIC']=float(rho) if rho is not None and math.isfinite(float(rho)) else None;q['evidence']='MATURE' if n>=500 else 'ACCUMULATING'
 summary['status']='PASS' if not summary['badHashes'] else 'FAIL';(BASE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
