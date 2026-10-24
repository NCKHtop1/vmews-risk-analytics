#!/usr/bin/env python3
"""Read-only delayed HNX futures quotes from the same KBS market source as stocks.

The 5-minute existing market publisher calls this as an OPTIONAL sidecar.
Never invent a match timestamp, rebrand collection time as trade time, or write
futures to HOSE equity quotes, strategy or risk snapshots.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
BASE = "https://kbbuddywts.kbsec.com.vn/iis-server/investment"
SOURCE = "https://kbbuddywts.kbsec.com.vn/"
KRX = re.compile(r"^41(I[12])([0-9A-HJ-NP-TV-W])([1-9ABC])000$")
SYMBOL = re.compile(r"^(VN30|VN100)F(2[0-9])(0[1-9]|1[0-2])$")
ALPHABET = "ABCDEFGHJKLMNPQRSTVW"
MONTH_CODE = {**{m: str(m) for m in range(1, 10)}, 10: "A", 11: "B", 12: "C"}
NOW = lambda: datetime.now(timezone.utc)


def year_code(y):
    index = (y - 2010) % 30
    return str(index) if index < 10 else ALPHABET[index - 10]


def krx_code(underlying, year, month):
    return "41" + ("I1" if underlying == "VN30" else "I2") + year_code(year) + MONTH_CODE[month] + "000"


def third_thursday(year, month):
    first = date(year, month, 1)
    return first + timedelta(days=(3 - first.weekday()) % 7 + 14)


def parse_contract(code, today=None):
    today = today or datetime.now(VN).date()
    code = str(code or "").strip().upper()
    m = SYMBOL.fullmatch(code)
    if m:
        underlying, yy, mm = m.groups()
        year, month = 2000 + int(yy), int(mm)
        if third_thursday(year, month) < today: return None
        return {"symbol": code, "providerSymbol": krx_code(underlying, year, month),
                "underlying": underlying, "expiry": third_thursday(year, month).isoformat()}
    m = KRX.fullmatch(code)
    if not m: return None
    asset, yc, mc = m.groups()
    month = next((m for m, v in MONTH_CODE.items() if v == mc), None)
    year = next((y for y in range(today.year - 1, today.year + 3) if year_code(y) == yc), None)
    if not month or year is None or third_thursday(year, month) < today: return None
    underlying = "VN30" if asset == "I1" else "VN100"
    return {"symbol": f"{underlying}F{year % 100:02d}{month:02d}", "providerSymbol": code,
            "underlying": underlying, "expiry": third_thursday(year, month).isoformat()}


def defaults(today):
    # Guard against late-month rollover; KRX identifiers are generated from
    # exchange conventions, never used to fabricate a listed contract/price.
    result = {}
    year, month = today.year, today.month
    for offset in range(7):
        y = year + (month - 1 + offset) // 12
        m = (month - 1 + offset) % 12 + 1
        if offset >= 2 and m not in (3, 6, 9, 12): continue
        for underlying in ("VN30", "VN100"):
            code = krx_code(underlying, y, m)
            row = parse_contract(code, today)
            if row: result[code] = row
    return result


def _num(value):
    if isinstance(value, bool): return None
    try:
        if value is None or str(value).strip() == "": return None
        result = float(str(value).replace(",", ""))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError): return None


def _request(url, payload=None, timeout=10):
    if not url.startswith(BASE + "/") or len(url) > 500:
        raise ValueError("Invalid approved KBS URL")
    headers = {"User-Agent": "FinQuery/1.0 public financial dashboard",
               "Accept": "application/json", "Referer": SOURCE,
               "Content-Type": "application/json", "x-lang": "vi"}
    raw = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=raw, headers=headers, method="POST" if raw is not None else "GET")
    with urlopen(req, timeout=timeout) as response:
        if response.geturl().split("?")[0] != url.split("?")[0]: raise ValueError("KBS redirect rejected")
        data = response.read(400_001)
        if len(data) > 400_000: raise ValueError("Response size limit")
        return json.loads(data)


def source_catalog(client=_request, today=None):
    today = today or datetime.now(VN).date()
    catalog = {}
    try:
        source = client(BASE + "/index/DER/stocks")
        rows = source.get("data") if isinstance(source, dict) else source
        if not isinstance(rows, list): raise ValueError("Registry not a list")
        for item in rows[:250]:
            candidate = (item if isinstance(item, str) else
                         item.get("sb") or item.get("SB") or item.get("symbol") or item.get("code")
                         if isinstance(item, dict) else "")
            contract = parse_contract(candidate, today)
            if contract: catalog[contract["providerSymbol"]] = contract
    except (OSError, ValueError, TypeError, KeyError):
        pass
    # Supplemental deterministic candidates are validated against actual
    # provider responses, never displayed merely because their codes exist.
    for code, contract in defaults(today).items(): catalog.setdefault(code, contract)
    return catalog


def parse_trade_time(trade, now):
    if not isinstance(trade, dict): return None
    date_part = str(trade.get("TD") or "").strip()
    time_part = str(trade.get("FT") or "").strip()
    candidates = []
    if date_part and time_part:
        candidates.append(date_part + " " + time_part)
    raw = re.sub(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d):\d+$", r"\1", str(trade.get("t") or "").strip())
    if raw: candidates.append(raw)
    for value in candidates:
        for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                stamp = datetime.strptime(value, pattern).replace(tzinfo=VN).astimezone(timezone.utc)
                if now - timedelta(days=15) <= stamp <= now + timedelta(minutes=5):
                    return stamp.isoformat()
            except ValueError:
                pass
    return None


def probe_trade(contract, client, now):
    symbol = contract["providerSymbol"]
    url = BASE + "/trade/history/" + quote(symbol) + "?page=1&limit=5"
    payload = client(url)
    rows = payload.get("data", []) if isinstance(payload, dict) else payload
    if isinstance(rows, dict): rows = rows.get("data", rows.get("items", []))
    if not isinstance(rows, list): return None
    observations = [parse_trade_time(row, now) for row in rows[:5]
                    if isinstance(row, dict) and str(row.get("SB") or symbol).upper() == symbol]
    observations = [x for x in observations if x]
    return max(observations) if observations else None


def normalize_board(payload, catalog, observed, now):
    rows = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list): raise ValueError("Derivative ISS payload is not a list")
    result = {}
    for raw in rows:
        if not isinstance(raw, dict): continue
        code = str(raw.get("SB") or "").upper()
        meta = catalog.get(code)
        if not meta: continue
        time = observed.get(code)
        if not time: continue
        price, ref, volume = _num(raw.get("CP")), _num(raw.get("RE")), _num(raw.get("TT"))
        if not price or price <= 0 or price > 50_000 or not ref or ref <= 0 or volume is None or volume <= 0:
            continue
        if abs(price / ref - 1) > .25: continue
        value = {**meta, "price": price, "reference": ref, "change": round(price-ref, 4),
                 "changePct": round((price / ref - 1) * 100, 4),
                 "volume": int(volume), "unit": "points", "market": "HNX_FUTURES",
                 "sourceTime": time, "source": "KBS", "status": "observed"}
        for source, field in (("OI", "openInterest"), ("HI", "high"), ("LO", "low"),
                              ("OP", "open"), ("B1", "bid1"), ("V1", "bidVol1"),
                              ("S1", "ask1"), ("U1", "askVol1")):
            x = _num(raw.get(source))
            if x is not None and x >= 0: value[field] = x
        if value.get("low") is not None and value["low"] > price: continue
        if value.get("high") is not None and value["high"] < price: continue
        result[meta["symbol"]] = value
    return result


def collect(client=_request, now=None):
    now = now or NOW()
    if now.tzinfo is None: raise ValueError("Need timezone-aware now")
    now = now.astimezone(timezone.utc)
    today = now.astimezone(VN).date()
    catalog = source_catalog(client, today)
    if not catalog: raise ValueError("No candidate futures contracts")
    # A single bounded batch fetch is cheaper than one price call per symbol.
    symbols = list(catalog)[:32]
    payload = client(BASE + "/derivative/iss", {"code": ",".join(symbols)})
    rows = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list): raise ValueError("Derivative source returned invalid schema")
    active = [r for r in rows if isinstance(r, dict) and str(r.get("SB") or "").upper() in catalog
              and (_num(r.get("TT")) or 0) > 0 and (_num(r.get("CP")) or 0) > 0]
    stamps = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        tasks = {executor.submit(probe_trade, catalog[str(row["SB"]).upper()], client, now): str(row["SB"]).upper()
                 for row in active[:12]}
        for future in as_completed(tasks):
            try:
                stamp = future.result()
                if stamp: stamps[tasks[future]] = stamp
            except (OSError, ValueError, TypeError, KeyError):
                continue
    contracts = normalize_board({"data": active}, catalog, stamps, now)
    if not contracts: raise ValueError("No futures quotes with per-contract verified trade timestamps")
    ordered = sorted(contracts.values(), key=lambda row: (row["underlying"], row["expiry"]))
    return {"schemaVersion": 1, "status": "ok",
            "source": SOURCE, "sourceName": "KBS delayed market quotes",
            "collectedAt": now.isoformat(), "latestSourceTime": max(x["sourceTime"] for x in ordered),
            "intervalTargetSeconds": 300, "exchange": "HNX", "type": "FUTURES_ONLY",
            "contracts": ordered, "notIntradayTickStream": True}


def retain_series(payload, old):
    """Append actual per-contract trade observations; no synthetic minute bars."""
    lookup = {row.get("symbol"): row for row in (old.get("contracts") or [])
              if isinstance(row, dict) and isinstance(row.get("symbol"), str)}
    for row in payload["contracts"]:
        previous = lookup.get(row["symbol"], {})
        seen = {}
        for tick in (previous.get("series") or [])[-240:]:
            if not isinstance(tick, dict) or not isinstance(tick.get("time"), str): continue
            try: when = datetime.fromisoformat(tick["time"].replace("Z", "+00:00"))
            except ValueError: continue
            price = _num(tick.get("price"))
            if when.tzinfo and price and price > 0 and when <= NOW():
                seen[tick["time"]] = {"time": tick["time"], "price": price}
        seen[row["sourceTime"]] = {"time": row["sourceTime"], "price": row["price"]}
        row["series"] = [seen[stamp] for stamp in sorted(seen)][-180:]
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    payload = collect()
    path = Path(args.output)
    try:
        old = json.loads(path.read_text(encoding='utf-8'))
        if old.get('schemaVersion') != 1: old = {}
    except (ValueError, OSError, AttributeError):
        old = {}
    payload = retain_series(payload, old)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    temp.replace(path)
    print(json.dumps({"futures": len(payload["contracts"]), "latest": payload["latestSourceTime"],
                      "targetSeconds": 300}))
if __name__ == "__main__":
    main()
