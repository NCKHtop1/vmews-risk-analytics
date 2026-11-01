#!/usr/bin/env python3
"""Portfolio visual regression with a deterministic fixture and real Chrome.

Covers: empty onboarding, saved policy, responsive layout, sector readability
and non-empty rebalance UI. The fixture cannot place live orders.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import re
import shutil
import tempfile
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

FRONT = Path(__file__).resolve().parents[1] / 'frontend'
ASSETS = ['style.css','market.css','risk-monitor.css','portfolio-intelligence.css',
          'responsive-system.css','fonts.css','portfolio-rebalance-core.js',
          'portfolio-intelligence.js','portfolio-policy-ui.js','portfolio-help.js']
JS = ['portfolio-rebalance-core.js','portfolio-intelligence.js','portfolio-policy-ui.js']
FIX = r"""
window.__fixture = {events:[], policy:null};
const fixture = window.__fixture;
const asOf='2026-10-30T07:45:00.004Z';
const specs=[
 ['port','Cảng biển',-.4,1.2],['steel','Thép',2.2,8.5],['bank','Ngân hàng',.7,.3],
 ['tech','Công nghệ',-1.7,-9.4],['health','Y tế',.2,1.1],['consumer','Tiêu dùng',.9,.1],
 ['build','Xây dựng',-.2,3.1],['securities','Chứng khoán',-.3,1.3],['energy','Năng lượng',-.5,-1.2],
 ['realestate','Bất động sản',-1.2,-3.2],['transport','Vận tải',.5,.8],
 ['retail','Bán lẻ',-.6,-4.4],['chem','Hóa chất',.2,-2.3]
];
const sectors=specs.map(([id,label,rs5,rs20])=>({
 id,label,score:50,memberRows:id==='port'?[{symbol:'GMD'}]:id==='steel'?[{symbol:'NKG'}]:[{symbol:'ZZZ'}],
 rs5,rs20,used:5,members:7,status:'sufficient',
 trail:[0,1,2,3,4,5].map(i=>({date:'2026-10-'+(25+i),rs5:rs5+.08*i,rs20:rs20-.08*i}))
}));
window.FinMarketData={
 currentBundle:()=>null,
 get:async file=>{
  if(file==='quotes.json')return{latestSourceTime:asOf,quotes:{GMD:{price:52700},NKG:{price:11900}}};
  if(file==='risk-monitor.json')return{sourceTime:asOf,sourceDate:'2026-10-30',sectors};
  if(file==='sector-rotation.json')return{version:'FINQUERY-SECTOR-RS-1.0',
   generatedAt:'2026-10-30T08:30:00Z',sourceDate:'2026-10-30',
   benchmark:{eligibleSymbols:72},sectors,stocks:{GMD:{sectorId:'port',rs20:1.2},NKG:{sectorId:'steel',rs20:8.5}}};
  throw Error('Unknown fixture '+file);
 }
};
const stockResponse = () => JSON.stringify({ok:true,events:fixture.events});
window.fetch=async (url,opts={})=>{
 const path=String(url),method=opts.method||'GET';
 if(path.includes('/api/user/portfolio-policy')){
  if(method==='PUT'){
   const p=JSON.parse(opts.body);
   fixture.policy={preset:p.preset,cash_pct:p.cashPct,drift_pct:p.driftPct,revision:(fixture.policy?.revision||0)+1};
  }
  return new Response(JSON.stringify({ok:true,policy:fixture.policy}),{status:200,headers:{'Content-Type':'application/json'}});
 }
 if(path.includes('/api/user/portfolio'))return new Response(stockResponse(),{status:200,headers:{'Content-Type':'application/json'}});
 throw Error('Unmocked '+path);
};
"""

def main():
    with tempfile.TemporaryDirectory(prefix='fq-portfolio-visual-') as name:
        path=Path(name)
        html=(FRONT/'index.html').read_text(encoding='utf-8')
        html=re.sub(r'<script\b[^>]*>[\s\S]*?</script>', '', html, flags=re.I)
        html=html.replace('<body class="site-locked">','<body>')
        html=html.replace('</body>','<script>'+FIX+'</script>'+''.join(
            '<script defer src="'+x+'"></script>' for x in JS)+'</body>')
        (path/'index.html').write_text(html,encoding='utf-8')
        for asset in ASSETS:shutil.copy2(FRONT/asset,path/asset)
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*a,**kw):super().__init__(*a,directory=name,**kw)
            def log_message(self,*a):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        opts=Options()
        for flag in ['--headless=new','--no-sandbox','--disable-dev-shm-usage']:opts.add_argument(flag)
        driver=webdriver.Chrome(options=opts)
        try:
            for width in [390,1440]:
                driver.set_window_size(width,920)
                driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{
                  'width':width,'height':920,'deviceScaleFactor':1,'mobile':width<600})
                driver.get(f'http://127.0.0.1:{server.server_port}/index.html')
                WebDriverWait(driver,15).until(lambda d:d.execute_script("return !!window.FinPortfolioPolicy && !!window.FinPortfolio"))
                driver.execute_script("""
                  document.body.classList.remove('site-locked');
                  document.getElementById('portfolio').hidden=false;
                  document.querySelector('.intro').hidden=true;
                  document.querySelector('.workspace').hidden=true;
                  window.FinPortfolio.open();
                """)
                WebDriverWait(driver,15).until(lambda d:d.execute_script(
                    "return !!document.querySelectorAll('#portfolio-setup-templates .portfolio-template').length"))
                result=driver.execute_script("""
                  return {width:innerWidth,scroll:document.documentElement.scrollWidth,
                    templates:document.querySelectorAll('#portfolio-setup-templates .portfolio-template').length,
                    onboarding:!document.getElementById('portfolio-onboarding').hidden,
                    emptyCardsHidden:getComputedStyle(document.querySelector('.portfolio-layout')).display==='none'}
                """)
                assert result['templates']==4 and result['onboarding'] and result['emptyCardsHidden'],result
                assert result['scroll']<=width+3,result
                WebDriverWait(driver,10).until(lambda d:d.execute_script(
                    "return document.getElementById('portfolio-market-brief').textContent.includes('2 mã có giá')"))
                WebDriverWait(driver,10).until(lambda d:d.execute_script(
                    "return document.getElementById('portfolio-market-brief').textContent.includes('RS20 nổi bật')"))
                assert driver.find_element(By.CSS_SELECTOR,'#portfolio-setup-templates .portfolio-template').text.find('Golden Gate')>=0
                # Adopt a template and save it through the actual controller.
                driver.execute_script("const e=document.querySelector('#portfolio-setup-templates [data-portfolio-preset=defensive]');e.scrollIntoView({block:'center'});e.click();")
                WebDriverWait(driver,5).until(lambda d:d.execute_script(
                    "return document.getElementById('portfolio-cash-target').value==='30'"))
                driver.execute_script("const e=document.getElementById('portfolio-policy-save');e.scrollIntoView({block:'center'});e.click();")
                WebDriverWait(driver,7).until(lambda d:d.execute_script(
                    "return window.__fixture.policy?.preset==='defensive'"))
                driver.execute_script("const e=document.querySelector('#portfolio-tabs [data-portfolio-tab=rotation]');e.scrollIntoView({block:'center'});e.click();")
                WebDriverWait(driver,12).until(lambda d:d.execute_script(
                    "return document.querySelectorAll('#portfolio-rotation-chart circle').length===13"))
                chart=driver.execute_script("""
                  const svg=document.querySelector('#portfolio-rotation-chart svg');
                  return {dots:svg.querySelectorAll('circle').length,
                    paths:svg.querySelectorAll('polyline').length,
                    texts:svg.querySelectorAll('text').length,
                    options:document.querySelectorAll('#portfolio-sector-list button').length};
                """)
                assert chart['dots']==13 and chart['paths']==0 and chart['options']==13,chart
                assert chart['texts']<=9,('overlapping labels returned',chart)
                driver.execute_script("const e=document.querySelector('#portfolio-sector-list [data-portfolio-sector=tech]');e.scrollIntoView({block:'center'});e.click();")
                assert 'Công nghệ' in driver.find_element(By.ID,'portfolio-rotation-detail').text
                assert driver.execute_script("return document.querySelectorAll('#portfolio-rotation-chart polyline').length") == 1
                # Switch the same mock account from empty to a real valued 2-ticker ledger.
                driver.execute_script("""
                  window.__fixture.events=[
                    {event_id:1,kind:'DEPOSIT',amount_vnd:200000000,trade_date:'2026-10-28',symbol:null},
                    {event_id:2,kind:'BUY',symbol:'GMD',quantity:3000,unit_price_vnd:56000,fee_vnd:0,trade_date:'2026-10-29'},
                    {event_id:3,kind:'BUY',symbol:'NKG',quantity:2000,unit_price_vnd:10000,fee_vnd:0,trade_date:'2026-10-29'}
                  ];
                  window.FinPortfolio.refresh();
                """)
                WebDriverWait(driver,15).until(lambda d:d.execute_script(
                    "return document.querySelectorAll('#portfolio-holdings-body tr').length===2"))
                driver.execute_script("const e=document.querySelector('#portfolio-tabs [data-portfolio-tab=plan]');e.scrollIntoView({block:'center'});e.click();")
                WebDriverWait(driver,12).until(lambda d:d.execute_script(
                    "return document.querySelectorAll('#portfolio-target-rows tr').length===2"))
                final=driver.execute_script("""
                  return {overflow:document.documentElement.scrollWidth-innerWidth,
                    onboardHidden:document.getElementById('portfolio-onboarding').hidden,
                    planCards:document.querySelectorAll('#portfolio-policy-cards .portfolio-template').length,
                    targets:document.querySelectorAll('#portfolio-target-rows tr').length,
                    review:document.getElementById('portfolio-plan-result').textContent.length};
                """)
                assert final['overflow']<=3 and final['onboardHidden'],final
                assert final['planCards']==4 and final['targets']==2 and final['review']>25,final
                print('PORTFOLIO_BROWSER_PASS',width,json.dumps({**result,**chart,**final}),flush=True)
        finally:
            driver.quit();server.shutdown()

if __name__=='__main__':main()
