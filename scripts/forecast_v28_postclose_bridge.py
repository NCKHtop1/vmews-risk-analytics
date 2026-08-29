"""Fail-closed bridge for the latest completed HOSE session.

Current-session inference is allowed only for the exchange's certified latest
completed session, with broad same-session TradingView OHLC coverage and broad
independent VNDIRECT close confirmation.  This also works when a workflow runs
after midnight, on a weekend, or during an exchange holiday.  No synthetic
OHLC is created.
"""
from __future__ import annotations
import math, os, re
from datetime import datetime, timedelta, timezone
from typing import Any
from vn_exchange_calendar import latest_completed_session

VN_TZ = timezone(timedelta(hours=7))
MIN_POSTCLOSE_COVERAGE = float(os.getenv("V28_POSTCLOSE_MIN_COVERAGE", "0.90"))
MIN_SECONDARY_COVERAGE = float(os.getenv("V28_POSTCLOSE_MIN_SECONDARY_COVERAGE", "0.90"))
MAX_LOG_GAP = float(os.getenv("V28_POSTCLOSE_MAX_LOG_GAP", "0.003"))


def _num(value: Any, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _symbol(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper().split(":")[-1])


def _exchange(value):
    raw = str(value or "").upper().strip()
    return {"HSX": "HOSE", "HOCHIMINH": "HOSE"}.get(raw, raw)


def _quote_time(value):
    timestamp = _num(value)
    if timestamp is None:
        return None
    if timestamp > 1e12:
        timestamp /= 1000.0
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(VN_TZ)
    except (OverflowError, OSError, ValueError):
        return None


def _tick(price):
    return 10 if price < 10_000 else 50 if price < 50_000 else 100


def fetch_tradingview_quotes():
    from tradingview_screener import stocks
    fields = ["name", "exchange", "open", "high", "low", "close", "change", "volume", "update_mode", "update_time"]
    _, frame = stocks("vietnam").select(*fields).limit(3000).get_scanner_data()
    if frame is None or len(frame) < 500:
        raise RuntimeError(f"TradingView Vietnam screener returned only {0 if frame is None else len(frame)} rows")
    return frame


def bridge_completed_session(
    histories,
    freshness,
    *,
    now=None,
    frame=None,
    secondary_rows=None,
    min_coverage=MIN_POSTCLOSE_COVERAGE,
    min_secondary_coverage=MIN_SECONDARY_COVERAGE,
):
    now = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    session_date = latest_completed_session(now).isoformat()
    prior_as_of = str(freshness.get("forecastAsOf") or "")[:10]
    audit = {
        "status": "NOT_APPLICABLE",
        "sessionDate": session_date,
        "observedAt": now.isoformat(timespec="seconds"),
        "minimumCoverage": min_coverage,
        "minimumSecondaryCoverage": min_secondary_coverage,
        "coverage": 0.0,
        "secondaryCoverage": 0.0,
        "eligibleSymbols": 0,
        "sameDayQuotes": 0,
        "secondarySameDayQuotes": 0,
        "mismatchCount": 0,
        "appendedSymbols": 0,
        "alreadyCurrentSymbols": 0,
        "primary": "TRADINGVIEW_VIETNAM_SCREEN",
        "secondary": "VNDIRECT_PUBLIC_EOD",
        "realOHLCRequired": True,
        "inferenceOnly": True,
    }
    if prior_as_of and prior_as_of >= session_date:
        audit["status"] = "NOT_APPLICABLE_ALREADY_CURRENT"
        freshness["postCloseBridge"] = audit
        return histories, freshness

    current = {
        str(s).upper()
        for s in (freshness.get("currentHOSESymbols") or histories)
        if str(s).upper() in histories
    }
    if not current:
        raise RuntimeError("Post-close bridge has no current HOSE universe")

    audit["eligibleSymbols"] = len(current)
    frame = frame if frame is not None else fetch_tradingview_quotes()
    primary = {}
    for _, row in frame.iterrows():
        symbol = _symbol(row.get("name") or row.get("ticker"))
        updated = _quote_time(row.get("update_time"))
        if (
            symbol not in current
            or _exchange(row.get("exchange")) != "HOSE"
            or symbol in primary
            or not updated
            or updated.date().isoformat() != session_date
        ):
            continue
        o, h, l, c = (_num(row.get(k)) for k in ("open", "high", "low", "close"))
        v = _num(row.get("volume"), 0.0) or 0.0
        if None in (o, h, l, c) or min(o, h, l, c) <= 0 or h + 1e-9 < max(o, c) or l - 1e-9 > min(o, c):
            continue
        primary[symbol] = {"open": o, "high": h, "low": l, "close": c, "volume": v, "updatedAt": updated}

    coverage = len(primary) / len(current)
    audit.update({"sameDayQuotes": len(primary), "coverage": round(coverage, 6)})
    if coverage + 1e-12 < min_coverage:
        audit["status"] = "REJECTED_STALE"
        freshness["postCloseBridge"] = audit
        raise RuntimeError(
            f"Post-close TradingView coverage for {session_date} {coverage:.1%} below {min_coverage:.1%}"
        )

    secondary = {}
    for symbol, rows in (secondary_rows or {}).items():
        symbol = str(symbol).upper()
        if symbol not in current:
            continue
        candidates = [
            r for r in (rows or [])
            if str(r.get("date") or "")[:10] == session_date and _num(r.get("close"), 0) > 0
        ]
        if candidates:
            secondary[symbol] = candidates[-1]

    common = set(primary) & set(secondary)
    sec_coverage = len(common) / len(current)
    mismatches = []
    for symbol in sorted(common):
        p = float(primary[symbol]["close"])
        s = float(secondary[symbol]["close"])
        tolerance = max(MAX_LOG_GAP, 2 * _tick(p) / p)
        if abs(math.log(p / s)) > tolerance:
            mismatches.append(symbol)

    audit.update({
        "secondarySameDayQuotes": len(common),
        "secondaryCoverage": round(sec_coverage, 6),
        "mismatchCount": len(mismatches),
        "mismatches": mismatches[:20],
    })
    if sec_coverage + 1e-12 < min_secondary_coverage or mismatches:
        audit["status"] = "REJECTED_SECOND_SOURCE"
        freshness["postCloseBridge"] = audit
        raise RuntimeError(
            f"Post-close independent confirmation for {session_date} failed: coverage={sec_coverage:.1%}, mismatches={mismatches[:20]}"
        )

    provider = freshness.setdefault("providerBySymbol", {})
    appended = already = 0
    for symbol, quote in primary.items():
        history = histories.get(symbol) or []
        if not history:
            continue
        latest = str(history[-1].get("date") or "")[:10]
        if latest > session_date:
            raise RuntimeError(f"Future-dated history detected for {symbol}: {latest} > {session_date}")
        if latest == session_date:
            already += 1
            continue
        history.append({
            "date": session_date,
            "open": quote["open"],
            "high": quote["high"],
            "low": quote["low"],
            "close": quote["close"],
            "modelClose": quote["close"],
            "volume": quote["volume"],
            "provider": "TradingView completed-session OHLC, VNDIRECT-confirmed close",
            "exchange": "HOSE",
            "ohlcUnavailable": False,
            "closeIndependentlyConfirmed": symbol in common,
        })
        provider[symbol] = "TRADINGVIEW_POST_CLOSE_VNDIRECT_CONFIRMED"
        appended += 1

    audit.update({
        "status": "PASS",
        "appendedSymbols": appended,
        "alreadyCurrentSymbols": already,
        "completedSessionVerified": True,
        "independentCloseConfirmed": True,
    })
    freshness.update({
        "forecastAsOf": session_date,
        "postCloseQuoteAsOf": session_date,
        "postCloseBridge": audit,
    })
    return histories, freshness
