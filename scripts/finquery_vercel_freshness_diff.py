#!/usr/bin/env python3
"""Check market & company-news snapshot freshness, including cache-busting retries."""
import concurrent.futures, datetime, hashlib, json, os, sys, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
U1='https://nckhtop1.github.io/vmews-risk-analytics/financial-report'
U2='https://finquery-web.vercel.app'
PATHS=[
'/market/news-latest.json','/market/news-company-latest.json',
'/market/news-daily-brief.json','/market/news-viewpoint-sentiment.json',
'/market/quotes.json','/market/technical-signals.json','/market/strategy-indicators.json',
'/market/watch-today.json','/market/risk-monitor.json','/market/macro.json',
'/market/drivers.json','/market/universe.json','/market/intraday-status.json',
'/data/manifest.json','/data/companies.json','/data/broker-research.json',
'/data/corporate-events.json','/data/business-plans.json',
]
def one(host,p,token):
  q=('?cache_probe='+token) if token else ''
  url=host+p+q
  try:
    with urlopen(Request(url,headers={'Cache-Control':'no-cache','Pragma':'no-cache','User-Agent':'FinQuery-FreshnessAudit/1'}),timeout=20) as r:
      b=r.read()
      headers=r.headers
      try:d=json.loads(b)
      except:d={}
      return {'code':r.status,'bytes':len(b),'sha':hashlib.sha256(b).hexdigest(),
        'cache_control':headers.get('Cache-Control'),'age':headers.get('Age'),
        'vercel_cache':headers.get('X-Vercel-Cache'),'etag':headers.get('ETag'),
        'checkedAt':d.get('checkedAt') if isinstance(d,dict) else None,
        'sourceTime':d.get('latestSourceTime',d.get('sourceTime')) if isinstance(d,dict) else None,
        'generatedAt':d.get('generatedAt') if isinstance(d,dict) else None,
        'status':d.get('status') if isinstance(d,dict) else None,
        'count':len(d.get('items') or []) if isinstance(d,dict) and 'items' in d else None,
        'riskScore':d.get('overall',{}).get('score') if isinstance(d,dict) and isinstance(d.get('overall'),dict) else None,
        'revision':d.get('code') if isinstance(d,dict) else None,
        'data':d}
  except HTTPError as e:
    return {'code':e.code,'error':str(e)}
  except Exception as e:return{'code':0,'error':str(e)}
def when(s):
  try:return datetime.datetime.fromisoformat(str(s).replace('Z','+00:00')).timestamp()
  except:return None
def main():
  report=[]
  for p in PATHS:
    token=str(int(time.time()*1000000))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
      a,b,ac,bc=list(ex.map(lambda x:one(*x),[(U1,p,''),(U2,p,''),(U1,p,token),(U2,p,token)]))
    t1=when(ac.get('checkedAt') or ac.get('generatedAt'))
    t2=when(bc.get('checkedAt') or bc.get('generatedAt'))
    delta=round(t1-t2,1) if t1 and t2 else None
    risk_a=ac.get('riskScore');risk_b=bc.get('riskScore')
    sourceMatch=ac.get('sourceTime')==bc.get('sourceTime')
    changed=[]
    if ac.get('code')==bc.get('code')==200 and ac.get('sha')!=bc.get('sha'):
      da=ac.get('data') or {};db=bc.get('data') or {}
      changed=sorted([k for k in set(da)|set(db) if da.get(k)!=db.get(k)]) if isinstance(da,dict) and isinstance(db,dict) else ['non-dict']
    item={'path':p,'github':a,'vercel':b,'github_bust':ac,'vercel_bust':bc,
          'lagSeconds':delta,'sameBytesBare':a.get('sha')==b.get('sha') and a.get('code')==200,
          'sameBytesBusted':ac.get('sha')==bc.get('sha') and ac.get('code')==200,
          'sourceMatches':sourceMatch,'differentTopFields':changed[:20]}
    for k in ('github','vercel','github_bust','vercel_bust'):
      item[k]={key:value for key,value in item[k].items() if key!='data'}
    report.append(item)
    print("FRESHNESS "+json.dumps(item,ensure_ascii=False)[:1900],flush=True)
  failures=[]
  for x in report:
    if x['path'] in ('/market/news-latest.json','/market/news-company-latest.json'):
      if x['lagSeconds'] is not None and x['lagSeconds']>15*60:
        failures.append('Vercel lag > 15 min for '+x['path']+': '+str(x['lagSeconds'])+'s')
  out={'paths':len(report),'failures':failures,'report':report}
  with open('finquery-freshness-diff.json','w',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
  print("FRESHNESS_SUMMARY "+json.dumps({'paths':len(report),'failures':failures,
      'mismatched_busted':[x['path'] for x in report if x['github_bust']['code']==x['vercel_bust']['code']==200 and not x['sameBytesBusted']]},ensure_ascii=False),flush=True)
  return 1 if failures else 0
if __name__=='__main__':sys.exit(main())
