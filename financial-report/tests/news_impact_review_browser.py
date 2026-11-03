#!/usr/bin/env python3
"""Desktop + mobile Chrome QA for reviewed-only news impact visual state.

Uses public static layout with real CSS and the real reviewed manifest; no
production login bypass, mock impact event or claim of deployed verification.
"""
import json
import shutil
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from site_responsive_browser import fixture, FRONT

DATA = FRONT.parent / "data/news-impact-reviewed.json"
WIDTHS = [(320,720), (390,844), (768,900), (1024,850), (1440,960)]

def luminance(rgb):
    items=[float(v) / 255 for v in rgb]
    t=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in items]
    return .2126*t[0]+.7152*t[1]+.0722*t[2]

def contrast(bg, fg):
    return (max(luminance(bg),luminance(fg))+.05)/(min(luminance(bg),luminance(fg))+.05)

def main():
    with tempfile.TemporaryDirectory(prefix='finquery-impact-ux-') as root:
        dest=Path(root)
        fixture(dest)
        text=(dest/'index.html').read_text(encoding='utf-8')
        text=text.replace('</body>','<script src="news-impact-reviewed.js"></script></body>')
        (dest/'index.html').write_text(text,encoding='utf-8')
        shutil.copy2(FRONT / 'news-impact-reviewed.js',dest/'news-impact-reviewed.js')
        (dest/'data').mkdir()
        shutil.copy2(DATA,dest/'data/news-impact-reviewed.json')

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs): super().__init__(*args,directory=root,**kwargs)
            def log_message(self,*args): pass

        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        options=Options()
        for f in ('--headless=new','--no-sandbox','--disable-dev-shm-usage'):
            options.add_argument(f)
        driver=webdriver.Chrome(options=options)
        try:
            for width,height in WIDTHS:
                driver.set_window_size(width,height)
                driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{
                    'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<=768
                })
                driver.get('http://127.0.0.1:'+str(server.server_port)+'/index.html')
                WebDriverWait(driver,12).until(lambda d:d.execute_script(
                    "return window.FinNewsImpactReview?.summary()?.status==='RESEARCH_ONLY'"
                ))
                detail=driver.execute_script("""
                    document.body.classList.remove('site-locked');
                    const section=document.getElementById('market');
                    section.hidden=false;
                    const news=document.getElementById('market-news-workspace');
                    news.hidden=false;
                    const panel=document.getElementById('news-impact-reviewed-panel');
                    panel.hidden=false;
                    const tab=document.querySelector('[data-news-tab="verified"]');
                    const alert=document.getElementById('news-alert-toggle');
                    const r=panel.getBoundingClientRect();
                    const nr=news.getBoundingClientRect();
                    const t=tab.getBoundingClientRect();
                    const p=panel.querySelector('p');
                    const rgb=(value)=>[...(value.matchAll(/[0-9.]+/g))].slice(0,3).map(m=>Number(m[0]));
                    const style=getComputedStyle(p);
                    return {
                        panel:{left:r.left,right:r.right,width:r.width,height:r.height},
                        news:{left:nr.left,right:nr.right},
                        tab:{width:t.width,height:t.height},
                        bodyWidth:document.documentElement.scrollWidth,viewport:innerWidth,
                        alertHidden:alert.hidden && alert.disabled,
                        eligible:window.FinNewsImpactReview.reviewedImpacts().length,
                        canNotify:window.FinNewsImpactReview.canNotify(),
                        paragraphSize:parseFloat(style.fontSize),
                        fg:rgb(style.color),bg:rgb(getComputedStyle(panel).backgroundColor),
                        title:document.getElementById('news-reviewed-headline').textContent,
                    };
                """)
                assert detail['eligible']==0 and detail['canNotify'] is False,(width,detail)
                assert detail['alertHidden'],(width,'alert button exposed',detail)
                assert detail['bodyWidth']<=width+2,(width,'horizontal body overflow',detail)
                assert detail['panel']['width']>=190,(width,'panel collapsed',detail)
                assert detail['panel']['left']>=-2 and detail['panel']['right']<=width+2,(width,'panel outside viewport',detail)
                assert detail['paragraphSize']>=11,(width,'body copy too small',detail)
                assert contrast(detail['bg'],detail['fg'])>=4.5,(width,'low contrast body copy',detail)
                if width<=768:
                    assert detail['tab']['height']>=34,(width,'news tab touch size',detail)
                print('FINQUERY_NEWS_IMPACT_UX',width,json.dumps(detail,ensure_ascii=False),flush=True)
            print('FINQUERY_NEWS_IMPACT_CHROME_UX_PASS',flush=True)
        finally:
            driver.quit()
            server.shutdown()

if __name__=='__main__':
    main()
