#!/usr/bin/env python3
"""Real Chrome UX gate: every dated ON point exposes its exact rate on hover, tap, and keyboard."""
from __future__ import annotations
import json
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

FRONT = Path(__file__).resolve().parents[1] / "frontend"
OBS = [
    {"date": "2026-10-20", "value": 3.71},
    {"date": "2026-10-21", "value": 3.39},
    {"date": "2026-10-22", "value": 4.3125},
    {"date": "2026-10-23", "value": 3.82},
    {"date": "2026-10-26", "value": 4.49},
    {"date": "2026-10-28", "value": 4.1},
]

def fixture(folder: Path):
    for name in ("market.css", "liquidity-derivatives.js"):
        shutil.copy2(FRONT / name, folder / name)
    payload = {
        "schemaVersion": 1, "asOf": "2026-10-28",
        "lastCheckedAt": datetime.now(timezone.utc).isoformat(),
        "interbank": {"status": "secondary_source_crosschecked", "observations": OBS},
        "derivatives": {"months": []},
        "vbmaSwap": {"status": "awaiting_verified_source", "points": []},
    }
    page = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <link rel="stylesheet" href="market.css">
    <style>*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f6f8fc}
    #macro-liquidity-overview{max-width:1080px;margin:10px auto;padding:12px;min-width:0}
    #money-on{width:100%;min-width:0;background:white}</style></head><body>
    <main id="macro-liquidity-overview"><div id="money-on" class="macro-viz-card"></div>
    <div id="money-futures"></div><div id="money-swap"></div><div id="money-vbma-curves"></div>
    <button id="money-refresh">Làm mới</button></main>
    <script>window.__sample=__DATA__;
    window.fetch=async url=>String(url).includes('on-observations')
      ? {ok:false,status:403,json:async()=>({})}
      : {ok:true,status:200,json:async()=>window.__sample};</script>
    <script src="liquidity-derivatives.js"></script></body></html>"""
    (folder / "index.html").write_text(
        page.replace("__DATA__", json.dumps(payload, ensure_ascii=False)), encoding="utf-8"
    )

def visible(driver):
    return driver.execute_script("""
      const el=document.querySelector('.money-on-tooltip');
      return !!el&&!el.hidden&&getComputedStyle(el).display!=='none';
    """)

def rate(driver):
    return driver.execute_script("""
      const el=document.querySelector('.money-on-tooltip');
      return {date:el?.querySelector('[data-on-tooltip-date]')?.textContent,
              value:el?.querySelector('[data-on-tooltip-rate]')?.textContent,
              active:document.querySelector('.money-on-trend')?.dataset.activePoint,
              focus:document.querySelector('[data-on-focus]')?.getAttribute('visibility')};
    """)

def run():
    with tempfile.TemporaryDirectory(prefix="finquery-on-tooltip-") as tmp:
        fixture(Path(tmp))
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=tmp, **kwargs)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        opts = Options()
        for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                     "--window-size=1280,900", "--force-device-scale-factor=1"):
            opts.add_argument(flag)
        driver = webdriver.Chrome(options=opts)
        try:
            for width in (1280, 390, 320):
                driver.set_window_size(width, 850)
                driver.get("http://127.0.0.1:%s/index.html" % server.server_port)
                WebDriverWait(driver, 15).until(
                    lambda d:len(d.find_elements(By.CSS_SELECTOR, ".money-on-trend [data-on-point]")) == len(OBS)
                )
                dots = driver.find_elements(By.CSS_SELECTOR, ".money-on-trend [data-on-point]")
                ActionChains(driver).move_to_element(dots[1]).perform()
                WebDriverWait(driver, 6).until(visible)
                hovered = rate(driver)
                assert hovered == {"date": "21/10/2026", "value": "3,39", "active": "1", "focus": "visible"}, (width, hovered)
                driver.execute_script("""
                  const dot=document.querySelector('[data-on-point="2"]');
                  const r=dot.getBoundingClientRect();
                  dot.dispatchEvent(new PointerEvent('pointerdown',{
                    bubbles:true,pointerType:'touch',clientX:r.left+r.width/2,clientY:r.top+r.height/2}));
                """)
                tapped = rate(driver)
                assert tapped["date"] == "22/10/2026" and tapped["value"] == "4,3125", (width, tapped)
                svg = driver.find_element(By.CSS_SELECTOR, "svg.money-on-trend")
                svg.click()
                svg.send_keys(Keys.HOME)
                start = rate(driver)
                assert start["date"] == "20/10/2026" and start["value"] == "3,71", (width, start)
                svg.send_keys(Keys.ARROW_RIGHT)
                next_one = rate(driver)
                assert next_one["date"] == "21/10/2026" and next_one["value"] == "3,39", (width, next_one)
                svg.send_keys(Keys.END)
                last = rate(driver)
                assert last["date"] == "28/10/2026" and last["value"] == "4,10", (width, last)
                driver.execute_script("window.FinLiquidityDerivatives.setData(window.__sample)")
                WebDriverWait(driver, 5).until(
                    lambda d:len(d.find_elements(By.CSS_SELECTOR, ".money-on-trend [data-on-point]")) == len(OBS)
                )
                dots = driver.find_elements(By.CSS_SELECTOR, ".money-on-trend [data-on-point]")
                ActionChains(driver).move_to_element(dots[2]).perform()
                WebDriverWait(driver, 5).until(visible)
                assert rate(driver)["value"] == "4,3125", ("rerender must retain hover", width, rate(driver))
                print("ON_TOOLTIP_BROWSER_PASS", width, hovered, tapped, next_one, last)
        finally:
            driver.quit()
            server.shutdown()

if __name__ == "__main__":
    run()
