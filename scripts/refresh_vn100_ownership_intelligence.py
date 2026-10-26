#!/usr/bin/env python3
"""Collect point-in-time HOSE VN100 ownership facts and realized price reactions.

The issuer/exchange disclosure snapshot is authoritative when explicitly source-linked.
KBS provides reference ownership, shareholders and officers; Vietcap provides a
disclosure discovery index. Market reactions use only recorded EOD bars and never
claim a disclosure caused a return or that a registration was executed.
"""
from __future__ import annotations

import argparse
import bisect
import concurrent.futures
import hashlib
import json
import math
import re
import statistics
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
KBS = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stockinfo"
VCI = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/events"
VCI_COMPANY = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company"
HORIZONS = (1, 3, 5, 10)
EVENT_CODES = "DDIND,DDINS,DDRP"


def today():
    return datetime.now(VN).date()


def string(value, maxlen=190):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:maxlen]


def asday(value):
    s = str(value or "").strip()
    if not s:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        candidate = s[:10]
    elif re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        candidate = datetime.strptime(s, "%d/%m/%Y").date().isoformat()
    elif re.match(r"^\d{8}$", s):
        candidate = datetime.strptime(s, "%Y%m%d").date().isoformat()
    else:
        return ""
    try:
        value = date.fromisoformat(candidate)
        if value > today() or value.year < 1990:
            return ""
        return candidate
    except ValueError:
        return ""


def number(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        x = float(str(value).replace(",", ""))
        return x if math.isfinite(x) and x >= 0 else None
    except (TypeError, ValueError):
        return None


def safe_count(value):
    x = number(value)
    return int(x) if x is not None and x == int(x) else None


def norm(s):
    x = unicodedata.normalize("NFD", str(s or "").lower()).replace("đ", "d")
    return "".join(c for c in x if unicodedata.category(c) != "Mn")


def fetch_json(url, attempts=2, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; FinQuery source publisher)",
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.6",
        "Origin": "https://trading.vietcap.com.vn",
        "x-lang": "vi",
    })
    last = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    raise ValueError("Non-200 source response")
                if int(response.headers.get("Content-Length", 0)) > 8_000_000:
                    raise ValueError("Oversized source response")
                return json.loads(response.read(8_000_000))
        except (TimeoutError, urllib.error.URLError, ValueError, OSError, json.JSONDecodeError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError(type(last).__name__ if last else "Unknown source error")


def vci_url(symbol, page=0, from_date=None):
    start = from_date or (today() - timedelta(days=730)).strftime("%Y%m%d")
    params = {
        "ticker": symbol, "fromDate": start, "toDate": today().strftime("%Y%m%d"),
        "eventCode": EVENT_CODES, "page": page, "size": 100,
    }
    return VCI + "?" + urllib.parse.urlencode(params)


def fetch_company(symbol, fetch_events=True):
    out = {"symbol": symbol, "profile": None, "events": None, "profileOk": False,
           "eventsOk": False, "errors": []}
    try:
        profile = fetch_json(f"{KBS}/profile/{symbol}?l=1")
        if isinstance(profile, dict) and profile.get("SB") == symbol:
            out["profile"] = profile
            out["profileOk"] = True
            # Some KBS profiles encode percentage as scaled integers (HSG has
            # OR=1669 instead of 16.xx). Never guess a divisor. Fetch a
            # separately dated shareholder list from Vietcap when needed.
            valid = [row for row in (profile.get("Shareholders") or [])
                     if isinstance(row, dict) and string(row.get("NM")) and
                     number(row.get("OR")) is not None and
                     number(row.get("OR")) <= 100]
            if not valid:
                try:
                    alternate = fetch_json(f"{VCI_COMPANY}/{symbol}/shareholder")
                    items = alternate.get("data") if isinstance(alternate, dict) else None
                    if not isinstance(items, list):
                        raise ValueError("Missing Vietcap shareholders")
                    fallback = []
                    cutoff = (today() - timedelta(days=730)).isoformat()
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        disclosed = asday(item.get("publicDate"))
                        fraction = number(item.get("percentage"))
                        if (not disclosed or disclosed < cutoff or
                            fraction is None or fraction > 1 or fraction < 0.01):
                            continue
                        name = string(item.get("ownerName"))
                        if name:
                            fallback.append({
                                "name": name, "percentage": round(100*fraction, 4),
                                "shares": safe_count(item.get("quantity")),
                                "asOf": disclosed
                            })
                    fallback.sort(key=lambda x: (-x["percentage"], x["name"]))
                    if fallback:
                        profile["_fallbackShareholders"] = fallback
                        profile["_shareholdersSource"] = (
                            f"{VCI_COMPANY}/{symbol}/shareholder")
                except Exception as exc:
                    out["errors"].append("shareholders:" + type(exc).__name__)
        else:
            raise ValueError("Issuer profile symbol mismatch")
    except Exception as exc:
        out["errors"].append("profile:" + type(exc).__name__)
    if not fetch_events:
        return out
    try:
        rows = []
        for page in range(3):
            response = fetch_json(vci_url(symbol, page))
            data = response.get("data") or {}
            if not isinstance(data, dict):
                raise ValueError("Unexpected Vietcap data")
            part = data.get("content")
            if not isinstance(part, list):
                raise ValueError("Missing Vietcap content")
            rows.extend(part)
            total = int(data.get("totalElements") or 0)
            if len(part) < 100 or (total and len(rows) >= total):
                break
        out["events"] = rows
        out["eventsOk"] = True
    except Exception as exc:
        out["errors"].append("events:" + type(exc).__name__)
    return out


def profile_sections(symbol, source):
    if not isinstance(source, dict):
        return None
    asof = asday(source.get("AD"))
    leaders = []
    for row in (source.get("Leaders") or [])[:60]:
        if not isinstance(row, dict):
            continue
        name = string(row.get("NM"))
        role = string(row.get("PN"), 100)
        if name and role:
            leaders.append({"name": name, "role": role})
    shareholders = []
    for row in (source.get("Shareholders") or [])[:45]:
        if not isinstance(row, dict):
            continue
        name = string(row.get("NM"))
        d = asday(row.get("D"))
        ratio = number(row.get("OR"))
        if name and ratio is not None and ratio <= 100:
            shareholders.append({
                "name": name, "percentage": round(ratio, 4),
                "shares": safe_count(row.get("V")), "asOf": d
            })
    shareholder_source = ""
    if not shareholders and source.get("_fallbackShareholders"):
        shareholders = source["_fallbackShareholders"][:45]
        shareholder_source = str(source.get("_shareholdersSource") or "")
    ownership = []
    for row in (source.get("Ownership") or [])[:30]:
        if not isinstance(row, dict):
            continue
        name = string(row.get("NM"))
        ratio = number(row.get("OR"))
        if name and ratio is not None and ratio <= 100:
            ownership.append({
                "name": name, "percentage": round(ratio, 4),
                "shares": safe_count(row.get("SH")), "asOf": asday(row.get("D"))
            })
    return {
        "asOf": asof, "leaders": leaders, "shareholders": shareholders,
        "shareholdersSource": shareholder_source,
        "ownership": ownership,
        "source": f"{KBS}/profile/{symbol}?l=1",
        "sourceName": "KBS"
    }


def event_type(title, action):
    t = norm(title)
    buy = "mua" in norm(action) or re.search(r"\b(mua|buy)\b", t)
    sell = "ban" in norm(action) or re.search(r"\b(ban|sell)\b", t)
    is_result = any(z in t for z in ("bao cao ket qua", "ket qua giao dich", "da mua", "da ban", "hoan tat"))
    is_register = any(z in t for z in ("dang ki", "dang ky", "dangki", "dangky"))
    if is_result and buy and not sell:
        return "executed_buy"
    if is_result and sell and not buy:
        return "executed_sell"
    if is_register and buy and not sell:
        return "registered_buy"
    if is_register and sell and not buy:
        return "registered_sell"
    return "reported_result" if is_result else "reported_registration"


def parse_vci_event(symbol, row):
    if not isinstance(row, dict) or str(row.get("ticker") or row.get("organCode") or "").upper() != symbol:
        return None
    if str(row.get("eventCode") or "") not in ("DDIND", "DDINS", "DDRP"):
        return None
    d = asday(row.get("publicDate"))
    title = string(row.get("eventTitleVi") or row.get("eventTitleEn"), 270)
    if not d or not title:
        return None
    typ = event_type(title, row.get("actionTypeVi") or row.get("actionTypeEn"))
    person = string(title.split(" - ")[0].strip(), 150) if " - " in title else ""
    if not person or person == title:
        person = string(row.get("eventNameVi") or "Người/tổ chức liên quan")
    # Only parse a shares count when the ticker immediately follows the number in the
    # source title. A generic number in a title is never assumed to be a share count.
    pattern = r"(?<![\w])(\d[\d.,]{0,17})\s+" + re.escape(symbol) + r"\b"
    match = re.search(pattern, title, re.IGNORECASE)
    quantity = None
    if match:
        raw = match.group(1).replace(",", "").replace(".", "")
        if raw.isdigit():
            quantity = safe_count(raw)
    category = str(row.get("eventCode"))
    source = vci_url(symbol)
    eventid = string(row.get("id"), 80)
    if not eventid:
        eventid = hashlib.sha1(f"{symbol}:{d}:{title}".encode()).hexdigest()[:20]
    return {
        "id": "VCI-" + eventid, "symbol": symbol,
        "person": person,
        "role": "Người liên quan" if category == "DDRP" else "Người nội bộ / cổ đông lớn",
        "type": typ, "disclosedAt": d + "T12:00:00+07:00",
        "date": d, "title": title, "quantity": quantity,
        "holdingsAfter": None, "sourceUrl": source,
        "sourcePublisher": "Vietcap", "sourceQuality": "aggregated",
        "sourceEventId": eventid
    }


def market_bars(market, symbol):
    file = market / "history" / f"{symbol}.json"
    if not file.exists():
        return []
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = {}
    for item in raw.get("bars") or []:
        day = asday(item.get("time") or item.get("date"))
        price = number(item.get("close"))
        vol = number(item.get("volume"))
        if day and price and price > 0:
            rows[day] = {"date": day, "close": price, "volume": vol or 0}
    return [rows[k] for k in sorted(rows)]


def reaction(event, bars):
    d = event.get("date") or asday(event.get("disclosedAt"))
    if not d or len(bars) < 30:
        return {"status": "unavailable"}
    days = [r["date"] for r in bars]
    i = bisect.bisect_right(days, d) - 1
    if i < 19 or i >= len(bars):
        return {"status": "unavailable"}
    base = bars[i]["close"]
    if base <= 0:
        return {"status": "unavailable"}
    changes = {}
    for h in HORIZONS:
        if i + h < len(bars):
            changes[str(h)] = round(100 * (bars[i+h]["close"] / base - 1), 2)
        else:
            changes[str(h)] = None
    pre = [x["volume"] for x in bars[max(0, i-19):i+1] if x["volume"] > 0]
    vols = [x["volume"] for x in bars[i+1:min(len(bars), i+4)] if x["volume"] > 0]
    volume_ratio = round(statistics.mean(vols) / statistics.mean(pre), 2) if len(pre)>=12 and vols else None
    r3 = changes["3"]
    signal = "CHO_DU_LIEU"
    if r3 is not None:
        # Purely observed reaction, not a trading recommendation.
        if volume_ratio is not None and volume_ratio >= 1.2 and r3 >= 2:
            signal = "TANG_KEM_THANH_KHOAN"
        elif volume_ratio is not None and volume_ratio >= 1.2 and r3 <= -2:
            signal = "GIAM_KEM_THANH_KHOAN"
        elif abs(r3) <= 1:
            signal = "DI_NGANG"
        else:
            signal = "THEO_DOI"
    return {
        "status": "observed" if changes["1"] is not None else "pending",
        "anchorDate": days[i], "close": base, "returnPct": changes,
        "volumeRatio3": volume_ratio, "signal": signal
    }


def is_source_event(row, symbol):
    if not isinstance(row, dict) or row.get("symbol") != symbol:
        return False
    if not asday(row.get("disclosedAt")) or not row.get("title"):
        return False
    url = str(row.get("sourceUrl") or "")
    return url.startswith(("https://www.hsx.vn/", "https://staticfile.hsx.vn/",
                           "https://www.mbbank.com.vn/","https://mbbank.com.vn/"))


def normalize_seed(row):
    x = dict(row)
    x["date"] = asday(x.get("disclosedAt"))
    x["sourceQuality"] = "issuer_or_exchange"
    return x


def build(core, market, output, limit=None, previous=None):
    core_list = json.loads(Path(core).read_text(encoding="utf-8"))
    expected = [x["symbol"] for x in core_list if x.get("exchange")=="HOSE"]
    if len(expected) != 100 or len(set(expected)) != 100:
        raise RuntimeError("VN100 HOSE core is not 100 unique symbols")
    symbols = expected[:limit] if limit else expected
    old = {}
    if previous and Path(previous).exists():
        try:
            old = json.loads(Path(previous).read_text(encoding="utf-8")).get("symbols") or {}
        except (ValueError, OSError):
            old = {}
    source_file = Path(market) / "ownership-disclosures.json"
    issuer_events = json.loads(source_file.read_text(encoding="utf-8")).get("events", []) if source_file.exists() else []
    # The discovery API sometimes rate-limits sustained requests. Publish all 100
    # source profiles every run, but rotate event queries across the least recently
    # successful issuers. A missed request is not evidence that no event exists.
    quota = len(symbols) if limit else min(len(symbols), 48)
    priority = sorted(symbols, key=lambda symbol: (
        bool((old.get(symbol) or {}).get("lastEventsSuccess")),
        str((old.get(symbol) or {}).get("lastEventsSuccess") or ""),
        symbols.index(symbol),
    ))
    event_symbols = set(priority[:quota])
    fresh = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch_company, symbol, symbol in event_symbols): symbol for symbol in symbols}
        for future in concurrent.futures.as_completed(futures):
            sym = futures[future]
            fresh[sym] = future.result()
            p = fresh[sym]
            print(json.dumps({"symbol": sym, "profile": p["profileOk"], "events": p["eventsOk"],
                              "eventCount": len(p["events"] or []), "errors": p["errors"]},ensure_ascii=False),flush=True)
    records = {}
    successes = 0
    event_successes = 0
    event_available = 0
    total_events = 0
    reactions = 0
    for symbol in symbols:
        incoming = fresh[symbol]
        prev = old.get(symbol) or {}
        profile = profile_sections(symbol, incoming["profile"]) if incoming["profileOk"] else prev.get("profile")
        if incoming["profileOk"]:
            successes += 1
        retained_vci = [x for x in prev.get("events") or []
                        if str(x.get("id","")).startswith("VCI-")]
        if incoming["eventsOk"]:
            event_successes += 1
            fetched_vci = [item for item in
                           (parse_vci_event(symbol, row) for row in incoming["events"])
                           if item]
            vci = fetched_vci + retained_vci
        else:
            vci = retained_vci
        if incoming["eventsOk"] or prev.get("lastEventsSuccess"):
            event_available += 1
        issuer = [normalize_seed(x) for x in issuer_events if is_source_event(x,symbol)]
        published = issuer + vci
        dedup = {}
        for event in published:
            if not event.get("date"):
                event["date"] = asday(event.get("disclosedAt"))
            key = event.get("id") or hashlib.sha1(json.dumps(event,sort_keys=True).encode()).hexdigest()
            if key not in dedup:
                dedup[key] = event
        bars = market_bars(Path(market), symbol)
        rows = sorted(dedup.values(), key=lambda x:x.get("date") or "",reverse=True)[:90]
        for event in rows:
            event["reaction"] = reaction(event,bars)
            reactions += event["reaction"]["status"]=="observed"
        total_events += len(rows)
        records[symbol] = {
            "symbol":symbol, "name": next((x["name"] for x in core_list if x["symbol"]==symbol),symbol),
            "profile":profile,
            "events":rows,
            "priceAsOf":bars[-1]["date"] if bars else None,
            "lastEventsSuccess":today().isoformat() if incoming["eventsOk"] else
                prev.get("lastEventsSuccess"),
            "sourceStatus":{
                "profile": "ok" if incoming["profileOk"] else ("retained" if profile else "unavailable"),
                "events": "ok" if incoming["eventsOk"] else
                    ("retained" if prev.get("lastEventsSuccess") else
                     ("unavailable" if symbol in event_symbols else "not_checked")),
                "market": "ok" if len(bars)>=30 else "unavailable",
            }
        }
    fetched = len(symbols)
    report = {
        "schemaVersion": 2, "status": "ok" if fetched==100 and successes>=90 and
            all(records[symbol]["sourceStatus"]["market"]=="ok" for symbol in symbols)
            else "partial",
        "asOf":today().isoformat(), "checkedAt":datetime.now(VN).isoformat(timespec="seconds"),
        "universe":{"expected":100,"processed":fetched,"profileFresh":successes,
                    "eventSourceFresh":event_successes,
                    "eventSourceAvailable":event_available,
                    "eventSourceQueried":len(event_symbols),
                    "profileAvailable":sum(bool(v["profile"]) for v in records.values()),
                    "historyAvailable":sum(v["sourceStatus"]["market"]=="ok" for v in records.values()),
                    "symbolsWithEvents":sum(bool(v["events"]) for v in records.values()),
                    "events":total_events,"eventsWithPriceReaction":reactions},
        "symbols":records
    }
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(report,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print("COVERAGE",json.dumps(report["universe"],ensure_ascii=False),flush=True)
    if successes==0 and event_successes==0:
        raise RuntimeError("No live ownership source responded; refusing to publish")
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--core",default="financial-report/data/companies.json")
    parser.add_argument("--market",required=True)
    parser.add_argument("--previous",default=None)
    parser.add_argument("--output",required=True)
    parser.add_argument("--limit",type=int,default=0)
    args=parser.parse_args()
    build(args.core,Path(args.market),Path(args.output),args.limit or None,args.previous)


if __name__=="__main__":
    main()
