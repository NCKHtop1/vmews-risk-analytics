"""Build an independent Yahoo daily-close confirmation snapshot for SoluTION.AI core refresh.

This file is consumed only by the dedicated SoluTION.AI core workflow. It does
not publish to main and does not weaken the existing forecast validation gates.
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from vn_exchange_calendar import VN_TZ, latest_completed_session

UA = "Mozilla/5.0 SoluTION.AI-Core/1.0"
VN = ZoneInfo("Asia/Ho_Chi_Minh")


def parse_yahoo_payload(payload: dict, session_date: str) -> float | None:
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return None
    stamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    closes = quote.get("close") or []
    chosen = None
    for idx, raw_stamp in enumerate(stamps):
        if idx >= len(closes):
            break
        close = closes[idx]
        try:
            close = float(close)
            stamp = float(raw_stamp)
        except (TypeError, ValueError):
            continue
        if close <= 0:
            continue
        day = datetime.fromtimestamp(stamp, VN).date().isoformat()
        if day == session_date:
            chosen = close
    return chosen


def yahoo_close(symbol: str, session_date: str, timeout: float = 6.0) -> float | None:
    ticker = urllib.parse.quote(f"{symbol}.VN")
    suffix = f"/v8/finance/chart/{ticker}?range=10d&interval=1d&includePrePost=false&events=div%2Csplits"
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}{suffix}"
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            close = parse_yahoo_payload(payload, session_date)
            if close:
                return close
        except Exception:
            continue
    return None


def parse_tcbs_payload(payload: dict, session_date: str) -> float | None:
    chosen = None
    for row in payload.get("data") or []:
        raw_date = str(row.get("tradingDate") or row.get("date") or "")[:10]
        if raw_date != session_date:
            continue
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            continue
        if close > 0:
            chosen = close
    return chosen


def tcbs_close(symbol: str, session_date: str, timeout: float = 6.0) -> float | None:
    session = datetime.fromisoformat(session_date).replace(tzinfo=VN)
    start = int((session - timedelta(days=5)).timestamp())
    end = int((session + timedelta(days=1)).timestamp())
    query = urllib.parse.urlencode({
        "ticker": symbol,
        "type": "stock",
        "resolution": "D",
        "from": start,
        "to": end,
    })
    url = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return parse_tcbs_payload(payload, session_date)
    except Exception:
        return None


def load_symbols(dashboard_path: Path, frozen_source_path: Path | None = None) -> list[str]:
    frozen_source_path = frozen_source_path or (dashboard_path.parent / "v12-frozen-source.json.gz")
    if frozen_source_path.exists():
        try:
            with gzip.open(frozen_source_path, "rt", encoding="utf-8") as stream:
                frozen = json.load(stream)
            current = {
                str(symbol).upper().strip()
                for symbol in (frozen.get("currentHOSESymbols") or [])
                if str(symbol).upper().strip().isalnum()
                and 2 <= len(str(symbol).upper().strip()) <= 5
            }
            if current:
                return sorted(current)
        except Exception:
            pass

    payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
    return sorted(
        symbol for symbol in (payload.get("symbols") or {})
        if symbol and symbol.isalnum() and 2 <= len(symbol) <= 5
    )


def build_snapshot(symbols: list[str], session_date: str, workers: int = 12) -> dict:
    rows: dict[str, float] = {}
    source_by_symbol: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(yahoo_close, symbol, session_date): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                close = future.result()
            except Exception:
                close = None
            if close:
                rows[symbol] = close
                source_by_symbol[symbol] = "YAHOO_FINANCE_DAILY"

    missing = [symbol for symbol in symbols if symbol not in rows]
    if missing:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as pool:
            futures = {pool.submit(tcbs_close, symbol, session_date): symbol for symbol in missing}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    close = future.result()
                except Exception:
                    close = None
                if close:
                    rows[symbol] = close
                    source_by_symbol[symbol] = "TCBS_PUBLIC_DAILY_GAPFILL"

    counts = {
        "YAHOO_FINANCE_DAILY": sum(value == "YAHOO_FINANCE_DAILY" for value in source_by_symbol.values()),
        "TCBS_PUBLIC_DAILY_GAPFILL": sum(value == "TCBS_PUBLIC_DAILY_GAPFILL" for value in source_by_symbol.values()),
    }
    return {
        "version": "SOLUTION-AI-INDEPENDENT-CLOSE-CONFIRM-2",
        "scope": "solution-ai",
        "provider": "Yahoo Finance daily close + TCBS public daily gap-fill",
        "asOf": session_date,
        "generatedAt": datetime.now(VN_TZ).isoformat(),
        "coverage": len(rows),
        "expected": len(symbols),
        "coverageRatio": (len(rows) / len(symbols)) if symbols else 0.0,
        "sourceCounts": counts,
        "predictions": [
            {"symbol": symbol, "close": rows[symbol], "source": source_by_symbol[symbol]}
            for symbol in sorted(rows)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dashboard", default="data/forecast-dashboard-v12.json")
    parser.add_argument("--output", default="")
    parser.add_argument("--frozen-source", default="data/v12-frozen-source.json.gz")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--session-date", default="")
    args = parser.parse_args()

    dashboard = Path(args.dashboard)
    symbols = load_symbols(dashboard, Path(args.frozen_source))
    session_date = args.session_date or latest_completed_session(datetime.now(VN_TZ)).isoformat()
    output = Path(args.output or f"data/forecast-live-v10/snapshots/{session_date}.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    snapshot = build_snapshot(symbols, session_date, workers=args.workers)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "session": session_date,
        "coverage": snapshot["coverage"],
        "expected": snapshot["expected"],
        "coverageRatio": round(snapshot["coverageRatio"], 4),
        "sourceCounts": snapshot.get("sourceCounts"),
        "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
