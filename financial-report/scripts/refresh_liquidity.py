#!/usr/bin/env python3
"""Safe standalone FinQuery ON/FX-swap source refresh (no market model writes).

Publishes only proven source observations to market/finquery-liquidity.json.
Never synthesizes an ON rate, FX swap point or an HNX futures volume.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from research_feeds_shadow import parse_vbma_csv

ON_URL = "https://stockbiz.vn/vi-mo/du-lieu/lai-suat-lien-ngan-hang"
ON_CROSS = "https://dulieukinhte.com/du-lieu-dong/lai-suat-thi-truong-lien-ngan-hang-qua-dem-34248"
SWAP_URL = "https://vbma.org.vn/csv/markets/charts/vi/fx_swap_curve.csv"
VN = timezone(timedelta(hours=7))
UA = "FinQueryDataQuality/1.0 (+https://finquery.info.vn/)"
TENORS = ["ON", "1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y"]

class ExtractText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.data = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip and data.strip(): self.data.append(data.strip())
    @property
    def text(self):
        return " ".join(self.data)

def fetch(url, timeout=12):
    allowed = {ON_URL, ON_CROSS, SWAP_URL}
    if url not in allowed:
        raise ValueError("Not an approved feed")
    with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/csv"}), timeout=timeout) as resp:
        if resp.geturl().split("?")[0] not in allowed:
            raise ValueError("Source redirected")
        raw = resp.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Response too large")
        return raw

def parse_on_history(html, reference=None):
    p=ExtractText();p.feed(html.decode("utf-8-sig", errors="replace"))
    text=re.sub(r"\s+", " ", p.text)
    # Only read the dated history table, never an unrelated interest-rate widget.
    marker=text.find("Số liệu các kỳ gần đây")
    if marker<0:
        raise ValueError("Missing dated ON history section")
    region=text[marker:marker+10000]
    pattern=re.compile(r"(?<!\d)(\d{2})/(\d{2})/(20\d{2})\s+(\d{1,2}(?:[.,]\d{1,3})?)\s*%")
    today=(reference or datetime.now(VN).date())
    observed={}
    for day,month,year,rate in pattern.findall(region):
        try: dt=date(int(year),int(month),int(day))
        except ValueError: continue
        value=float(rate.replace(",","."))
        if 0<=value<=25 and dt<=today and (today-dt).days<200:
            observed[dt.isoformat()]={"date":dt.isoformat(),"value":value}
    points=[observed[k] for k in sorted(observed)]
    if len(points)<2:
        raise ValueError("Insufficient dated ON observations")
    if (today-date.fromisoformat(points[-1]["date"])).days>14:
        raise ValueError("ON source too stale")
    return points

def verify_crosscheck(html, point):
    p=ExtractText();p.feed(html.decode("utf-8-sig", errors="replace"))
    content=p.text
    day=date.fromisoformat(point["date"])
    name=day.strftime("%d-%m-%Y")
    rate=str(point["value"]).replace(".",",")
    # Comparator must actually contain the day and rate in its published table.
    pos=content.find(name)
    if pos<0: return False
    near=content[max(0,pos-500):pos+16000]
    return rate in near or f"{point['value']:.2f}".replace(".",",") in near

def parse_swap_verified(raw, asof):
    """Only a strict, dated, unit-labelled swap-points table may become public."""
    parsed=parse_vbma_csv(raw)
    cols=parsed.get("columns",[])
    # The VBMA published dataset may be a rate curve instead of swap points.
    # A unit must be explicit: do not convert FX rate/forward price into points.
    header=" ".join(cols).casefold()
    if not re.search(r"\b(?:swap\s*points?|pips?|điểm\s*(?:hoán\s*đổi|swap))\b",header,re.I):
        return None
    tenors={c.upper():c for c in cols if c.upper() in TENORS}
    if len(tenors)<3:
        return None
    date_columns=[c for c in cols if re.search(r"(date|ngày|asof)",c,re.I)]
    if not date_columns:
        return None
    candidates=[]
    for row in parsed.get("rows",[]):
        stamp=str(row.get(date_columns[0]) or "").strip()
        formats=("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y")
        observation=None
        for f in formats:
            try: observation=datetime.strptime(stamp,f).date();break
            except ValueError: continue
        if not observation or observation>asof or (asof-observation).days>7:
            continue
        points=[]
        for tenor in TENORS:
            key=tenors.get(tenor)
            if not key: continue
            value=str(row.get(key) or "").strip()
            if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?",value):continue
            number=float(value)
            if abs(number)>100000:continue
            points.append({"tenor":tenor,"value":number})
        if len(points)>=3:
            candidates.append((observation,points))
    if not candidates: return None
    observation,points=max(candidates,key=lambda x:x[0])
    return {"status":"verified","unit":"swap points","measurement":"FX Swap MID points",
            "asOf":observation.isoformat(),"points":points}

def refresh(snapshot, fetcher=fetch, allow_swap_publication=False, clock=None):
    today=clock or datetime.now(VN).date()
    updated=json.loads(json.dumps(snapshot))
    updated["lastCheckedAt"]=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    issues=[]
    # ON: retain last trusted source date when source unavailable, never publish an unverified jump.
    try:
        new=parse_on_history(fetcher(ON_URL),today)
        last=new[-1]
        if not verify_crosscheck(fetcher(ON_CROSS),last):
            raise ValueError("Latest ON observation did not match independent source")
        old=updated["interbank"].get("observations",[])
        merged={r["date"]:r for r in old+new if isinstance(r.get("value"),(int,float))}
        updated["interbank"]["observations"]=[merged[k] for k in sorted(merged)][-180:]
        updated["interbank"]["asOf"]=last["date"]
        updated["interbank"]["status"]="secondary_source_crosschecked"
        updated["asOf"]=max(updated.get("asOf",""),last["date"])
    except Exception as exc:
        issues.append("ON "+type(exc).__name__+": "+str(exc)[:110])
    # Swap ingestion is license-gated and strictly accepts dated SWAP POINTS (not interest rates).
    try:
        raw=fetcher(SWAP_URL)
        parsed=parse_swap_verified(raw,today)
        if parsed and allow_swap_publication:
            updated["vbmaSwap"].update(parsed)
            updated["vbmaSwap"]["licenseStatus"]="approved"
        elif parsed:
            issues.append("VBMA licensing approval required for source publication")
        else:
            issues.append("VBMA source unit/date schema not verified")
    except Exception as exc:
        issues.append("VBMA "+type(exc).__name__+": "+str(exc)[:110])
    updated["sourceIssues"]=issues[:6]
    return updated

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--snapshot",required=True)
    args=parser.parse_args()
    path=Path(args.snapshot)
    raw=json.loads(path.read_text(encoding="utf-8"))
    # Never let an unaudited env var silently grant distribution rights.
    updated=refresh(raw,allow_swap_publication=raw.get("vbmaSwap",{}).get("licenseStatus")=="approved")
    pending=path.with_suffix(".tmp")
    pending.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    pending.replace(path)
    print(json.dumps({"on":updated["interbank"]["asOf"],
                      "hnx":updated["derivatives"]["lastMonth"],
                      "swap":updated["vbmaSwap"]["status"],
                      "issues":updated["sourceIssues"]},ensure_ascii=False))

if __name__=="__main__":main()
