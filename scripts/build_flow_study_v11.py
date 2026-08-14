import json,math,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import numpy as np
from forecast_v11_features import yahoo_adjusted
ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));VERSION='VMEWS-FLOW-STUDY-11.0.0';H=(1,2,3,4,5)
def state(z):return 'STRONG_BUY' if z>=.75 else 'BUY' if z>=.2 else 'STRONG_SELL' if z<=-.75 else 'SELL' if z<=-.2 else 'NEUTRAL'
def price(s):
 try:r,_=yahoo_adjusted(s,'10y',15);return s,{x['date']:x['modelClose'] for x in r},[x['date'] for x in r]
 except:return s,{},[]
def stat(a):
 x=np.asarray([z for z in a if isinstance(z,(int,float)) and math.isfinite(z)],float)
 if not len(x):return None
 return {'n':len(x),'meanAR':float(x.mean()),'medianAR':float(np.median(x)),'positiveRate':float(np.mean(x>0)),'q20':float(np.quantile(x,.2)),'q80':float(np.quantile(x,.8))}
def main():
 flow=json.loads((ROOT/'data/flow-v11.json').read_text(encoding='utf-8'));syms=[s for s,r in flow['symbols'].items() if len(r)>=60];prices={}
 with ThreadPoolExecutor(max_workers=12) as ex:
  fs={ex.submit(price,s):s for s in syms}
  for f in as_completed(fs):s,p,d=f.result();prices[s]=(p,d)
 obs=[]
 for s in syms:
  rows=flow['symbols'][s];p,dates=prices.get(s,({},[]));idx={d:i for i,d in enumerate(dates)}
  for j in range(60,len(rows),5):
   r=rows[j];d=r['date'];i=idx.get(d)
   if i is None:continue
   z={'symbol':s,'date':d}
   for typ in ('foreign','prop'):
    v=np.asarray([float(x.get(typ+'NetValue',0) or 0) for x in rows[max(0,j-59):j+1]],float);sd=float(v.std(ddof=1)) if len(v)>2 else 0.;zz=float((v[-1]-v.mean())/(sd or 1));n5=float(sum(v[-5:]));n20=float(sum(v[-20:]));gross=sum(float(x.get(typ+'BuyValue',0) or 0)+float(x.get(typ+'SellValue',0) or 0) for x in rows[max(0,j-19):j+1]);z[typ+'Z']=zz;z[typ+'State']=state(zz);z[typ+'Net5']=n5;z[typ+'Net20']=n20;z[typ+'Ratio20']=n20/gross if gross else 0.
   for h in H:
    if i+h<len(dates) and dates[i+h] in p:z['r'+str(h)]=math.log(p[dates[i+h]]/p[d])
   obs.append(z)
 # cross-sectional market median per date for abnormal returns
 med={}
 for h in H:
  for d in set(x['date'] for x in obs):
   a=[x.get('r'+str(h)) for x in obs if x['date']==d and isinstance(x.get('r'+str(h)),(int,float))]
   if len(a)>=8:med[(d,h)]=float(np.median(a))
 for x in obs:
  for h in H:
   if isinstance(x.get('r'+str(h)),(int,float)) and (x['date'],h) in med:x['ar'+str(h)]=x['r'+str(h)]-med[(x['date'],h)]
 groups={}
 for typ in ('foreign','prop'):
  groups[typ]={}
  for st in ('STRONG_SELL','SELL','NEUTRAL','BUY','STRONG_BUY'):
   a=[x for x in obs if x.get(typ+'State')==st];groups[typ][st]={'n':len(a),'horizons':{str(h):stat([x.get('ar'+str(h)) for x in a]) for h in H}}
 cur={}
 for s,c in flow.get('current',{}).items():
  z={}
  for typ in ('foreign','prop'):
   st=state(float(c.get(typ+'Z60',0) or 0));z[typ]={'state':st,'z60':c.get(typ+'Z60'),'net1':c.get(typ+'Net1'),'net5':c.get(typ+'Net5'),'net20':c.get(typ+'Net20'),'netRatio20':c.get(typ+'NetRatio20'),'history':groups[typ].get(st)}
  if 'foreignRoom' in c:z['foreign']['room']=c['foreignRoom']
  cur[s]=z
 out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'sourceVersion':flow['version'],'sampledObservations':len(obs),'groups':groups,'current':cur,'governance':{'role':'separate historically tested evidence layer; it changes confidence only when its historical state has adequate observations','minimumStateN':250}}
 (ROOT/'data/flow-study-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps({'symbols':len(cur),'observations':len(obs),'foreign':{k:v['n'] for k,v in groups['foreign'].items()},'prop':{k:v['n'] for k,v in groups['prop'].items()}},ensure_ascii=False))
if __name__=='__main__':main()
