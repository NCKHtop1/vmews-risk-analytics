#!/usr/bin/env python3
"""Independent real Chromium browser audit, same navigation on GitHub Pages & Vercel."""
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

SITES={
    "github":"https://nckhtop1.github.io/vmews-risk-analytics/financial-report/",
    "vercel":"https://finquery-web.vercel.app/",
}
MODULES=[
    "FinQueryAI","FinancialMarket","FinancialReportContext",
    "FinTechnicalScanner","FinStrategyBuilder","FinStrategyIntelligence",
    "FinResearchAgent","FinRiskMonitor","FinSectionCollapse","FinMacro"
]
def valid_js():
    return """
      const symbol=window.FinancialMarket?.context?.()?.symbol || '';
      const quote=window.FinancialMarket?.context?.()?.quote || null;
      const scan=window.FinTechnicalScanner?.context?.() || {};
      const strategy=window.FinStrategyBuilder?.context?.() || {};
      const macro=window.FinMacro?.context?.() || {};
      const risk=window.FinRiskMonitor?.context?.() || {};
      const features=Object.fromEntries(
        ["FinQueryAI","FinancialMarket","FinancialReportContext",
         "FinTechnicalScanner","FinStrategyBuilder","FinStrategyIntelligence",
         "FinResearchAgent","FinRiskMonitor","FinSectionCollapse","FinMacro"]
        .map(k=>[k,Boolean(window[k])]));
      const tx=id=>(document.getElementById(id)?.textContent||'').trim();
      return {
        title:document.title,base:location.origin,path:location.pathname,
        hostname:location.hostname,hosting:document.documentElement.dataset.hosting,
        locked:document.body.classList.contains('site-locked'),
        features,
        symbol,quote:quote ? {price:Number(quote.price),changePct:Number(quote.changePct)} : null,
        sourceTime:window.FinancialMarket?.context?.()?.quoteBundleSourceTime || '',
        reportLoaded:Boolean(window.FinancialReportContext?.raw?.()),
        scannerSymbol:scan?.current?.symbol || '',
        scannerCount:Object.keys(scan?.snapshot?.symbols||{}).length,
        strategyCount:Object.keys(strategy?.snapshot?.symbols||{}).length,
        strategyConditions:strategy?.strategy?.conditions?.length||0,
        riskStatus:risk.status||'',riskSourceTime:risk.sourceTime||'',
        riskScore:risk.overall?.score ?? null,
        macroSources:Object.keys(macro.datasets||{}).length,
        priceLabel:tx('quote-price'),quoteTime:tx('quote-time'),
        riskStatusLabel:tx('risk-source-status'),
        chartCanvas:document.querySelectorAll('#price-chart canvas').length,
        topWatch:tx('today-watch-label'),
        forecastLink:document.getElementById('forecast-link')?.href||'',
        headerH1:document.querySelector('.intro h1')?.textContent.trim()||'',
        missingElements:['market','risk-monitor','strategy-builder',
                         'investment-ideas','research-ai','macro']
                        .filter(x=>!document.getElementById(x))
      };
    """

def visit(label,url):
    opts=Options()
    for arg in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--window-size=1440,1200']:
        opts.add_argument(arg)
    opts.set_capability("goog:loggingPrefs",{"browser":"ALL"})
    service=Service(shutil.which("chromedriver")) if shutil.which("chromedriver") else Service()
    driver=webdriver.Chrome(service=service,options=opts)
    driver.set_page_load_timeout(70)
    driver.set_script_timeout(30)
    checks=[]
    errors=[]
    snapshots={}
    phase='loading'
    def check(name,predicate,error=None):
        try:
            ok=bool(predicate() if callable(predicate) else predicate)
            checks.append({"name":name,"ok":ok,"details":error if not ok else None})
        except Exception as e:
            checks.append({"name":name,"ok":False,"details":str(e)[:350]})
    try:
        phase='opening URL'
        driver.get(url+'?symbol=FPT&mode=year#market')
        driver.execute_script("""
            sessionStorage.setItem('finquery-site-access','1');
            sessionStorage.setItem('finquery-technical-access','1');
            sessionStorage.setItem('finquery-macro-access','1');
        """)
        driver.refresh()
        wait=WebDriverWait(driver,45)
        phase='waiting for market modules'
        wait.until(lambda d:d.execute_script("return window.FinancialMarket&&window.FinPlatformViews&&window.FinRiskMonitor;"))
        # A previous-session close can correctly be unavailable as a LIVE quote after midnight.
        # Browser parity must still verify price label and timestamp rather than requiring LIVE 24/7.
        phase='waiting for rendered chart'
        wait.until(lambda d:d.execute_script("return Boolean(document.querySelector('#price-chart canvas'));"))
        phase='waiting for strategy snapshot'
        wait.until(lambda d:d.execute_script("return Boolean(window.FinStrategyBuilder?.context?.()?.snapshot?.symbols);"))
        phase='waiting for scanner'
        wait.until(lambda d:d.execute_script("return Boolean(window.FinTechnicalScanner?.context?.()?.current);"))
        time.sleep(2)
        snapshots['initial']=driver.execute_script(valid_js())
        check("FinQuery correct entry", "FinQuery" in snapshots['initial']['title'] and "VMEWS" not in snapshots['initial']['title'])
        check("all critical JS modules initialized",all(snapshots['initial']['features'].values()),snapshots['initial']['features'])
        check("site access restored using authorized smoke session flags",not snapshots['initial']['locked'])
        check("last known FPT price rendered",bool(re.search(r'[1-9][0-9.,]*',snapshots['initial']['priceLabel'])),snapshots['initial']['priceLabel'])
        check("price chart rendered",snapshots['initial']['chartCanvas']>0)
        check("scanner selected FPT",snapshots['initial']['scannerSymbol']=='FPT')
        check("strategy data loaded",snapshots['initial']['strategyCount']>=100, str(snapshots['initial']['strategyCount']))
        check("macro sources >=3",snapshots['initial']['macroSources']>=3,str(snapshots['initial']['macroSources']))
        check("main views exist",not snapshots['initial']['missingElements'],snapshots['initial']['missingElements'])
        check("hosting original Pages build",snapshots['initial']['hosting']=='pages',snapshots['initial']['hosting'])
        phase='opening Risk view'
        driver.execute_script("window.FinPlatformViews.openRisk();")
        wait.until(lambda d:d.execute_script("return document.getElementById('risk-monitor')?.hidden===false;"))
        wait.until(lambda d:d.execute_script("return Boolean(window.FinRiskMonitor?.context?.()?.overall?.score >= 0);"))
        snapshots['risk']=driver.execute_script(valid_js())
        check("Risk view opens and has computed score",snapshots['risk']['riskScore'] is not None,snapshots['risk']['riskScore'])
        check("Risk source aligned with quote snapshot",
              not snapshots['risk']['riskSourceTime'] or
              snapshots['risk']['riskSourceTime']==snapshots['risk']['sourceTime'],
              str(snapshots['risk']['riskSourceTime'])+"/"+str(snapshots['risk']['sourceTime']))
        phase='opening Strategy view'
        driver.execute_script("window.FinPlatformViews.openStrategy();")
        wait.until(lambda d:d.execute_script("return document.getElementById('strategy-builder')?.hidden===false;"))
        wait.until(lambda d:d.execute_script("return Boolean(document.querySelector('#sai-open-symbol'));"))
        check("Strategy panel shows real rows",bool(driver.execute_script("""
            return (document.querySelector('#sai-investment-view')?.textContent||'').trim().length>50;
        """)))
        driver.execute_script("window.FinStrategyIntelligence.selectSymbol('HCM');")
        wait.until(lambda d:d.execute_script("return (document.querySelector('#sai-investment-view h3')?.textContent||'').includes('HCM');"))
        snapshots['strategy']=driver.execute_script(valid_js())
        check("Strategy HCM selection", "HCM" in (driver.execute_script("return document.querySelector('#sai-investment-view h3')?.textContent||''")))
        phase='click Strategy -> Chart'
        driver.find_element('id','sai-open-symbol').click()
        wait.until(lambda d:d.execute_script("return window.FinancialMarket?.context?.()?.symbol==='HCM' && document.querySelector('#price-chart canvas');"))
        snapshots['chart_link']=driver.execute_script(valid_js())
        check("Strategy action opens correct HCM chart",snapshots['chart_link']['symbol']=='HCM',snapshots['chart_link']['symbol'])
        driver.execute_script("window.FinancialMarket.openChart('FPT');")
        wait.until(lambda d:d.execute_script("return window.FinancialMarket?.context?.()?.symbol==='FPT';"))
        driver.execute_script("window.FinPlatformViews.openAnalysis();")
        snapshots['final']=driver.execute_script(valid_js())
        check("Analysis view restores FPT chart",snapshots['final']['symbol']=='FPT' and snapshots['final']['chartCanvas']>0)
        check("Financial report loaded",snapshots['final']['reportLoaded'])
        phase='completed'
        errors=[{"level":x.get("level"),"message":x.get("message","")[:230]}
               for x in driver.get_log("browser") if x.get("level")=="SEVERE"]
    except Exception as e:
        checks.append({"name":"BROWSER RUN FINISHED phase="+phase,"ok":False,"details":repr(e)[:1000]})
        try:snapshots['on_error']=driver.execute_script(valid_js())
        except Exception:pass
        try:errors=[{"level":x.get("level"),"message":x.get("message","")[:230]} for x in driver.get_log("browser") if x.get("level")=="SEVERE"]
        except Exception:pass
    finally:
        driver.quit()
    result={"url":url,"checks":checks,"errors":errors,"snapshots":snapshots}
    print(label.upper()+" BROWSER",json.dumps({"checkResults":[x['name']+":"+("PASS" if x['ok'] else "FAIL "+str(x.get('details'))) for x in checks],"severeCount":len(errors),"severeSample":errors[:5],"initial":snapshots.get("initial"),"risk":snapshots.get("risk"),"chart":snapshots.get("chart_link"),"onError":snapshots.get("on_error")},ensure_ascii=False)[:16000],flush=True)
    return result

def main():
    results={k:visit(k,u) for k,u in SITES.items()}
    failures=[]
    for k,res in results.items():
        for x in res["checks"]:
            if not x["ok"]:failures.append(k+" / "+x['name']+": "+str(x.get("details"))[:300])
    baseline=results['github'].get('snapshots') or {}
    target=results['vercel'].get('snapshots') or {}
    discrepancies=[]
    for step in ['initial','risk','strategy','chart_link','final']:
        a=baseline.get(step,{});b=target.get(step,{})
        keys=['hosting','locked','symbol','quote','sourceTime','reportLoaded','scannerSymbol',
              'strategyCount','macroSources','riskScore','chartCanvas','riskStatusLabel','riskSourceTime','missingElements']
        for key in keys:
            if key in a and key in b and a[key]!=b[key]:
                discrepancies.append({"step":step,"field":key,"github":a[key],"vercel":b[key]})
    for d in discrepancies:
        print("PARITY_DIFFERENCE "+json.dumps(d,ensure_ascii=False),flush=True)
        if d['field'] in ('hosting','locked','symbol','reportLoaded','scannerSymbol','strategyCount','macroSources','riskScore','chartCanvas','missingElements','quote'):
            failures.append("Parity browser mismatch: "+d["step"]+" / "+d["field"])
    reports={"checkedAt":datetime.utcnow().isoformat()+"Z","results":results,"discrepancies":discrepancies,"failures":failures}
    with open("finquery-browser-audit.json","w",encoding="utf-8") as f:json.dump(reports,f,ensure_ascii=False,indent=2)
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("### FinQuery Browser parity (real Chrome)\n\n")
            for name,rr in results.items():f.write(name+": "+str(sum(bool(c["ok"]) for c in rr["checks"]))+"/"+str(len(rr["checks"]))+" checks passed\n\n")
            f.write("Parity differences: "+str(len(discrepancies))+"; failures: "+str(len(failures))+"\n\n")
            for line in failures:f.write("- FAIL "+line+"\n")
    print("BROWSER_SUMMARY "+json.dumps({"checks":{k:(sum(c['ok'] for c in v['checks']),len(v['checks'])) for k,v in results.items()},
                                           "discrepancies":len(discrepancies),"failures":failures},ensure_ascii=False),flush=True)
    return 1 if failures else 0
if __name__=="__main__":
    sys.exit(main())
