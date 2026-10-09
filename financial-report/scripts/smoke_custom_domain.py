#!/usr/bin/env python3
"""Check HTTPS, routing, market data and canonical links on FinQuery's real domain."""
import json
import os
import sys
import ssl
import time
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

DOMAIN = "https://finquery.info.vn"
PAGES = "https://nckhtop1.github.io/vmews-risk-analytics"
HEADERS = {"User-Agent": "FinQuery-Real-Domain-Smoke/1.0", "Cache-Control": "no-cache", "Accept": "*/*"}

def read(url):
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=20, context=ssl.create_default_context()) as r:
            body = r.read(2_000_000)
            return r.status, r.url, r.headers, body
    except HTTPError as e:
        body = e.read(500)
        print("ERROR_RESPONSE", json.dumps({"url":url,"status":e.code,"headers":dict(e.headers),"body":body[:260].decode("utf-8","replace")}, ensure_ascii=False))
        raise

def check(label, url, validator):
    try:
        status, final, headers, body = read(url)
        assert status == 200, f"HTTP {status}"
        validator(body, final, headers)
        print("PASS", label, status, len(body), final, headers.get("content-type"))
        return body
    except Exception as e:
        print("FAIL", label, repr(e))
        raise

def html_contains(needle, require_app=False):
    def check_html(body, final, headers):
        assert urlparse(final).hostname == "finquery.info.vn", f"escaped domain: {final}"
        if require_app:
            assert urlparse(final).path == "/financial-report/index.html", f"wrong landing page: {final}"
        assert needle.lower().encode("utf8") in body.lower(), f"missing HTML marker {needle}"
        assert "text/html" in str(headers.get("content-type","")).lower(), "not HTML"
    return check_html

def parse_quote(body, final, headers):
    assert urlparse(final).hostname == "finquery.info.vn", f"quote redirected off custom domain {final}"
    d = json.loads(body)
    assert d.get("status")=="ok", f"status {d.get('status')}"
    count=len(d.get("quotes") or {})
    expected=int(d.get("expected") or 0)
    covered=int(d.get("coverage") or 0)
    assert expected>=100 and count>=0.95*expected and covered>=0.95*expected, f"coverage {count}/{expected}, {covered}"
    valid=sum(1 for row in d["quotes"].values() if isinstance(row,dict) and isinstance(row.get("price"),(int,float)) and row["price"]>0)
    assert valid >= 0.95*expected, f"positive prices {valid}/{expected}"
    assert d.get("latestSourceTime"), "quote source timestamp missing"
    return d

def main():
    try:
        print("DOMAIN_SMOKE_CHECK", datetime.now(timezone.utc).isoformat())
        # Route should retain canonical host after one or two same-origin redirects.
        check("home",DOMAIN+"/",html_contains("FinQuery", require_app=True))
        check("app",DOMAIN+"/financial-report/",html_contains("FinQuery", require_app=True))
        check("market app bundle",DOMAIN+"/financial-report/index.html",
              lambda b,u,h:(len(b)>100000 and b"FinMarketData" in b and b"FinQuery" in b) or (_ for _ in ()).throw(AssertionError("compiled FinQuery app missing")))
        _, _, _, src_content = read(PAGES+"/financial-report/market/quotes.json?smoke="+str(int(time.time())))
        src=json.loads(src_content)
        _, dom_final, _, dom_content = read(DOMAIN+"/financial-report/market/quotes.json?smoke="+str(int(time.time())))
        dom=parse_quote(dom_content,dom_final,{})
        lag=(datetime.fromisoformat(src["latestSourceTime"].replace("Z","+00:00"))-datetime.fromisoformat(dom["latestSourceTime"].replace("Z","+00:00"))).total_seconds()
        assert lag<=1500, f"quote delivery lag {lag:.0f}s"
        # Fail closed when a purportedly live quote feed itself goes stale
        # during Vietnamese trading hours. Off-hours keep the completed session.
        market_now=datetime.now(timezone(timedelta(hours=7)))
        minutes=market_now.hour*60+market_now.minute
        active=(market_now.weekday()<5 and
                (9*60+15<=minutes<=11*60+40 or 13*60<=minutes<=14*60+35))
        stamp=datetime.fromisoformat(dom["latestSourceTime"].replace("Z","+00:00"))
        source_age=(datetime.now(timezone.utc)-stamp).total_seconds()
        assert source_age >= -300, f"quote timestamp in future {source_age:.0f}s"
        if active:
            assert source_age <= 20*60, f"live quote feed stale {source_age:.0f}s"
        print("PASS quotes",dom["coverage"],"/",dom["expected"],"sourceLagSec",max(0,int(lag)),"feedAgeSec",int(source_age),"liveSession",active)
        check("news",DOMAIN+"/financial-report/market/news-latest.json",
              lambda b,u,h: json.loads(b).get("status")=="ok" or (_ for _ in ()).throw(AssertionError("news not ok")))
        check("forecast",DOMAIN+"/forecast-final.html",html_contains("forecast"))
        check("www", "https://www.finquery.info.vn/",html_contains("FinQuery", require_app=True))
        print("FINQUERY_CANONICAL_DOMAIN_SMOKE_PASS")
        return 0
    except Exception as e:
        print("::error::FinQuery canonical production route unavailable:",repr(e))
        return 1

if __name__=="__main__":
    sys.exit(main())
