#!/usr/bin/env python3
"""Real Chrome emulation of client networks blocking GitHub domains, browsing Vercel only."""
import json, os, re, shutil, sys, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

url="https://finquery-web.vercel.app/?symbol=FPT&mode=year#market"
opt=Options()
for arg in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--window-size=1440,1200']:
    opt.add_argument(arg)
opt.set_capability("goog:loggingPrefs",{"browser":"ALL"})
driver=webdriver.Chrome(service=Service(shutil.which('chromedriver')) if shutil.which('chromedriver') else Service(),options=opt)
driver.set_page_load_timeout(80);driver.set_script_timeout(30)
blocked=['*github.io/*','*github.com/*','*githubusercontent.com/*','*githubraw.com/*']
results={}
phase='opening'
try:
    driver.execute_cdp_cmd("Network.enable",{})
    driver.execute_cdp_cmd("Network.setBlockedURLs",{"urls":blocked})
    driver.get(url)
    driver.execute_script("""
      sessionStorage.setItem('finquery-site-access','1');
      sessionStorage.setItem('finquery-technical-access','1');
      sessionStorage.setItem('finquery-macro-access','1');
    """)
    driver.refresh()
    wait=WebDriverWait(driver,65)
    phase='waiting market source failover'
    wait.until(lambda d:d.execute_script("return Boolean(window.FinancialMarket?.context?.()?.quoteBundleSourceTime)"))
    phase='waiting chart'
    wait.until(lambda d:d.execute_script("return document.querySelectorAll('#price-chart canvas').length>0"))
    phase='waiting strategy data'
    wait.until(lambda d:d.execute_script("return Object.keys(window.FinStrategyBuilder?.context?.()?.snapshot?.symbols||{}).length>=100"))
    phase='opening risk'
    driver.execute_script("window.FinPlatformViews.openRisk()")
    wait.until(lambda d:d.execute_script("return Number.isFinite(Number(window.FinRiskMonitor?.context?.()?.overall?.score))"))
    phase='opening strategy'
    driver.execute_script("window.FinPlatformViews.openStrategy()")
    wait.until(lambda d:d.execute_script("return Boolean(document.querySelector('#sai-open-symbol'))"))
    phase='testing news and forecast'
    time.sleep(4)
    results=driver.execute_script("""
      const market=window.FinancialMarket?.context?.()||{};
      const risk=window.FinRiskMonitor?.context?.()||{};
      const strategy=window.FinStrategyBuilder?.context?.()||{};
      const text=id=>(document.getElementById(id)?.textContent||'').trim();
      return {
        hostname:location.hostname,
        siteLocked:document.body.classList.contains('site-locked'),
        title:document.title,
        priceLabel:text('quote-price'),
        quoteTime:text('quote-time'),
        marketSymbol:market.symbol,
        marketSourceTime:market.quoteBundleSourceTime,
        newsCheckedAt:market.newsCheckedAt,
        companyNewsCount:(market.news||[]).length,
        marketNewsCount:(market.marketNews||[]).length,
        riskStatus:risk.status,
        riskScore:risk.overall?.score,
        riskAligned:String(risk.sourceTime||'')===String(market.quoteBundleSourceTime||''),
        strategySymbols:Object.keys(strategy.snapshot?.symbols||{}).length,
        chartCanvases:document.querySelectorAll('#price-chart canvas').length,
        reportLoaded:Boolean(window.FinancialReportContext?.raw?.()),
        forecastLink:document.getElementById('forecast-link')?.href||'',
        blockedForecastLink:(document.getElementById('forecast-link')?.hostname||'').endsWith('github.io'),
        macroSources:Object.keys(window.FinMacro?.context?.()?.datasets||{}).length
      }
    """)
except Exception as e:
    results={"error":repr(e),"phase":phase}
    try:
        results['diagnostic']=driver.execute_script("""
          return {title:document.title,locked:document.body.classList.contains('site-locked'),
            market:window.FinancialMarket?.context?.()?.symbol,
            quoteTime:document.getElementById('quote-time')?.textContent,
            price:document.getElementById('quote-price')?.textContent,
            status:document.getElementById('risk-source-status')?.textContent,
            marketTime:window.FinancialMarket?.context?.()?.quoteBundleSourceTime,
            count:Object.keys(window.FinStrategyBuilder?.context?.()?.snapshot?.symbols||{}).length,
          };
        """)
    except:pass
finally:
    try:results['browserSevere']=[str(x.get('message'))[:190] for x in driver.get_log('browser') if x.get('level')=='SEVERE'][:10]
    except:pass
    driver.quit()
print('BLOCKED_GITHUB_BROWSER '+json.dumps(results,ensure_ascii=False),flush=True)
with open('finquery-bank-network-audit.json','w',encoding='utf-8') as f:json.dump(results,f,ensure_ascii=False,indent=2)
checks={
'finquery loads': 'FinQuery' in results.get('title',''),
'client access': results.get('siteLocked') is False,
'FPT UI price': bool(re.search(r'[1-9][0-9.,]*',results.get('priceLabel',''))),
'market source failover': bool(results.get('marketSourceTime')),
'chart rendered': (results.get('chartCanvases') or 0)>0,
'strategy 100+':(results.get('strategySymbols') or 0)>=100,
'risk score': isinstance(results.get('riskScore'),(int,float)) and 0<=results.get('riskScore',-1)<=100,
'risk aligned':results.get('riskAligned') is True,
'financial report loaded':results.get('reportLoaded') is True,
'macro data loaded':(results.get('macroSources') or 0)>=3,
'forecast link stays on allowed host':results.get('blockedForecastLink') is False,
}
for name,passed in checks.items():print(('PASS ' if passed else 'FAIL ')+name,flush=True)
print('BLOCKED_GITHUB_SUMMARY '+str(sum(checks.values()))+'/'+str(len(checks))+' pass',flush=True)
sys.exit(0 if all(checks.values()) else 1)
