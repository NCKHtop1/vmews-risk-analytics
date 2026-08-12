import importlib.util
import json
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'deep-alerts'
OUT.mkdir(parents=True,exist_ok=True)

def load_module(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

radar=load_module('vmews_cache_radar',ROOT/'api'/'radar.py')
scan=json.loads((ROOT/'data'/'market-scan.json').read_text(encoding='utf-8'))
try: market_payload=json.loads((ROOT/'data'/'market-context.json').read_text(encoding='utf-8'))
except Exception: market_payload={}
market=market_payload.get('market') or {'score':50,'available':False,'reason':'Static VNINDEX context unavailable'}

# Every visible RED/YELLOW alert must have a deep-history path. This keeps
# market-wide triage and single-name research as one connected workflow.
selected=[]; seen=set()
for x in list(scan.get('redList') or []) + list(scan.get('yellowList') or []):
    s=x.get('symbol')
    if s and s not in seen:
        seen.add(s); selected.append(x)

def build(meta):
    symbol=meta['symbol']
    rows,audit=radar.load_rows(symbol)
    cur,hz,fs=radar.core.technical_state(rows)
    mods={
      'technical':{'score':cur['technical'],'available':True,'drivers':cur.get('technicalDrivers',{})},
      'analog':hz['20'],
      'market':market,
      'macro':{'score':50,'available':False,'note':'Excluded from static CDN fallback cache.'},
      'sentiment':{'score':50,'available':False,'note':'Merged from research-news snapshot in browser when available.'},
      'fundamental':{'score':50,'available':False,'note':'Unavailable in static CDN fallback cache; excluded from context score.'},
    }
    score,conf=radar.aggregate(mods)
    phase,color,state=radar.classify(score,cur,conf)
    cutoff_i=cur['i']
    payload={
      'version':'VMEWS-DEEP-ALERT-CACHE-1.1.0','mode':'detail','symbol':symbol,
      'name':meta.get('name') or radar.core.NAMES.get(symbol,symbol),
      'request':{'from':None,'to':None,'asOf':None},'fetchedAt':datetime.now(timezone.utc).isoformat(),
      'modelAsOf':cur['date'],'quote':None,'score':score,'confidence':conf,'phase':phase,'color':color,'state':state,
      'effectiveScore':score,'liveOverlay':{'available':False,'score':score,'intradayReturn':None},
      'reasons':radar.reasons(mods),'current':cur,'horizons':hz,'modules':mods,'news':[],'fundamentals':{},
      'history':rows[-1800:],
      'scoreHistory':[{'date':f['date'],'technical':f['technical']} for f in fs if f['i']<=cutoff_i],
      'crashReplay':radar.replay(rows,fs,cutoff_i),'dataQuality':radar.pct_quality(rows,audit),
      'warnings':['Static CDN deep-history fallback used; current macro/fundamental context is excluded unless separately available.'],
      'audit':[audit],
      'source':{'price':f"{audit.get('source')} · {audit.get('provider')}",'quote':'Not used','market':'Static VMEWS VNINDEX context snapshot','fundamental':'Excluded in static fallback','sentiment':'Browser research-news merge when available','macro':'Excluded in static fallback'}
    }
    return symbol,payload

for p in OUT.glob('*.json'):
    if p.name!='manifest.json':
        try:p.unlink()
        except:pass

ok={}; errors=[]
with ThreadPoolExecutor(max_workers=6) as ex:
    fut={ex.submit(build,m):m for m in selected}
    for f in as_completed(fut):
        meta=fut[f]
        try:
            symbol,payload=f.result()
            (OUT/f'{symbol}.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
            ok[symbol]={'rows':payload['dataQuality']['rows'],'modelAsOf':payload['modelAsOf'],'source':payload['audit'][0].get('source')}
        except Exception as e:
            errors.append({'symbol':meta.get('symbol'),'error':str(e)[:400]})

red_symbols=[x.get('symbol') for x in scan.get('redList') or [] if x.get('symbol')]
yellow_symbols=[x.get('symbol') for x in scan.get('yellowList') or [] if x.get('symbol')]
alert_symbols=red_symbols+yellow_symbols
missing_red=[s for s in red_symbols if s not in ok]
missing_alerts=[s for s in alert_symbols if s not in ok]
manifest={'version':'VMEWS-DEEP-ALERT-CACHE-1.1.0','generatedAt':datetime.now(timezone.utc).isoformat(),'marketModelDate':scan.get('modelDate'),'requested':len(selected),'cached':len(ok),'symbols':ok,'errors':errors,'redSymbols':red_symbols,'yellowSymbols':yellow_symbols,'missingRed':missing_red,'missingAlerts':missing_alerts,'alertCoverageRatio':len(ok)/len(alert_symbols) if alert_symbols else 1.0}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
if missing_alerts: raise RuntimeError(f'Missing RED/YELLOW deep cache: {missing_alerts}')
