#!/usr/bin/env python3
"""Real Chrome regression: adding all indicators must keep price candles visible."""
from __future__ import annotations
import json
import shutil
import tempfile
import threading
from datetime import date, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

FRONT = Path(__file__).resolve().parents[1] / "frontend"
INDICATORS = ("sma", "ema", "wma", "vwma", "bb", "supertrend", "volume", "vma",
              "rsi", "macd", "atr", "adx", "stoch", "cci", "roc", "willr", "obv", "mfi", "cmf")


def bars():
    values = []
    start = date(2025, 10, 1)
    for i in range(360):
        day = start + timedelta(days=i)
        if day.weekday() > 4:
            continue
        price = 22000 + i * 10 + (i % 21 - 10) * 32
        values.append({"time": day.isoformat(), "open": price - 40,
                       "high": price + 140, "low": price - 170,
                       "close": price + 20, "volume": 800000 + (i % 20) * 40000})
    return values


def fixture(folder):
    vendor = folder / "vendor"
    vendor.mkdir()
    for name in ("chart-math.js", "chart-engine.js", "market.css"):
        shutil.copy2(FRONT / name, folder / name)
    shutil.copy2(FRONT / "vendor/lightweight-charts-5.0.9.js",
                 vendor / "lightweight-charts-5.0.9.js")
    (folder / "chart-config.json").write_text("{}", encoding="utf-8")
    checks = "".join(f'<label><input id="ind-{name}" type="checkbox" {"checked" if name in ("sma","volume") else ""}>{name}</label>'
                     for name in INDICATORS)
    controls = ("chart-zoom-in", "chart-zoom-out", "chart-fit", "chart-focus-latest", "chart-fullscreen", "indicator-open", "indicator-close", "chart-marker-toggle")
    buttons = "".join(f'<button type="button" id="{name}">{name}</button>' for name in controls)
    html = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <link rel="stylesheet" href="market.css"><style>*{{box-sizing:border-box}}body{{margin:0;padding:12px;font-family:Arial}}#chart-terminal{{max-width:1080px;margin:auto;min-width:0}}
    #price-chart{{height:540px;min-height:400px;width:100%;overflow:hidden}}[hidden]{{display:none!important}}
    #chart-insight-markers{{height:10px}}</style></head>
    <body><div id="chart-terminal">
    <select id="chart-interval"><option value="1d" selected>Ngày</option><option value="1m">1 phút</option></select>
    <select id="chart-type"><option value="candles" selected>Nến</option><option value="line">Đường</option><option value="area">Vùng</option></select>
    <select id="chart-period"><option value="recent" selected>Gần nhất</option><option value="0">All</option></select>
    {buttons}<span id="chart-status"></span><span id="chart-range-label"></span>
    <div id="chart-oscillator-nav" hidden><label for="chart-oscillator-focus">Pane</label><select id="chart-oscillator-focus"></select><small id="chart-oscillator-hint"></small></div>
    <dialog id="chart-indicators"><input id="indicator-search"><div id="indicator-list">{checks}</div><div id="indicator-selected-empty"></div><p id="chart-indicator-error"></p></dialog>
    <div class="chart-canvas-wrap"><div id="price-chart"></div><div id="chart-insight-markers"></div><span id="chart-latest-candle" class="chart-latest-candle" aria-hidden="true" hidden></span></div>
    <div id="price-readout"></div><div id="signal-toast-stack"></div><div id="signal-feed"></div>
    <div id="signal-title"></div><div id="signal-status"></div><p id="chart-stream-status" hidden></p>
    </div>
    <script src="vendor/lightweight-charts-5.0.9.js"></script>
    <script src="chart-math.js"></script>
    <script>window.FinMarketData={{get:async()=>({{
       symbol:'MBB',unit:'VND',bars:{json.dumps(bars(),separators=(',',':'))},
       collectedAt:'2026-10-23T07:45:00Z',status:'ok',source:'QA fixture'
    }})}};</script>
    <script data-config="chart-config.json" src="chart-engine.js"></script>
    <script>window.__qaChart=window.FinChart.create('./market/',()=>{{}});window.__qaChart.select('MBB');</script></body></html>"""
    (folder / "index.html").write_text(html, encoding="utf-8")


def run():
    with tempfile.TemporaryDirectory(prefix="finquery-indicators-") as tmp:
        fixture(Path(tmp))
        shutil.copy2(FRONT / "favicon.svg", Path(tmp) / "favicon.ico")
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=tmp, **kwargs)
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        opts = Options()
        for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                     "--hide-scrollbars", "--window-size=1280,920"):
            opts.add_argument(flag)
        opts.set_capability("goog:loggingPrefs", {"browser":"ALL"})
        driver = webdriver.Chrome(options=opts)
        try:
            for width, height in ((1440, 920), (768, 850), (390, 844), (320, 780)):
                driver.set_window_size(width, height)
                driver.get(f"http://127.0.0.1:{server.server_port}/index.html")
                WebDriverWait(driver, 18).until(lambda d:d.execute_script(
                    "return window.__qaChart?.bars?.length>180 && !!window.__qaChart?.series?.price"))
                focus=driver.execute_script("""
                    const c=window.__qaChart,range=c.chart.timeScale().getVisibleLogicalRange();
                    const latest=document.getElementById('chart-latest-candle');
                    const chart=document.getElementById('price-chart');
                    const observed=latest?.getBoundingClientRect();
                    const root=chart?.getBoundingClientRect();
                    const exactX=c.chart.timeScale().timeToCoordinate(c.bars.at(-1).time);
                    const markerX=observed?.left+(observed?.width||0)/2;
                    const style=latest?getComputedStyle(latest):null;
                    return {from:range?.from,to:range?.to,bars:c.bars.length,
                      label:latest?.textContent||'',period:document.getElementById('chart-period').value,
                      tf:document.getElementById('chart-interval').value,
                      cueHidden:latest?.hidden,cueClass:latest?.className,
                      pulse:style?.animationName,markerWidth:observed?.width,
                      xError:Math.abs(markerX-(root?.left||0)-exactX)};
                """)
                assert focus["period"]=="recent", focus
                assert focus["to"]>=focus["bars"]-1, "latest observation outside initial view"
                assert focus["to"]-focus["from"]<=30, "default daily chart must show readable candles without user zoom"
                assert focus["tf"]=="1d", ("chart must enter in daily candles", focus)
                assert focus["label"]=="", ("no intrusive latest-candle value banner", focus)
                assert not focus["cueHidden"] and "is-candle" in focus["cueClass"], focus
                assert focus["pulse"]=="finquery-bar-focus", ("last candle itself must pulse", focus)
                assert 5 <= focus["markerWidth"] <= 24 and focus["xError"]<7, ("cue must track last candle, not chart corner", focus)
                driver.execute_script("""
                    const select=document.getElementById('chart-type');
                    select.value='line';select.dispatchEvent(new Event('change',{bubbles:true}));
                """)
                line=driver.execute_script("""
                    const cue=document.getElementById('chart-latest-candle');
                    return {line:cue.classList.contains('is-line'),hidden:cue.hidden,
                      label:cue.textContent,animate:getComputedStyle(cue).animationName};
                """)
                assert line=={"line":True,"hidden":False,"label":"","animate":"finquery-bar-focus"},line
                driver.execute_script("""
                    const select=document.getElementById('chart-type');
                    select.value='candles';select.dispatchEvent(new Event('change',{bubbles:true}));
                """)
                driver.execute_script("""
                    const c=window.__qaChart;
                    c.chart.timeScale().setVisibleLogicalRange({from:12,to:37});
                    c.positionLatestCue();
                """)
                assert driver.execute_script(
                    "return document.getElementById('chart-latest-candle').hidden"
                ), "cue must disappear when user pans away from latest candle"
                driver.execute_script("document.getElementById('chart-focus-latest').click();")
                centered=driver.execute_script("""
                    return window.__qaChart.chart.timeScale().getVisibleLogicalRange();
                """)
                assert centered["to"]>=focus["bars"]-1, "one-click latest focus does not recenter"
                print("CHART_LATEST_FOCUS",width,json.dumps(focus),flush=True)
                driver.execute_script("""
                    const dialog=document.getElementById('chart-indicators');
                    dialog.querySelectorAll('input[type=checkbox]').forEach(el=>{
                      el.checked=true;
                      el.dispatchEvent(new Event('change',{bubbles:true}));
                    });
                """)
                result=driver.execute_script("""
                    const ctrl=window.__qaChart,container=document.getElementById('price-chart');
                    const canvases=[...container.querySelectorAll('canvas')];
                    return {width:innerWidth,pageWidth:document.documentElement.scrollWidth,
                      price:!!ctrl.series.price,panes:ctrl.chart.panes().length,
                      bars:ctrl.bars.length,chartHeight:container.getBoundingClientRect().height,
                      hasCanvas:canvases.some(c=>c.getBoundingClientRect().height>0&&c.getBoundingClientRect().width>0),
                      focused:document.getElementById('chart-oscillator-focus').options.length,
                      navVisible:!document.getElementById('chart-oscillator-nav').hidden};
                """)
                print("CHART_INDICATORS_ALL_ENABLED", width, json.dumps(result), flush=True)
                assert result["bars"] > 180 and result["price"] and result["hasCanvas"]
                assert 1 <= result["panes"] <= 4, "Cannot add unlimited oscillator panes"
                assert result["chartHeight"] >= 540
                assert result["navVisible"] and result["focused"] >= 10
                assert result["pageWidth"] <= result["width"] + 3
                driver.execute_script("""
                    const s=document.getElementById('chart-oscillator-focus');
                    s.value='macd';s.dispatchEvent(new Event('change',{bubbles:true}));
                """)
                assert driver.execute_script("return !!window.__qaChart.series.price && window.__qaChart.chart.panes().length<=4")
                errors = [x for x in driver.get_log("browser") if x["level"] == "SEVERE"]
                assert not errors, errors[:3]
            print("FINQUERY_MULTIPLE_INDICATOR_BROWSER_PASS", flush=True)
        finally:
            driver.quit()
            server.shutdown()


if __name__ == "__main__":
    run()
