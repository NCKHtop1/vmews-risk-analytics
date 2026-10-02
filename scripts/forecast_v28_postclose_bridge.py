"""Fail-closed bridge for the latest completed HOSE session.

Current-session inference is allowed only for the exchange's certified latest
completed session, with broad same-session TradingView OHLC coverage and broad
independent VNDIRECT close confirmation. Symbols without a verified same-session
bar remain explicitly stale; they never receive synthetic OHLC and they do not
block publication when both independent source coverage gates pass. Downstream
consumers must keep stale symbols out of current-session rankings. This also
works when a workflow runs after midnight, on a weekend, or during an exchange
holiday. No synthetic OHLC is created.
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


def tradingview_close_confirmation(row, session_date: str, *, today=None):
    """Return an independently observed close for the requested completed session.

    TradingView replaces most rows with the new live session shortly after the
    next market opens. In that case its current close and percentage change
    still encode the immediately previous close. Use that relation only for
    close confirmation; never create OHLC from it.
    """
    close = _num(row.get("close"))
    if close is None or close <= 0:
        return None, None

    updated = _quote_time(row.get("update_time"))
    source_date = str(row.get("date") or "")[:10]
    observed_date = source_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", source_date) else (updated.date().isoformat() if updated else "")
    if observed_date == session_date:
        return float(close), "SAME_SESSION_CLOSE"

    day_value = today or datetime.now(VN_TZ).date()
    if not hasattr(day_value, "isoformat"):
        try:
            day_value = datetime.fromisoformat(str(day_value)).date()
        except Exception:
            return None, None
    current_day = day_value.isoformat()
    if observed_date != current_day or not session_date or session_date >= current_day:
        return None, None
    # The implied previous close is valid only for the certified latest
    # completed session before this live day. Never back-cast across two or
    # more sessions, weekends, or holidays.
    live_probe = datetime(day_value.year, day_value.month, day_value.day, 10, 0, tzinfo=VN_TZ)
    if session_date != latest_completed_session(live_probe).isoformat():
        return None, None

    change = _num(row.get("change"))
    if change is None:
        return None, None
    denominator = 1.0 + change / 100.0
    if denominator <= 0:
        return None, None
    previous_close = close / denominator
    if not math.isfinite(previous_close) or previous_close <= 0:
        return None, None
    return float(previous_close), "CURRENT_SESSION_CHANGE_IMPLIED_PREVIOUS_CLOSE"


def bridge_completed_session(
    histories,
    freshness,
    *,
    now=None,
    frame=None,
    secondary_rows=None,
    min_coverage=MIN_POSTCLOSE_COVERAGE,
    min_secondary_coverage=MIN_SECONDARY_COVERAGE,
    secondary_coverage_scope="universe",
    primary_name="TRADINGVIEW_VIETNAM_SCREEN",
    secondary_name="VNDIRECT_PUBLIC_EOD",
    provider_label="TradingView completed-session OHLC, VNDIRECT-confirmed close",
    provider_code="TRADINGVIEW_POST_CLOSE_VNDIRECT_CONFIRMED",
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
        "staleSymbols": 0,
        "staleSymbolSample": [],
        "primary": primary_name,
        "secondary": secondary_name,
        "secondaryCoverageScope": secondary_coverage_scope,
        "realOHLCRequired": True,
        "inferenceOnly": True,
    }
    # An already-current history proves freshness, but on the current
    # trading day it does not prove the independent two-source close contract.
    # Continue through the TradingView/VNDIRECT checks before publication.
    if (
        prior_as_of
        and prior_as_of >= session_date
        and session_date != now.date().isoformat()
    ):
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
        source_date = str(row.get("date") or "")[:10]
        observed_date = source_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", source_date) else (updated.date().isoformat() if updated else "")
        if (
            symbol not in current
            or _exchange(row.get("exchange")) != "HOSE"
            or symbol in primary
            or observed_date != session_date
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
    secondary_base = len(primary) if secondary_coverage_scope == "primary" else len(current)
    sec_coverage = len(common) / max(1, secondary_base)
    mismatches = []
    for symbol in sorted(common):
        p = float(primary[symbol]["close"])
        s = float(secondary[symbol]["close"])
        tolerance = max(MAX_LOG_GAP, 2 * _tick(p) / p)
        if abs(math.log(p / s)) > tolerance:
            mismatches.append(symbol)

    audit.update({
        "secondarySameDayQuotes": len(common),
        "secondaryCoverageBase": secondary_base,
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
            "provider": provider_label,
            "exchange": "HOSE",
            "ohlcUnavailable": False,
            "closeIndependentlyConfirmed": symbol in common,
        })
        provider[symbol] = provider_code
        appended += 1

    stale = sorted(
        symbol for symbol in current
        if not histories.get(symbol)
        or str((histories[symbol] or [{}])[-1].get("date") or "")[:10] != session_date
    )
    audit.update({
        "appendedSymbols": appended,
        "alreadyCurrentSymbols": already,
        "staleSymbols": len(stale),
        "staleSymbolSample": stale[:20],
    })
    # A broad, independently confirmed same-session cross-section is enough to
    # advance the market snapshot. Some listed names can legitimately have no
    # same-day trade/quote (suspension, illiquidity, provider omission). Keep
    # those rows untouched and explicitly stale instead of fabricating OHLC or
    # freezing every liquid symbol behind a 100% universe requirement.
    audit.update({
        "status": "PASS",
        "completedSessionVerified": True,
        "independentCloseConfirmed": True,
        "partialUniverse": bool(stale),
        "publicationScope": "VERIFIED_CURRENT_PLUS_EXPLICIT_STALE" if stale else "FULL_CURRENT_UNIVERSE",
    })
    freshness.update({
        "forecastAsOf": session_date,
        "postCloseQuoteAsOf": session_date,
        "postCloseBridge": audit,
    })
    return histories, freshness
