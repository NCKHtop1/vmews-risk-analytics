#!/usr/bin/env python3
"""Real Chrome QA: no unverified-impact tab, score, methodology or empty impact card.

Runs actual production markup/CSS at mobile/tablet/desktop widths. The
research guard can still validate in the background, never on the UI.
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
WIDTHS = [(320, 720), (390, 844), (768, 900), (1024, 850), (1440, 960)]

def main():
    with tempfile.TemporaryDirectory(prefix="finquery-news-quiet-") as folder:
        root=Path(folder)
        fixture(root)
        page=(root/"index.html").read_text(encoding="utf-8")
        page=page.replace("</body>",'<script src="news-impact-reviewed.js"></script></body>')
        (root/"index.html").write_text(page,encoding="utf-8")
        shutil.copy2(FRONT/"news-impact-reviewed.js",root/"news-impact-reviewed.js")
        (root/"data").mkdir()
        shutil.copy2(DATA,root/"data/news-impact-reviewed.json")

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,directory=folder,**kwargs)
            def log_message(self,*args): pass

        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        opts=Options()
        for flag in ("--headless=new","--no-sandbox","--disable-dev-shm-usage"):
            opts.add_argument(flag)
        driver=webdriver.Chrome(options=opts)
        try:
            for width,height in WIDTHS:
                driver.set_window_size(width,height)
                driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":1,"mobile":width<=768
                })
                driver.get(f"http://127.0.0.1:{server.server_port}/index.html")
                WebDriverWait(driver,12).until(
                    lambda d:d.execute_script(
                        "return window.FinNewsImpactReview?.summary()?.status==='RESEARCH_ONLY'"
                    )
                )
                result=driver.execute_script("""
                  document.body.classList.remove('site-locked');
                  const market=document.getElementById('market');market.hidden=false;
                  const news=document.getElementById('market-news-workspace');news.hidden=false;
                  const rect=news.getBoundingClientRect();
                  const list=document.getElementById('news-primary-tabs');
                  const buttons=[...list.querySelectorAll('button')];
                  const data=window.FinNewsImpactReview;
                  const forbidden=['BẰNG CHỨNG THỰC CHỨNG','Tiêu chí kiểm chứng',
                     'Sổ nghiên cứu tiến cứu','0 tác động đạt chuẩn',
                     'Chưa có sự kiện đạt chuẩn tác động'];
                  const text=news.innerText;
                  return {
                    listExists:!!document.getElementById('news-list'),
                    latest:!!list.querySelector('[data-news-tab="all"]'),
                    company:!!list.querySelector('[data-news-tab="company"]'),
                    verifiedTab:!!list.querySelector('[data-news-tab="verified"]'),
                    verifiedOption:!!document.querySelector('#news-mode option[value="verified"]'),
                    researchPanel:!!document.getElementById('news-impact-reviewed-panel'),
                    researchCount:!!document.getElementById('news-impact-summary'),
                    forbiddenVisible:forbidden.filter(x=>text.includes(x)),
                    width:rect.width,left:rect.left,right:rect.right,
                    bodyWidth:document.documentElement.scrollWidth,
                    viewport:innerWidth,
                    tabMinHeight:Math.min(...buttons.map(b=>b.getBoundingClientRect().height)),
                    notifications:data.canNotify(),
                    reviewedImpacts:data.reviewedImpacts().length
                  };
                """)
                assert result["listExists"] and result["latest"] and result["company"], (width,result)
                assert not result["verifiedTab"] and not result["verifiedOption"], (width,result)
                assert not result["researchPanel"] and not result["researchCount"], (width,result)
                assert result["forbiddenVisible"]==[], (width,result)
                assert not result["notifications"] and result["reviewedImpacts"]==0,(width,result)
                assert result["bodyWidth"]<=width+2,(width,"horizontal overflow",result)
                assert result["left"]>=-2 and result["right"]<=width+2,(width,"news outside viewport",result)
                if width<=768:
                    assert result["tabMinHeight"]>=36,(width,"touch target too small",result)
                print("FINQUERY_NEWS_QUIET_UX",width,json.dumps(result,ensure_ascii=False),flush=True)
            print("FINQUERY_NEWS_QUIET_UX_PASS",flush=True)
        finally:
            driver.quit()
            server.shutdown()

if __name__=="__main__":
    main()
