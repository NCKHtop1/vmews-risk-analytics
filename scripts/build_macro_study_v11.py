import json,math,os
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import quote
from urllib.request import Request,urlopen
import numpy as np
ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));VERSION='VMEWS-MACRO-STUDY-11.0.0';H=(1,2,3,4,5);SPECS={'vix':'^VIX','usdVnd':'USDVND=X','dxy':'DX-Y.NYB','us10y':'^TNX','brent':'BZ=F'}
def fetch(sym,rg='10y'):
 for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
  try:
   u=f'https://{host}/v8/finance/chart/{quote(sym,safe="")}?range={rg}&interval=1d&includePrePost=false';p=json.loads(urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS-Macro/11'}),timeout=15).read().decode());z=(p.get('chart',{}).get('result') or [None])[0]
   if not z:continue
   ts=z.get('timestamp') or [];q=(z.get('indicators',{}).get('quote') or [{}])[0];out=[]
   for i,t in enumerate(ts):
    try:c=float((q.get('close') or [])[i]);d=datetime.fromtimestamp(t,timezone.utc).date().isoformat()
    except:continue
    if math.isfinite(c) and c>0:out.append((d,c))
   if len(out)>100:return dict(out),[x[0] for x in out]
  except:pass
 return {},[]
def ret_before(vals,dates,d,k=20):
 ds=[x for x in dates if x<d]
 if len(ds)<k+1:return None
 a,b=ds[-1],ds[-k-1];return math.log(vals[a]/vals[b])
def zscore(a,x):
 v=np.asarray(a[-252:],float)
 if len(v)<30:return 0.
 return float((x-v.mean())/(v.std(ddof=1) or 1))
def stat(a):
 x=np.asarray(a,float)
 return {'n':len(x),'mean':float(x.mean()),'median':float(np.median(x)),'positiveRate':float(np.mean(x>0)),'q20':float(np.quantile(x,.2)),'q80':float(np.quantile(x,.8))} if len(x) else None
def main():
 m={k:fetch(s) for k,s in SPECS.items()};vni,vd=fetch('^VNINDEX')
 if not vni:vni,vd=fetch('^VNINDEX.VN')
 if len(vd)<800:raise RuntimeError(f'VNINDEX macro benchmark unavailable: {len(vd)} rows')
 rows=[];hist=[]
 for i,d in enumerate(vd):
  if i<260:continue
  f={};ok=True
  for k,(vals,ds) in m.items():
   r=ret_before(vals,ds,d,20)
   if r is None:ok=False;break
   f[k+'Ret20']=r
  if not ok:continue
  score=.32*f['vixRet20']+.18*f['dxyRet20']+.18*f['us10yRet20']+.18*f['usdVndRet20']+.14*abs(f['brentRet20']);hist.append(score);zs=zscore(hist,score);state='STRESS' if zs>=.8 else 'SUPPORTIVE' if zs<=-.8 else 'NEUTRAL';z={'date':d,'score':score,'z':zs,'state':state,**f}
  for h in H:
   if i+h<len(vd):z['r'+str(h)]=math.log(vni[vd[i+h]]/vni[d])
  rows.append(z)
 groups={}
 for st in ('SUPPORTIVE','NEUTRAL','STRESS'):
  a=[x for x in rows if x['state']==st];groups[st]={'n':len(a),'horizons':{str(h):stat([x['r'+str(h)] for x in a if 'r'+str(h) in x]) for h in H}}
 cur=rows[-1] if rows else None;out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'pointInTimeRule':'For VN date T, all cross-market macro closes are restricted to dates strictly earlier than T.','features':list(SPECS),'current':cur,'groups':groups,'observations':len(rows)};(ROOT/'data/macro-study-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps({'observations':len(rows),'current':cur,'groups':{k:v['n'] for k,v in groups.items()}},ensure_ascii=False))
if __name__=='__main__':main()
