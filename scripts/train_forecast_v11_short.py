import json, os, math, importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import train_forecast_v10 as v
from forecast_v11_short_features import features,FEATURES,MIN_ROWS

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));MANIFEST=ROOT/'data/hose-fallbacks/manifest.json';OUT=ROOT/'data/forecast-model-short-v11.json'
def core():
 p=ROOT/'api/stocks.py';s=importlib.util.spec_from_file_location('short_core',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
CORE=core()
def one(sym):
 p=ROOT/f'data/hose-fallbacks/{sym}.json';raw=None
 if p.exists():
  try:raw=json.loads(p.read_text(encoding='utf-8')).get('history') or None
  except:pass
 if not raw:
  try:raw,_,_=CORE.yahoo_chart(sym,'10y',7)
  except:return sym,[]
 try:
  rows,fs=features(raw)
  if len(rows)<MIN_ROWS or len(fs)<15:return sym,[]
  out=[]
  for f in fs:
   i=f['i'];z={'symbol':sym,**f,'technical':f['technicalShort']}
   for h in v.HORIZONS:z['y'+str(h)]=math.log(rows[i+h]['modelClose']/rows[i]['modelClose']) if i+h<len(rows) else np.nan
   out.append(z)
  return sym,out
 except:return sym,[]
def short_panel(root='.'):
 m=json.loads(MANIFEST.read_text(encoding='utf-8'));items=[s for s,r in (m.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=MIN_ROWS];P=[];used=[]
 with ThreadPoolExecutor(max_workers=10) as ex:
  fs={ex.submit(one,s):s for s in items}
  for f in as_completed(fs):
   s,a=f.result()
   if a:P.extend(a);used.append(s)
 dates=sorted(set(x['date'] for x in P));keep=set(dates[::5]);P=[x for x in P if x['date'] in keep];by={}
 for x in P:by.setdefault(x['date'],[]).append(x)
 for a in by.values():
  mr=float(np.median([x['ret20'] for x in a]));rs=float(np.mean([x['technicalShort']>=50 for x in a]))
  for x in a:x['marketRet20']=mr;x['riskShare']=rs
 print(json.dumps({'requested':len(items),'loadedSymbols':len(set(used)),'rows':len(P),'dates':len(keep)},ensure_ascii=False))
 if len(set(used))<350 or len(P)<100000:raise RuntimeError('short-history panel below production floor')
 return P,len(set(used))
def main():
 orig=(ROOT/'data/forecast-model-v10.json').read_bytes() if (ROOT/'data/forecast-model-v10.json').exists() else None
 try:
  v.VERSION='VMEWS-FORECAST-SHORT-11.0.0';v.FEATURES=list(FEATURES);v.build_panel=short_panel;v.train(str(ROOT));p=ROOT/'data/forecast-model-v10.json';z=json.loads(p.read_text(encoding='utf-8'));z['version']='VMEWS-FORECAST-SHORT-11.0.0';z['minSessions']=MIN_ROWS;z['featureNames']=FEATURES;z['governance'].update({'purpose':'Fallback for currently listed HOSE stocks with less than 520 sessions. It does not pretend SMA200/long-history state exists.','trainingUniverse':'Current HOSE resolver universe with >=80 completed sessions.','featureParity':'STRICT short-history feature set, deployable after 80 sessions.','riskCompatibility':'Uses a short-window deterioration proxy; canonical VMEWS YELLOW/RED remains separate when canonical risk is available.','actionAuthority':'none','exactMagnitude':False});OUT.write_text(json.dumps(z,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'version':z['version'],'minSessions':MIN_ROWS,'universe':z['universe'],'promotion':z['promotion']},ensure_ascii=False,indent=2))
 finally:
  if orig is not None:(ROOT/'data/forecast-model-v10.json').write_bytes(orig)
if __name__=='__main__':main()
