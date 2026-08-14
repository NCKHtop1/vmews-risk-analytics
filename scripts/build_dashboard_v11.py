import json,math,os
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from forecast_v11_features import yahoo_adjusted
ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));VERSION='VMEWS-DASHBOARD-11.0.0'
def chart(s):
 try:r,_=yahoo_adjusted(s,'2y',12);return s,[{'date':x['date'],'close':x['modelClose'],'volume':x['volume']} for x in r[-160:]]
 except:return s,[]
def main():
 cur=json.loads((ROOT/'data/forecast-current-v11.json').read_text(encoding='utf-8'));model=json.loads((ROOT/'data/forecast-model-v11.json').read_text(encoding='utf-8'));syms=cur['symbols'];charts={}
 with ThreadPoolExecutor(max_workers=16) as ex:
  fs={ex.submit(chart,s):s for s in syms}
  for f in as_completed(fs):s,r=f.result();charts[s]=r
 alpha=[z['horizons']['5']['alpha'] for z in syms.values() if '5' in z.get('horizons',{}) and isinstance(z['horizons']['5'].get('alpha'),(int,float))];alo,ahi=(np.quantile(alpha,.1),np.quantile(alpha,.9)) if alpha else (-.01,.01)
 rows=[]
 for s,z in syms.items():
  h=z.get('horizons',{}).get('5',{});liq=float(z.get('avgTurnover30',0) or 0);liq=liq*1000 if z.get('modelClose',0)<10000 else liq;ar=float(h.get('alpha',0) or 0);rank=(ar-alo)/(ahi-alo) if ahi>alo else .5;p=float(h.get('historicalUpRate',.5) or .5);med=float(h.get('medianReturn',0) or 0);risk=float(z.get('technical',50) or 50);score=100*(.42*max(0,min(1,rank))+.28*max(0,min(1,(p-.35)/.3))+.18*max(0,min(1,(med+.02)/.04))+.12*(1-min(1,risk/100)))
  rows.append({'symbol':s,'score':score,'alpha5':ar,'upRate5':p,'median5':med,'risk':risk,'riskStatus':z.get('riskStatus','GREEN'),'liquidity30':liq,'date':z.get('date')})
 watch=[x for x in rows if x['riskStatus'] not in {'YELLOW','RED'} and x['liquidity30']>=500_000_000];watch.sort(key=lambda x:x['score'],reverse=True);yellow=sorted([x for x in rows if x['riskStatus']=='YELLOW'],key=lambda x:x['risk'],reverse=True);red=sorted([x for x in rows if x['riskStatus']=='RED'],key=lambda x:x['risk'],reverse=True)
 dates=[z.get('date') for z in syms.values() if z.get('date')];modal=max(set(dates),key=dates.count) if dates else None;market=next((z.get('market') for z in syms.values() if z.get('date')==modal and z.get('market')),{});out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'modelVersion':model['version'],'asOf':modal,'promotion':model['promotion'],'market':market,'symbols':syms,'charts':charts,'lists':{'watch':watch[:30],'yellow':yellow[:30],'red':red[:30]},'counts':{'symbols':len(syms),'chartSymbols':sum(bool(x) for x in charts.values()),'watchEligible':len(watch),'yellow':len(yellow),'red':len(red)}}
 (ROOT/'data/forecast-dashboard-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps(out['counts'],ensure_ascii=False))
if __name__=='__main__':main()
