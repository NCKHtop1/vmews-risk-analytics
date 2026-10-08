#!/usr/bin/env python3
"""Check Forecast root data, then real browser rendering with GitHub blocked."""
import hashlib,json,re,shutil,sys,time
from urllib.request import urlopen
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
ROOT='https://nckhtop1.github.io/vmews-risk-analytics'
SITE='https://finquery-web.vercel.app'
data_files=[
'forecast-dashboard-v12.json','phase-gates-v12.json','forecast-model-v12.json',
'data-audit-v12.json','forecast-market-v13.json','forecast-backtest-v12.json',
'forecast-session-v21.json','community-intelligence-live-v19.json',
'forecast-current-v12.json','event-intelligence-v12.json'
]
fail=[]
for x in data_files:
  try:
    with urlopen(ROOT+'/data/'+x,timeout=20) as r:a=r.read()
    with urlopen(SITE+'/data/'+x,timeout=20) as r:b=r.read()
    same=hashlib.sha256(a).digest()==hashlib.sha256(b).digest()
    print('FORECAST_DATA '+x+' '+('EXACT' if same else 'MISMATCH')+' bytes='+str(len(a))+'/'+str(len(b)),flush=True)
    if not same:fail.append('data mismatch '+x)
  except Exception as e:
    print('FORECAST_DATA '+x+' ERROR '+repr(e),flush=True)
    fail.append('data fetch '+x)
opt=Options()
for arg in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--window-size=1366,1000']:
  opt.add_argument(arg)
opt.set_capability("goog:loggingPrefs",{"browser":"ALL"})
d=webdriver.Chrome(service=Service(shutil.which("chromedriver")) if shutil.which("chromedriver") else Service(),options=opt)
d.set_page_load_timeout(80)
out={}
try:
  d.execute_cdp_cmd('Network.enable',{})
  d.execute_cdp_cmd('Network.setBlockedURLs',{'urls':['*github.io/*','*github.com/*','*githubusercontent.com/*','*githubraw.com/*']})
  d.get(SITE+'/forecast-final.html?symbol=FPT')
  wait=WebDriverWait(d,65)
  wait.until(lambda z:z.execute_script("return (document.querySelector('#close')?.textContent||'').match(/[1-9][0-9.,]*/);"))
  time.sleep(4)
  out=d.execute_script("""
    const text=id=>(document.getElementById(id)?.textContent||'').trim();
    const cur=(document.getElementById('symbol')?.value||'').trim();
    const cards=document.getElementById('forecastCards');
    return {title:document.title,hostname:location.hostname,selectedSymbol:cur,
      snapshotDate:text('snapshotDate'),status:text('status'),close:text('close'),
      quoteAsOf:text('quoteAsOf'),t1:text('t1'),t3:text('t3'),t5:text('t5'),
      forecastCardsLength:(cards?.textContent||'').trim().length,
      chartElement:Boolean(document.getElementById('chart')),
      backtestLength:text('backtest').length,
      risk:text('risk'),
      errorIndicators:[...document.querySelectorAll('[role=alert]')].map(x=>x.textContent.trim().slice(0,90)).slice(0,5)};
  """)
except Exception as e:
  out={"error":repr(e)}
  try:out["diagnostic"]=d.execute_script("""
    return {close:document.getElementById('close')?.textContent,status:document.getElementById('status')?.textContent,
      symbol:document.getElementById('symbol')?.value,
      forecast:document.getElementById('forecastCards')?.textContent?.slice(0,200)}
  """)
  except:pass
finally:
  try:out['browserSevere']=[x.get('message','')[:190] for x in d.get_log('browser') if x.get('level')=='SEVERE'][:12]
  except:pass
  d.quit()
print('FORECAST_BLOCKED_GITHUB '+json.dumps(out,ensure_ascii=False)[:5500],flush=True)
if out.get('error'):fail.append('Forecast UI fails while Github blocked')
if out.get('forecastCardsLength',0)<30:fail.append('Forecast card content not rendered')
if out.get('close','') in ('','—','–'):fail.append('Forecast current/last price missing')
with open('finquery-forecast-smoke.json','w',encoding='utf-8') as f:json.dump({"dataFiles":data_files,"browser":out,"failures":fail},f,ensure_ascii=False,indent=2)
print('FORECAST_SUMMARY '+str(len(fail))+' failures '+json.dumps(fail,ensure_ascii=False),flush=True)
sys.exit(1 if fail else 0)
