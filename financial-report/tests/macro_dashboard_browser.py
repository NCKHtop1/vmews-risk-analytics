#!/usr/bin/env python3
"""Visual contract for the real Macro section at mobile and desktop widths.

Uses deterministic source-shaped fixtures; separate release tests check live
VBMA/World Bank retrieval. No credentials or production auth are bypassed.
"""
import json
import shutil
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def build_fixture(directory: Path):
    preview = directory / "index.html"
    original = (FRONT / "index.html").read_text(encoding="utf-8")
    segment = original.split('<section id="macro"', 1)[1].split('<button id="ai-fab"', 1)[0]
    html = (
        '<!doctype html><html lang="vi" data-hosting="pages"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="stylesheet" href="style.css"><link rel="stylesheet" href="market.css">'
        '<title>Macro ESG mobile QA</title></head><body><main style="max-width:1170px;margin:auto">'
        '<section id="macro"' + segment + "</main>"
        '<script src="section-collapse.js"></script><script src="workspace-tabs.js"></script>'
        '<script src="macro-dashboard.js"></script>'
        '<script src="macro.js"></script>'
        '<script src="liquidity-derivatives.js"></script></body></html>'
    )
    preview.write_text(html, encoding="utf-8")
    for file in ("style.css", "market.css", "section-collapse.js", "workspace-tabs.js", "macro-dashboard.js", "macro.js", "liquidity-derivatives.js"):
        shutil.copy2(FRONT / file, directory / file)
    data_dir = directory / "market"
    data_dir.mkdir()
    month = lambda date: {"Cột 1": date}
    macro = {
        "status": "ok",
        "checkedAt": "2026-10-23T01:58:17+00:00",
        "sources": [
            {"id": k, "status": "ok", "qualityStatus": "ok", "url": "https://vbma.org.vn/"}
            for k in ("pmi", "money_supply", "credit_sector", "fdi")
        ] + [{"id": "esg_world_bank", "status": "cached",
              "url": "https://esgdata.worldbank.org/data/countries?iso3=VNM"}],
        "datasets": {
            "pmi": {"title": "PMI theo tháng", "source": "VBMA", "status": "ok", "qualityStatus": "ok",
                    "columns": ["Cột 1", "T7 2026", "T8 2026", "T9 2026"],
                    "rows": [{"Cột 1": "PMI", "T7 2026": 52.9, "T8 2026": 53.3, "T9 2026": 51.9}]},
            "money_supply": {"title": "Tổng cung tiền", "source": "VBMA", "status": "ok", "qualityStatus": "ok",
                             "columns": ["Cột 1", "M2 (tỷ VND)"],
                             "rows": [{"Cột 1": "T5 2026", "M2 (tỷ VND)": 19974985},
                                      {"Cột 1": "T6 2026", "M2 (tỷ VND)": 20414616},
                                      {"Cột 1": "T7 2026", "M2 (tỷ VND)": 20455644}]},
            "credit_sector": {"title": "Dư nợ tín dụng", "source": "VBMA", "status": "ok", "qualityStatus": "ok",
                              "columns": ["Cột 1", "Tổng dư nợ"],
                              "rows": [{"Cột 1": "T5 2026", "Tổng dư nợ": 19703851},
                                       {"Cột 1": "T6 2026", "Tổng dư nợ": 20150411},
                                       {"Cột 1": "T7 2026", "Tổng dư nợ": 20262110}]},
            "fdi": {"title": "FDI", "source": "VBMA", "status": "ok", "qualityStatus": "ok",
                    "columns": ["Cột 1", "FDI giải ngân (lũy kế năm) (tỷ USD)"],
                    "rows": [{"Cột 1": "T7 2026", "FDI giải ngân (lũy kế năm) (tỷ USD)": 15.2},
                             {"Cột 1": "T8 2026", "FDI giải ngân (lũy kế năm) (tỷ USD)": 17.25},
                             {"Cột 1": "T9 2026", "FDI giải ngân (lũy kế năm) (tỷ USD)": 21.07}]},
            "esg_world_bank": {"title": "World Bank ESG", "source": "World Bank", "status": "cached",
                               "columns": ["Year", "AG.LND.FRST.ZS"],
                               "rows": [{"Year": 2021, "AG.LND.FRST.ZS": 46.96},
                                        {"Year": 2022, "AG.LND.FRST.ZS": 47.2},
                                        {"Year": 2023, "AG.LND.FRST.ZS": 47.44}]},
        }
    }
    esg = {"status":"ok","checkedAt":"2026-10-23T01:58:17+00:00","companies": {"MBB": {"canonicalMetrics": [
        {"metricId": "green_credit", "label": "Dư nợ tín dụng xanh", "year": 2025,
         "value": 68501, "unit": "billion VND", "pillar": "E", "sourceUrl": "https://example.com/mbb.pdf"}
    ]}}}
    (data_dir / "macro.json").write_text(json.dumps(macro, ensure_ascii=False), encoding="utf-8")
    (data_dir / "company-esg.json").write_text(json.dumps(esg, ensure_ascii=False), encoding="utf-8")


def run():
    with tempfile.TemporaryDirectory(prefix="finquery-macro-visual-") as tmp:
        directory = Path(tmp)
        build_fixture(directory)

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=tmp, **kwargs)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        options = Options()
        for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                     "--hide-scrollbars", "--window-size=1280,900"):
            options.add_argument(flag)
        driver = webdriver.Chrome(options=options)
        try:
            for width, height in ((1280, 920), (390, 844)):
                driver.set_window_size(width, height)
                driver.get(f"http://127.0.0.1:{server.server_port}/index.html?symbol=MBB")
                WebDriverWait(driver, 25).until(
                    lambda d: d.execute_script(
                        "return document.querySelectorAll('#macro-overview .macro-trend-svg').length === 4"
                        " && document.querySelectorAll('#macro-country-chart .macro-trend-svg').length === 1"
                    )
                )
                driver.execute_script("""
                    window.FinLiquidityDerivatives.setData(arguments[0]);
                """, {
                    "schemaVersion":1,"asOf":"2026-10-22",
                    "interbank":{"status":"secondary_source_crosschecked",
                        "source":"https://stockbiz.vn/vi-mo/du-lieu/lai-suat-lien-ngan-hang",
                        "observations":[{"date":"2026-10-21","value":3.39},{"date":"2026-10-22","value":4.31}]},
                    "derivatives":{"source":"https://www.gov.hnx.vn/vi-vn/chi-tiet-tin-60023563-0.html",
                        "months":[{"month":"2026-08","vn30":{"openInterest":27984,"avgVolume":228905},
                                   "vn100":{"openInterest":77,"avgVolume":66}},
                                  {"month":"2026-09","vn30":{"openInterest":39543,"avgVolume":219121},
                                   "vn100":{"openInterest":203,"avgVolume":259}}]},
                    "vbmaSwap":{"status":"awaiting_verified_source",
                               "source":"https://vbma.org.vn/csv/markets/charts/vi/fx_swap_curve.csv",
                               "points":[]}
                })
                report = driver.execute_script("""
                    const ids=['macro','macro-overview','macro-country-chart','macro-company-chart'];
                    const cards=[...document.querySelectorAll('.macro-viz-card')];
                    const viewport=window.innerWidth;
                    const rects=cards.map(el=>el.getBoundingClientRect());
                    return {
                      viewport,wide:document.documentElement.scrollWidth,
                      macroOpen:document.getElementById('macro-body')?.hidden===false,
                      fourCharts:document.querySelectorAll('#macro-overview svg').length,
                      worldCharts:document.querySelectorAll('#macro-country-chart svg').length,
                      singleYear:document.getElementById('macro-company-chart')?.textContent.includes('Năm 2025'),
                      cardsInside:rects.every(r=>r.left>=-2&&r.right<=viewport+2),
                      noExtraPIN:document.getElementById('macro-access-code')===null,
                      onRateChart:document.querySelectorAll('#money-on svg').length,
                      futuresCards:document.querySelectorAll('#money-futures .money-future-contract').length,
                      onValue:document.getElementById('money-on')?.textContent.includes('4,31'),
                      swapNoFake:document.getElementById('money-swap')?.textContent.includes('Chưa xác minh được') || document.querySelector('#money-swap .money-tenor-curve') !== null,
                      moneyWithin:[...document.querySelectorAll('.money-dashboard-grid .macro-viz-card, .money-future-contract')].every(el=>{
                        const r=el.getBoundingClientRect();return r.left>=-2&&r.right<=viewport+2;}),

                      titles:cards.map(x=>x.querySelector('h4')?.textContent)
                    };
                """)
                print(f"BROWSER_VISUAL_{width}", json.dumps(report, ensure_ascii=False), flush=True)
                assert not report["macroOpen"] and report["fourCharts"] == 4
                driver.execute_script("document.getElementById('macro-chevron').click()")
                assert driver.execute_script("return document.getElementById('macro-body').hidden") is False
                driver.execute_script("document.getElementById('macro-chevron').click()")
                assert driver.execute_script("return document.getElementById('macro-body').hidden") is True
                driver.execute_script("document.getElementById('macro-chevron').click()")
                assert report["worldCharts"] == 1 and report["singleYear"]
                assert report["cardsInside"] and report["wide"] <= report["viewport"] + 3
                assert report["onRateChart"]==1 and report["onValue"] and report["swapNoFake"]
                driver.execute_script("window.FinWorkspaceTabs.openMacro('on')")
                WebDriverWait(driver,5).until(lambda d:d.execute_script("return !document.getElementById('macro-panel-on').hidden"))
                overlap=driver.execute_script("""
                   const labels=[...document.querySelectorAll('#money-on svg [data-on-tick]')].map(el=>el.getBoundingClientRect());
                   return labels.slice(1).every((r,i)=>r.left>=labels[i].right+2);
                """)
                assert overlap, "ON chart x-axis labels overlap"
                assert report["moneyWithin"]
                assert report["noExtraPIN"]
                driver.save_screenshot(str(directory / f"macro_esg_{width}.png"))
                # The details panel should still display the legacy full-data tools on demand.
                driver.execute_script("window.FinWorkspaceTabs.openMacro('esg'); document.getElementById('macro-explore').open=true")
                WebDriverWait(driver, 8).until(
                    lambda d: d.execute_script("return document.getElementById('macro-tabs').children.length > 0")
                )
            print("FINQUERY_MACRO_ESG_BROWSER_VISUAL_PASS", flush=True)
        finally:
            driver.quit()
            server.shutdown()


if __name__ == "__main__":
    run()
