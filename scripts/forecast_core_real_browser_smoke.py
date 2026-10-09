#!/usr/bin/env python3
"""End-to-end Forecast Core no-hang and nine-symbol navigation smoke on real domain.

The UI may explicitly withhold stale forecasts, but must finish loading, show a
recoverable error if data is unavailable, never print fake current-session
rankings, and never fail to navigate among the previously mismatched symbols.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

DOMAIN = os.environ.get("FINQUERY_FORECAST_URL", "https://finquery.info.vn/forecast-final.html")
DISPUTED = ("AGR", "ASP", "BTP", "C47", "EIB", "HDB", "LSS", "MIG", "TLD")
URL = DOMAIN + ("&" if "?" in DOMAIN else "?") + "symbol=FPT&smoke=forecast-core"
RESULTS = Path("forecast-core-browser-evidence")
RESULTS.mkdir(exist_ok=True)

def snapshot(driver):
    return driver.execute_script("""
      const value = id => document.getElementById(id)?.textContent?.trim() || "";
      return {
        url: location.href,
        status: value("status"),
        snapshot: value("snapshotDate"),
        decision: value("decision"),
        summary: value("summary"),
        close: value("close"),
        chartTitle: value("chartTitle"),
        chartWidth: document.getElementById("chart")?.getBoundingClientRect()?.width || 0,
        chartMode: document.getElementById("chart")?.dataset?.quoteMode || "",
        quoteAsOf: value("quoteAsOf"),
        loaderInstalled: typeof window.__VMEWS_LOAD_BASE__ === "function",
        renderInstalled: typeof window.__VMEWS_RENDER_SYMBOL__ === "function"
      };
    """)

def verify_ready(d):
    s = snapshot(d)
    if not s["renderInstalled"]:
        return False
    status = s["status"].lower()
    if not status:
        return False
    # The independent live quote arrives first. Do not mistake "price visible"
    # for a Forecast Core whose snapshot and decision are actually loaded.
    if ("đang tải" in status or "đang được tải" in status
            or "đang đồng bộ forecast core" in status):
        return False
    if s["snapshot"].upper() in ("", "ĐANG TẢI"):
        return False
    if s["decision"] in ("", "—"):
        return False
    return s

def render_symbol(driver, symbol):
    driver.set_script_timeout(18)
    result = driver.execute_async_script("""
      const symbol = arguments[0], done = arguments[arguments.length-1];
      Promise.resolve(window.__VMEWS_RENDER_SYMBOL__(symbol))
       .then(() => done({ok:true, symbol, chartTitle:document.getElementById("chartTitle")?.textContent || "",
                         status:document.getElementById("status")?.textContent || ""}))
       .catch(e => done({ok:false, symbol, error:String(e?.message||e)}));
    """, symbol)
    assert result.get("ok"), result
    assert symbol in result.get("chartTitle",""), result
    assert symbol in result.get("status",""), result
    return result

def main():
    options=Options()
    for arg in ("--headless=new","--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--window-size=1440,1100"):
        options.add_argument(arg)
    driver_path=shutil.which("chromedriver")
    service=Service(driver_path) if driver_path else Service()
    driver=webdriver.Chrome(service=service,options=options)
    driver.set_page_load_timeout(50)
    errors=[]
    try:
        driver.get(URL)
        loaded = WebDriverWait(driver,70, poll_frequency=.5).until(verify_ready)
        assert "thử tải lại" not in loaded["status"].lower(), "Forecast Core failed but stopped loading: "+str(loaded)
        assert loaded["chartWidth"] > 200, "Forecast chart never mounted"
        assert loaded["close"] not in ("","—","0"), "FPT price missing from Forecast page"
        assert loaded["snapshot"].upper() != "ĐANG TẢI", "snapshot date still loading"
        assert loaded["decision"] and "đang tải" not in loaded["decision"].lower(), "decision still spinning"
        errors.append({"initial": loaded})
        for symbol in DISPUTED:
            result = render_symbol(driver,symbol)
            errors.append({"symbol":symbol,"status":result["status"][:180]})
        driver.set_window_size(390,844)
        mobile=snapshot(driver)
        assert mobile["chartWidth"]>250, "mobile chart collapsed"
        assert "đang tải" not in mobile["status"].lower(), "mobile status stuck loading"
        # Regression: both market quote endpoints deliberately stall until their
        # own AbortController timeout. Already-verified Forecast Core must be
        # rendered without awaiting this OPTIONAL live quote fetch.
        hook=driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",{"source":"""
        (() => {
          const original=window.fetch.bind(window);
          window.fetch=(input,options)=> {
            const url=String(input?.url||input||"");
            if (url.includes("/market/quotes.json") || url.includes("/forecast-session-v21.json")) return new Promise((resolve,reject)=>{
              const signal=options?.signal;
              if (signal?.aborted) return reject(new DOMException("Aborted","AbortError"));
              signal?.addEventListener("abort",()=>reject(new DOMException("Aborted","AbortError")),{once:true});
            });
            return original(input,options);
          };
        })();
        """})
        try:
            t0=time.monotonic()
            driver.get(URL+"&blockedLive=1")
            blocked=WebDriverWait(driver,9,poll_frequency=.25).until(verify_ready)
            seconds=round(time.monotonic()-t0,2)
            assert blocked["chartWidth"]>200, f"Chart hidden while live feed blocked: {blocked}"
            # An audited EOD close is a real observation, not a fabricated live
            # quote. The expected behavior depends on the completed model date.
            # This test must reject fake live provenance in both branches.
            assert blocked["chartMode"] in ("HISTORICAL_ONLY","VERIFIED_EOD"), (
                f"Blocked live feeds presented an unverified live price: {blocked}")
            if blocked["chartMode"] == "VERIFIED_EOD":
                assert blocked["close"] not in ("","—","0"), f"Verified EOD close absent: {blocked}"
                assert "eod" in blocked["chartTitle"].lower(), f"Audited EOD provenance not displayed: {blocked}"
                assert "eod" in blocked["quoteAsOf"].lower(), f"EOD source date not labeled: {blocked}"
                assert "giá đóng cửa eod đã kiểm định" in blocked["summary"].lower(), f"Forecast interpretation incorrectly claims current live price: {blocked}"
            else:
                assert blocked["close"] in ("","—"), f"Stale core close was misrepresented as current: {blocked}"
                assert "lịch sử" in blocked["chartTitle"].lower(), f"Chart must label old data as historical: {blocked}"
                assert "không có giá live" in blocked["quoteAsOf"].lower(), f"Missing live feed not labeled: {blocked}"
                assert "KHÔNG CÓ GIÁ LIVE" in blocked["decision"], f"Expected historical-only decision: {blocked}"
            assert "thử tải lại" not in blocked["status"].lower(), f"Non-essential price feed broke Forecast Core: {blocked}"
            assert "đang tải" not in blocked["decision"].lower(), f"Forecast Core still loading after price probe failure: {blocked}"
            errors.append({"blockedLivePrice":blocked,"elapsedSec":seconds})
            print("FORECAST_CORE_BLOCKED_LIVE_PRICE_PASS",json.dumps({"elapsedSec":seconds,"snapshot":blocked},ensure_ascii=False))
        finally:
            driver.execute_cdp_cmd("Page.removeScriptToEvaluateOnNewDocument",{"identifier":hook["identifier"]})
        print("FORECAST_CORE_REAL_BROWSER_PASS",json.dumps({"url":URL,"symbols":list(DISPUTED),
              "initial":loaded,"mobile":mobile,"steps":errors},ensure_ascii=False,default=str))
        return 0
    except Exception as e:
        print("::error::FORECAST_CORE_REAL_BROWSER_FAIL",repr(e),"state",json.dumps(snapshot(driver),ensure_ascii=False))
        driver.save_screenshot(str(RESULTS/"forecast-core-failure.png"))
        (RESULTS/"forecast-core-last-state.json").write_text(json.dumps({"url":URL,"error":str(e),"steps":errors,"snapshot":snapshot(driver)},ensure_ascii=False,indent=2),encoding="utf8")
        return 1
    finally:
        driver.quit()

if __name__=="__main__":
    sys.exit(main())
