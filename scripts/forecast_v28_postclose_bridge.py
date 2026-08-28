"""Strict post-close bridge from same-day TradingView quotes into forecast inference.

VNDIRECT EOD can lag the just-completed HOSE session.  After the Vietnamese
market has closed, this module may append a same-day close/volume observation
for inference only when broad HOSE quote coverage proves the session is current.
It never fabricates a future date and never activates during an open session.
"""

from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

VN_TZ = timezone(timedelta(hours=7))
MIN_POSTCLOSE_COVERAGE = float(os.getenv("V28_POSTCLOSE_MIN_COVERAGE", "0.90"))
POSTCLOSE_HOUR = 15
POSTCLOSE_MINUTE = 5


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _symbol(value: Any) -> str:
    text = str(value or "").upper().split(":")[-1]
    return re.sub(r"[^A-Z0-9]", "", text)


def _exchange(value: Any) -> str:
    text = str(value or "").upper().strip()
    return {"HSX": "HOSE", "HOCHIMINH": "HOSE"}.get(text, text)


def _quote_time(value: Any) -> datetime | None:
    timestamp = _num(value)
    if timestamp is None:
        return None
    if timestamp > 1e12:
        timestamp /= 1000.0
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(VN_TZ)
    except (OverflowError, OSError, ValueError):
        return None


def _postclose(now: datetime) -> bool:
    local = now.astimezone(VN_TZ)
    return local.weekday() < 5 and (local.hour, local.minute) >= (POSTCLOSE_HOUR, POSTCLOSE_MINUTE)


def fetch_tradingview_quotes():
    from tradingview_screener import stocks

    fields = ["name", "exchange", "close", "change", "volume", "update_mode", "update_time"]
    _, frame = stocks("vietnam").select(*fields).limit(3000).get_scanner_data()
    if frame is None or len(frame) < 500:
        raise RuntimeError(f"TradingView Vietnam screener returned only {0 if frame is None else len(frame)} rows")
    return frame


def bridge_completed_session(
    histories: dict[str, list[dict[str, Any]]],
    freshness: dict[str, Any],
    *,
    now: datetime | None = None,
    frame=None,
    min_coverage: float = MIN_POSTCLOSE_COVERAGE,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Append the completed same-day HOSE close only after strict coverage proof."""
    now = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    today = now.date().isoformat()
    audit = {
        "status": "NOT_APPLICABLE",
        "sessionDate": today,
        "minimumCoverage": min_coverage,
        "coverage": 0.0,
        "eligibleSymbols": 0,
        "sameDayQuotes": 0,
        "appendedSymbols": 0,
        "alreadyCurrentSymbols": 0,
        "provider": "TradingView Vietnam Screener",
        "inferenceOnly": True,
    }
    if not _postclose(now):
        freshness["postCloseBridge"] = audit
        return histories, freshness

    current = {
        str(symbol).upper()
        for symbol in (freshness.get("currentHOSESymbols") or histories.keys())
        if str(symbol).upper() in histories
    }
    if not current:
        raise RuntimeError("Post-close bridge has no current HOSE universe")
    audit["eligibleSymbols"] = len(current)

    frame = frame if frame is not None else fetch_tradingview_quotes()
    matched: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        symbol = _symbol(row.get("name") or row.get("ticker"))
        if symbol not in current or _exchange(row.get("exchange")) != "HOSE" or symbol in matched:
            continue
        close = _num(row.get("close"))
        updated_at = _quote_time(row.get("update_time"))
        if close is None or close <= 0 or updated_at is None or updated_at.date().isoformat() != today:
            continue
        matched[symbol] = {
            "close": close,
            "volume": _num(row.get("volume"), 0.0) or 0.0,
            "updatedAt": updated_at,
        }

    coverage = len(matched) / len(current)
    audit["sameDayQuotes"] = len(matched)
    audit["coverage"] = round(coverage, 6)
    if coverage + 1e-12 < min_coverage:
        audit["status"] = "REJECTED_STALE"
        freshness["postCloseBridge"] = audit
        raise RuntimeError(
            f"Post-close current-session coverage {coverage:.1%} is below {min_coverage:.1%}; "
            "refusing to publish a stale forecast as current."
        )

    provider_by_symbol = freshness.setdefault("providerBySymbol", {})
    appended = already_current = 0
    for symbol, quote in matched.items():
        history = histories.get(symbol) or []
        if not history:
            continue
        latest_date = str(history[-1].get("date") or "")[:10]
        if latest_date > today:
            raise RuntimeError(f"Future-dated history detected for {symbol}: {latest_date} > {today}")
        if latest_date == today:
            already_current += 1
            continue
        close = float(quote["close"])
        history.append(
            {
                "date": today,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "modelClose": close,
                "volume": float(quote["volume"]),
                "provider": "TradingView post-close completed-session bridge",
                "exchange": "HOSE",
                "ohlcUnavailable": True,
            }
        )
        provider_by_symbol[symbol] = "TRADINGVIEW_POST_CLOSE"
        appended += 1

    audit.update(
        {
            "status": "PASS",
            "appendedSymbols": appended,
            "alreadyCurrentSymbols": already_current,
            "completedSessionVerified": True,
        }
    )
    freshness["forecastAsOf"] = today
    freshness["postCloseQuoteAsOf"] = today
    freshness["postCloseBridge"] = audit
    return histories, freshness
