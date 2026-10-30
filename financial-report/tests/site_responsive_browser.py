#!/usr/bin/env python3
"""Automated desktop + mobile UX regression against the REAL FinQuery shell.

This uses public static markup plus fixture data. It does not bypass production
authentication or claim to test authenticated live flows. Run alongside
existing chart, auth and risk data-contract suites.
"""
import json
import re
import shutil
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

FRONT = Path(__file__).resolve().parents[1] / "frontend"
WIDTHS = [(320, 720), (360, 780), (390, 844), (430, 932),
          (768, 900), (1024, 800), (1440, 900), (1920, 1080)]
CSS = ("style.css", "market.css", "risk-monitor.css", "responsive-system.css", "fonts.css")
JS = ("responsive-navigation.js", "section-collapse.js", "workspace-tabs.js")


def fixture(folder):
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    html = html.replace('<body class="site-locked">', '<body>')
    html = html.replace('<form id="site-unlock-form"', '<form id="site-unlock-form" hidden')
    # Keep real structure, CSS order, semantic controls and lightweight navigation JS.
    html = html.replace("</body>", "".join(f'<script src="{name}"></script>' for name in JS) + "</body>")
    (folder / "index.html").write_text(html, encoding="utf-8")
    for item in CSS + JS:
        shutil.copy2(FRONT / item, folder / item)
    for name in ("login.html", "admin.html"):
        html=(FRONT.parent.parent / "finquery-access" / name).read_text(encoding="utf-8")
        html=re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
        (folder / name).write_text(html, encoding="utf-8")
    # Test the same visible table layout the app generates, without requiring backend data.
    return html


def main():
    with tempfile.TemporaryDirectory(prefix="finquery-responsive-") as path:
        folder = Path(path)
        fixture(folder)

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=path, **kwargs)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        options = Options()
        for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"):
            options.add_argument(flag)
        driver = webdriver.Chrome(options=options)
        try:
            for width, height in WIDTHS:
                driver.set_window_size(width, height)
                driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1,
                    "mobile": width <= 768
                })
                driver.get(f"http://127.0.0.1:{server.server_port}/index.html")
                WebDriverWait(driver, 10).until(lambda d: d.execute_script(
                    "return !!window.FinWorkspaceTabs && !!document.getElementById('finquery-nav-toggle')"
                ))
                # Representative generated tables, cards and chart layout.
                driver.execute_script("""
                  const report=document.getElementById('table-container');
                  report.innerHTML='<table><thead><tr><th>Chỉ tiêu</th>'+
                    Array.from({length:11},(_,i)=>'<th>Q'+(i+1)+'</th>').join('')+
                    '</tr></thead><tbody><tr><td>Tổng tài sản</td>'+
                    Array.from({length:11},()=>'<td>1.234.567</td>').join('')+
                    '</tr></tbody></table>';
                  const tabs=document.getElementById('report-tabs');
                  tabs.innerHTML=['Cân đối kế toán','Kết quả KD','Lưu chuyển tiền','Chỉ số'].map((label,i)=>
                    '<button role="tab" type="button" aria-selected="'+(i===0)+'">'+label+'</button>').join('');
                  const target=document.getElementById('risk-sector-detail');
                  target.innerHTML='<div class="risk-stock-table-wrap" tabindex="0" aria-label="Danh sách rủi ro: vuốt ngang để xem thêm"><table class="risk-stock-table">'+
                    '<thead><tr>'+Array.from({length:8},(_,i)=>'<th>Chỉ tiêu '+(i+1)+'</th>').join('')+
                    '</tr></thead><tbody><tr>'+Array.from({length:8},()=>'<td>1.234.567</td>').join('')+
                    '</tr></tbody></table></div>';
                  target.hidden=false;
                  document.getElementById('risk-monitor').hidden=false;
                  document.getElementById('strategy-builder').hidden=false;
                  document.getElementById('overview').hidden=false;
                  document.getElementById('macro').classList.remove('is-collapsed');
                  document.getElementById('macro-body').hidden=false;
                  document.getElementById('macro-body').style.display='block';
                  document.querySelector('body').classList.remove('site-locked');
                """)
                report = driver.execute_script("""
                    const $=s=>document.querySelector(s);
                    const box=s=>{let e=$(s);if(!e)return null;let r=e.getBoundingClientRect();
                       return {x:r.x,right:r.right,width:r.width,client:e.clientWidth,scroll:e.scrollWidth}};
                    const nav=$('.header nav[aria-label="Điều hướng nền tảng"]');
                    const tab=$('#market-primary-tabs');
                    const tabBox=tab.getBoundingClientRect();
                    const tabFits=[...tab.querySelectorAll('button')].every(e=>{
                      const r=e.getBoundingClientRect();return r.left>=tabBox.left-2&&r.right<=tabBox.right+2;
                    });
                    const ctl=$('#chart-terminal .market-controls');
                    const controls=[...ctl.children].filter(e=>getComputedStyle(e).display!=='none');
                    const controlsFit=controls.every(e=>{
                     const a=e.getBoundingClientRect(),b=ctl.getBoundingClientRect();
                     return a.left>=b.left-2&&a.right<=b.right+2;
                    });
                    const touch=['#finquery-nav-toggle','#ticker','#chart-interval',
                        '#chart-type','#chart-period','#chart-focus-latest',
                        '#market-primary-tabs button'].map(sel=>{
                        const e=$(sel);return {sel,height:e?.getBoundingClientRect().height||0};
                    });
                    const outer=['.header','main','.workspace','.configuration','.preview',
                      '#market','.market-price','#chart-terminal','#risk-monitor',
                      '#strategy-builder','#macro','#overview'].map(sel=>{
                      const e=$(sel),r=e.getBoundingClientRect();
                      return {sel,left:r.left,right:r.right,width:r.width};
                    });
                    const leaks=outer.filter(r=>r.left < -2||r.right > innerWidth+2);
                    return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
                      header:box('.header'),nav:box('.header nav'),
                      market:box('#market'),marketTab:box('#market-primary-tabs'),
                      chart:box('#price-chart'),table:box('.table-container'),
                      riskTable:box('.risk-stock-table-wrap'),
                      compactToggle:box('#finquery-nav-toggle'),
                      tabFits,controlsFit,leaks,touch,
                      advancedClosed:!$('#chart-advanced-tools').open};
                """)
                print("FINQUERY_RESPONSIVE", width, json.dumps(report, ensure_ascii=False), flush=True)
                assert report["documentWidth"] <= width + 2, ("document overflow", width, report)
                assert not report["leaks"], ("section beyond viewport", width, report["leaks"])
                assert report["tabFits"] and report["controlsFit"], ("clipped tabs/controls", width, report)
                assert report["advancedClosed"], ("advanced tools expanded by default", width)
                assert report["chart"]["width"] > 150, ("chart collapsed", width)
                assert report["table"]["scroll"] >= report["table"]["client"], ("report table clipped", width)
                assert report["riskTable"]["scroll"] >= report["riskTable"]["client"], ("risk table clipped", width)
                if width <= 850:
                    assert report["compactToggle"]["width"] >= 80
                    for target in report["touch"]:
                        assert target["height"] >= 38, ("small touch target", width, target)
                    # One menu, navigable without a horizontal scroll on phones.
                    assert driver.execute_script(
                      "return getComputedStyle(document.querySelector('.header nav')).display"
                    ) == "none"
                    driver.find_element("id", "finquery-nav-toggle").click()
                    nav_open = driver.execute_script("""
                      const h=document.querySelector('.header');
                      return h.classList.contains('finquery-nav-open') &&
                        document.getElementById('finquery-nav-toggle').getAttribute('aria-expanded')==='true' &&
                        [...h.querySelectorAll('nav a')].every(e=>{
                           const r=e.getBoundingClientRect(),hbox=h.getBoundingClientRect();
                           return r.left>=hbox.left-2&&r.right<=hbox.right+2
                        });
                    """)
                    assert nav_open, ("mobile menu overflow", width)
                    driver.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
                    assert driver.execute_script(
                        "return document.getElementById('finquery-nav-toggle').getAttribute('aria-expanded')"
                    ) == "false"
                else:
                    assert driver.execute_script(
                        "return getComputedStyle(document.getElementById('finquery-nav-toggle')).display"
                    ) == "none"
                # Open and close one advanced control in its original DOM location.
                menu = driver.execute_script("""
                  const d=document.getElementById('chart-advanced-tools');
                  const summary=d.querySelector('summary');
                  const oldHeight=d.parentElement.getBoundingClientRect().height;
                  summary.click();
                  const r=d.querySelector('.chart-advanced-actions').getBoundingClientRect();
                  return {open:d.open, label:summary.getAttribute('aria-label'),
                    text:summary.textContent.trim(),width:summary.getBoundingClientRect().width,
                    oldHeight,newHeight:d.parentElement.getBoundingClientRect().height,
                    visible:r.width>100 && r.height>100,
                    fits:r.left>=-2 && r.right<=innerWidth+2};
                """)
                assert menu["open"] and menu["visible"] and menu["fits"], (width,menu)
                assert menu["label"]=="Tùy chọn biểu đồ" and menu["text"]=="⋯", (width,menu)
                assert menu["width"]<=44 and menu["oldHeight"]==menu["newHeight"], (width,menu)
                driver.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
                assert not driver.execute_script("return document.getElementById('chart-advanced-tools').open")
                driver.execute_script("document.querySelector('#chart-advanced-tools > summary').click()")
                driver.execute_script("document.getElementById('chart-fit').click()")
                assert not driver.execute_script("return document.getElementById('chart-advanced-tools').open")
            # Auth pages use independent HTML/CSS: protect mobile sign-in and admin UI.
            for width in (320, 390, 768, 1024):
                driver.set_window_size(width, 900)
                driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width <= 768
                })
                for page in ("login.html", "admin.html"):
                    driver.get(f"http://127.0.0.1:{server.server_port}/{page}")
                    check=driver.execute_script("""
                      const main=document.querySelector('main').getBoundingClientRect();
                      const width=innerWidth;
                      return {documentWidth:document.documentElement.scrollWidth,
                        mainLeft:main.left,mainRight:main.right,viewport:width};
                    """)
                    print("FINQUERY_AUTH_RESPONSIVE",page,width,json.dumps(check),flush=True)
                    assert check["documentWidth"]<=width+2,(page,width,check)
                    assert check["mainLeft"]>=-2 and check["mainRight"]<=width+2,(page,width,check)
            print("FINQUERY_RESPONSIVE_SITE_BROWSER_PASS", flush=True)
        finally:
            driver.quit()
            server.shutdown()


if __name__ == "__main__":
    main()
