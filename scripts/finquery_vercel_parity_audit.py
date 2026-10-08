#!/usr/bin/env python3
"""Independent HTTP/data parity audit: deployed GitHub Pages vs Vercel facade."""
import concurrent.futures
import hashlib
import html.parser
import json
import os
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

ORIGIN = "https://nckhtop1.github.io/vmews-risk-analytics/financial-report"
VERCEL = "https://finquery-web.vercel.app"
ROOT_GITHUB = "https://nckhtop1.github.io/vmews-risk-analytics"
TIMEOUT = 25
BASE_PATHS = [
    "/", "/index.html", "/favicon.svg",
    "/style.css", "/market.css", "/risk-monitor.css", "/fonts.css",
    "/app.js", "/market-data.js", "/market.js", "/risk-monitor.js",
    "/research-agent.js", "/research-ai.js", "/chart-engine.js",
    "/technical-scanner.js", "/strategy-intelligence.js",
    "/strategy-intelligence-core.js", "/strategy-engine.js",
    "/alert-center.js", "/insights.js", "/macro.js", "/metrics.js",
    "/knowledge-base.js", "/dashboard.js", "/xlsx.js",
    "/data/manifest.json", "/data/companies.json",
    "/data/insights-status.json", "/deployment.json",
    "/market/quotes.json", "/market/universe.json",
    "/market/technical-signals.json", "/market/strategy-indicators.json",
    "/market/risk-monitor.json", "/market/market-risk-calibration.json",
    "/market/sector-risk-calibration.json",
    "/market/news-latest.json", "/market/news-company-latest.json",
    "/market/news-brief.json", "/market/news-sentiment.json",
    "/market/macro.json", "/market/intraday-status.json",
    "/market/watchlist.json", "/market/market-status.json",
    "/vendor/lightweight-charts-5.0.9.js",
]
REQUIRED = {
    "/", "/index.html", "/market/quotes.json", "/market/universe.json",
    "/market/technical-signals.json", "/market/strategy-indicators.json",
    "/market/risk-monitor.json", "/market/news-latest.json",
    "/market/news-company-latest.json", "/market/intraday-status.json",
    "/deployment.json", "/data/manifest.json", "/data/companies.json",
}
records = []
def request(url, retries=1):
    last = None
    for attempt in range(retries+1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"FinQuery-Audit/1.0", "Accept":"*/*"})
            with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
                b=r.read()
                return {"code":r.status,"url":r.url,"bytes":len(b),"sha":hashlib.sha256(b).hexdigest(),
                        "data":b, "content_type":r.headers.get("Content-Type",""),
                        "cache":r.headers.get("Cache-Control",""),"age":r.headers.get("Age",""),
                        "vercel_cache":r.headers.get("X-Vercel-Cache","")}
        except urllib.error.HTTPError as e:
            body=e.read()
            return {"code":e.code,"url":url,"bytes":len(body),"sha":hashlib.sha256(body).hexdigest(),
                    "data":body, "content_type":e.headers.get("Content-Type",""),
                    "cache":e.headers.get("Cache-Control",""),"age":e.headers.get("Age",""),
                    "vercel_cache":e.headers.get("X-Vercel-Cache","")}
        except Exception as e:
            last = str(e)
            if attempt < retries: time.sleep(0.6)
    return {"code":0,"error":last}
class Assets(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs=[]
    def handle_starttag(self, tag, attrs):
        d=dict(attrs)
        if tag=="script" and d.get("src"):self.refs.append(d["src"])
        if tag=="link" and d.get("href") and ("stylesheet" in d.get("rel","") or "icon" in d.get("rel","")):
            self.refs.append(d["href"])
def against(p):
    base1=ORIGIN+p
    base2=VERCEL+p
    a,b=concurrent.futures.ThreadPoolExecutor(max_workers=2).map(request, (base1,base2))
    comparable=a["code"]==b["code"]==200
    eq=comparable and a["sha"]==b["sha"]
    row={"path":p,"github":a["code"],"vercel":b["code"],"same_bytes":eq,"github_bytes":a.get("bytes"),"vercel_bytes":b.get("bytes"),
         "cache":b.get("cache"),"vercel_cache":b.get("vercel_cache"),"age":b.get("age"),"github_error":a.get("error"),"vercel_error":b.get("error")}
    if comparable and not eq:
        a2,b2=concurrent.futures.ThreadPoolExecutor(max_workers=2).map(request,(base1+"?finquery_audit=stable",base2+"?finquery_audit=stable"))
        row["retry_same_bytes"]=a2["code"]==b2["code"]==200 and a2.get("sha")==b2.get("sha")
    if p.endswith(".json") and a.get("code")==200:
        try:
            d=json.loads(a["data"])
            row["json_type"]=type(d).__name__
            row["sourceTime"]=d.get("sourceTime",d.get("checkedAt",d.get("generatedAt",d.get("latestSourceTime")))) if isinstance(d,dict) else None
            if p=="/market/quotes.json":
                row["quote_coverage"]=d.get("coverage")
                row["quote_status"]=d.get("status")
                row["quote_count"]=len(d.get("quotes") or {})
            if p=="/deployment.json":
                row["revisions"]=d
        except Exception as e:row["json_error"]=str(e)
    return row

def run():
    print("HTTP PARITY: origin="+ORIGIN+" Vercel="+VERCEL,flush=True)
    main=request(ORIGIN+"/")
    if main.get("code")!=200:
        print("BLOCKER origin inaccessible",main);return 2
    asset_scanner=Assets();asset_scanner.feed(main["data"].decode("utf-8","replace"))
    inline_refs=[urllib.parse.urlsplit(urllib.parse.urljoin(VERCEL+"/",p)).path for p in asset_scanner.refs if urllib.parse.urlsplit(urllib.parse.urljoin(VERCEL+"/",p)).netloc==urllib.parse.urlsplit(VERCEL).netloc]
    paths=sorted(set(BASE_PATHS+inline_refs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        records.extend(pool.map(against,paths))
    failures=[];warnings=[]
    for r in records:
        p=r["path"]
        state="EXACT" if r["same_bytes"] else "MISMATCH" if r["github"]==r["vercel"]==200 else "HTTP_DIFF" if r["github"]!=r["vercel"] else "NOT_PUBLISHED"
        if p in REQUIRED and state!="EXACT":
            if r.get("retry_same_bytes"):
                warnings.append("Live content changed between requests: "+p)
            else:failures.append("Required asset/data not byte-identical: "+p+" "+state)
        elif state=="MISMATCH":
            warnings.append("Optional content mismatch: "+p)
        elif state=="HTTP_DIFF":
            failures.append("Route status mismatch: "+p+" GitHub "+str(r["github"])+" Vercel "+str(r["vercel"]))
        print("ROUTE "+state+" "+p+" old="+str(r["github"])+" new="+str(r["vercel"])+
              " size="+str(r.get("github_bytes"))+"/"+str(r.get("vercel_bytes"))+
              " vcache="+str(r.get("vercel_cache"))+" ttl="+str(r.get("cache"))[:60]+
              " age="+str(r.get("age"))+
              (" time="+str(r.get("sourceTime")) if r.get("sourceTime") else ""), flush=True)
    forecast_root=request(VERCEL+"/forecast-final.html")
    forecast_original=request(ROOT_GITHUB+"/forecast-final.html")
    forecast={"github":forecast_original.get("code"),"vercel":forecast_root.get("code"),
              "same_bytes":forecast_root.get("sha")==forecast_original.get("sha") and forecast_original.get("code")==200}
    print("FORECAST_ENTRY "+json.dumps(forecast),flush=True)
    if forecast_original.get("code")==200 and not forecast["same_bytes"]:
        failures.append("Forecast standalone route /forecast-final.html differs from GitHub root (broken internal navigation)")
    for p in ["/forecast-final-v12.js","/forecast-portfolio-v14.css","/solution-ai-v17.js",
              "/forecast-polish-v12.js","/forecast-freshness.js",
              "/forecast-portfolio-v14.js","/forecast-live-leaders-v14.js",
              "/forecast-deep-dive-v24.js","/forecast-final-v41.html",
              "/forecast-technical-radar-v41.js"]:
        a=request(ROOT_GITHUB+p);b=request(VERCEL+p)
        print("FORECAST_ASSET "+p+" "+str(a.get("code"))+"/"+str(b.get("code"))+" same="+str(a.get("sha")==b.get("sha")),flush=True)
        if a.get("code")==200 and (b.get("code")!=200 or a.get("sha")!=b.get("sha")):
            failures.append("Forecast dependency broken: "+p)
    # Substantive contract: the content should be the Pages build, not VMEWS.
    if b"<title>VMEWS" in main["data"]:
        failures.append("Origin unexpectedly served old VMEWS instead of FinQuery")
    if b"data-hosting=\"pages\"" not in main["data"]:
        warnings.append("Pages hosting marker absent: relative vs raw data loading might change")
    out={"origin":ORIGIN,"vercel":VERCEL,"checked":len(records),"exact":sum(bool(r["same_bytes"]) for r in records),
         "mismatched":sum(r["github"]==r["vercel"]==200 and not r["same_bytes"] for r in records),
         "missing_both":[r["path"] for r in records if r["github"]==r["vercel"]==404],
         "failure_count":len(failures),"warning_count":len(warnings),"failures":failures,"warnings":warnings,
         "records":records,"forecast":forecast}
    with open("finquery-parity-http-report.json","w",encoding="utf-8") as fp:json.dump(out,fp,ensure_ascii=False,indent=2)
    print("SUMMARY "+json.dumps({k:v for k,v in out.items() if k not in ("records",)},ensure_ascii=False),flush=True)
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a") as f:
            f.write("### FinQuery HTTP + data parity\n")
            f.write(f"{out['exact']}/{out['checked']} exact HTTP routes, {len(failures)} failures, {len(warnings)} warnings.\n\n")
            for v in failures:f.write("- FAIL: "+v+"\n")
            for v in warnings:f.write("- WARN: "+v+"\n")
    return 1 if failures else 0
if __name__=="__main__":
    sys.exit(run())
