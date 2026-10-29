#!/usr/bin/env python3
"""Real Chrome shared-chart inspection: mouse, touch, keyboard, rerenders and narrow devices."""
from __future__ import annotations
import json
import shutil
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

FRONT = Path(__file__).resolve().parents[1] / "frontend"

def fixture(folder):
    for name in ("market.css", "chart-inspect.js"):
        shutil.copy2(FRONT / name, folder / name)
    # Three dates, with two series at the middle observation, and a separate tenor curve.
    html = """<!doctype html><html lang="vi"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="market.css">
    <style>body{margin:0;padding:16px;font:13px Arial}
    main{max-width:900px;margin:auto}
    svg[data-fq-inspect]{display:block;width:100%;height:auto;border:1px solid #e2e7ef}
    .panel{padding:8px;border:1px solid #edf1f6;margin-bottom:12px}</style></head>
    <body><main>
    <div class="panel"><svg id="macro-demo" viewBox="0 0 600 230"
      data-fq-inspect="line" data-fq-top="15" data-fq-bottom="200"
      tabindex="0" role="img" aria-label="Lãi suất theo tháng">
      <path d="M40 170L300 70L560 105" fill="none" stroke="#3565c7"/>
      <circle data-fq-point="0" data-fq-x="40" data-fq-y="170"
        data-fq-label="T8 2026" data-fq-series="Lãi suất"
        data-fq-value="3,39" data-fq-unit="%/năm" cx="40" cy="170" r="4" fill="#3565c7"/>
      <circle data-fq-point="1" data-fq-x="300" data-fq-y="70"
        data-fq-label="T9 2026" data-fq-series="Lãi suất"
        data-fq-value="4,3125" data-fq-unit="%/năm" cx="300" cy="70" r="4" fill="#3565c7"/>
      <circle data-fq-point="2" data-fq-x="560" data-fq-y="105"
        data-fq-label="T10 2026" data-fq-series="Lãi suất"
        data-fq-value="4,10" data-fq-unit="%/năm" cx="560" cy="105" r="4" fill="#3565c7"/>
      <circle data-fq-point="1b" data-fq-x="300" data-fq-y="135"
        data-fq-label="T9 2026" data-fq-series="So sánh nhóm"
        data-fq-value="+2,15" data-fq-unit="%" cx="300" cy="135" r="4" fill="#c9782a"/>
    </svg></div>
    <div class="panel"><svg id="bond-demo" viewBox="0 0 600 210" data-fq-inspect="tenor"
      data-fq-top="10" data-fq-bottom="175" tabindex="0" role="img" aria-label="Trái phiếu">
      <path d="M40 160L300 80L560 40" fill="none" stroke="#188779"/>
      <circle data-fq-point="0" data-fq-x="40" data-fq-y="160" data-fq-label="2Y"
        data-fq-series="TPCP" data-fq-value="4,02" data-fq-unit="%/năm"
        cx="40" cy="160" r="4" fill="#188779"/>
      <circle data-fq-point="1" data-fq-x="300" data-fq-y="80" data-fq-label="5Y"
        data-fq-series="TPCP" data-fq-value="4,125" data-fq-unit="%/năm"
        cx="300" cy="80" r="4" fill="#188779"/>
      <circle data-fq-point="2" data-fq-x="560" data-fq-y="40" data-fq-label="10Y"
        data-fq-series="TPCP" data-fq-value="4,47" data-fq-unit="%/năm"
        cx="560" cy="40" r="4" fill="#188779"/>
    </svg></div>
    <script src="chart-inspect.js"></script>
    </main></body></html>"""
    (folder / "index.html").write_text(html, encoding="utf-8")

def read(driver):
    return driver.execute_script("""
      const tip=document.querySelector('.fq-chart-tooltip');
      return {visible:!!tip&&!tip.hidden,label:tip?.querySelector('.fq-chart-tooltip-label')?.textContent,
        series:tip?.querySelector('.fq-chart-tooltip-series')?.textContent,
        value:tip?.querySelector('.fq-chart-tooltip-value')?.textContent,
        guide:document.querySelector('.fq-chart-guide[visibility="visible"]')!=null,
        cursor:document.querySelector('.fq-chart-cursor[visibility="visible"]')!=null,
        overflows:document.documentElement.scrollWidth>innerWidth+1};
    """)

def run():
    with tempfile.TemporaryDirectory(prefix="finquery-chart-inspect-") as tmp:
        fixture(Path(tmp))
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=tmp, **kwargs)
            def log_message(self, *args): pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        opts=Options()
        for flag in ("--headless=new","--no-sandbox","--disable-dev-shm-usage",
                     "--force-device-scale-factor=1","--window-size=1280,920"):
            opts.add_argument(flag)
        driver=webdriver.Chrome(options=opts)
        try:
            for width,height in ((1280,920),(390,844),(320,780)):
                driver.set_window_size(width,height)
                driver.get("http://127.0.0.1:%s/index.html"%server.server_port)
                WebDriverWait(driver,12).until(lambda d:d.execute_script("return !!window.FinChartInspect"))
                macro=driver.find_element(By.ID,"macro-demo")
                ActionChains(driver).move_to_element(macro.find_element(By.CSS_SELECTOR,'[data-fq-point="1"]')).perform()
                WebDriverWait(driver,5).until(lambda d:read(d)["visible"])
                shown=read(driver)
                assert shown["label"]=="T9 2026" and shown["value"]=="4,3125 %/năm", (width,shown)
                assert shown["guide"] and shown["cursor"] and not shown["overflows"],(width,shown)
                # Same period, second series: pick by nearest Y; use an event at the chart coordinate.
                second=driver.execute_script("""
                  const svg=document.getElementById('macro-demo');
                  const p=svg.querySelector('[data-fq-point="1b"]');
                  const m=svg.getScreenCTM(),x=Number(p.getAttribute('cx')),y=Number(p.getAttribute('cy'));
                  const px=m.a*x+m.c*y+m.e,py=m.b*x+m.d*y+m.f;
                  svg.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerType:'touch',clientX:px,clientY:py}));
                  const t=document.querySelector('.fq-chart-tooltip');
                  return [t.querySelector('.fq-chart-tooltip-series').textContent,
                          t.querySelector('.fq-chart-tooltip-value').textContent];
                """)
                assert second==["So sánh nhóm","+2,15 %"],(width,second)
                # Focus and keyboard reads exact source observations in chronological order.
                macro.click()
                macro.send_keys(Keys.HOME)
                first=read(driver)
                assert first["label"]=="T8 2026" and first["value"]=="3,39 %/năm",(width,first)
                macro.send_keys(Keys.ARROW_RIGHT)
                middle=read(driver)
                assert middle["label"]=="T9 2026" and middle["value"]=="4,3125 %/năm",(width,middle)
                macro.send_keys(Keys.END)
                latest=read(driver)
                assert latest["label"]=="T10 2026" and latest["value"]=="4,10 %/năm",(width,latest)
                # DOM render replacement must not require re-binding individual chart event handlers.
                driver.execute_script("const e=document.getElementById('bond-demo');e.outerHTML=e.outerHTML")
                bond=driver.find_element(By.ID,"bond-demo")
                ActionChains(driver).move_to_element(bond.find_element(By.CSS_SELECTOR,'[data-fq-point="1"]')).perform()
                WebDriverWait(driver,5).until(lambda d:read(d)["label"]=="5Y")
                point=read(driver)
                assert point["value"]=="4,125 %/năm" and point["series"]=="TPCP",(width,point)
                bond.send_keys(Keys.ESCAPE)
                WebDriverWait(driver,3).until(lambda d:not read(d)["visible"])
                print("CHART_INSPECT_BROWSER_PASS",width,shown["value"],second,point["value"])
        finally:
            driver.quit()
            server.shutdown()

if __name__=="__main__":
    run()
