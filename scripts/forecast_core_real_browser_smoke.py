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
        close: value("close"),
        chartTitle: value("chartTitle"),
        chartWidth: document.getElementById("chart")?.getBoundingClientRect()?.width || 0,
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
    if "đang tải" in status or "đang đồng bộ forecast core" in status or "đang tải forecast core" in status:
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
