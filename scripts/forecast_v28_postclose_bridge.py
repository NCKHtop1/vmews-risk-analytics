"""Fail-closed bridge for the latest completed HOSE session.

Current-session inference is allowed only for the exchange's certified latest
completed session, with broad same-session TradingView OHLC coverage and broad
independent VNDIRECT close confirmation. Symbols without independently confirmed
same-session data are excluded from the current publication universe; their
historical rows remain untouched and no synthetic OHLC is created. This allows a
broad verified market cross-section to advance without relabeling suspended,
illiquid, or provider-missing names as current. This also works when a workflow
runs after midnight, on a weekend, or during an exchange holiday.
"""
from __future__ import annotations
import gzip, json, math, os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from vn_exchange_calendar import latest_completed_session

VN_TZ = timezone(timedelta(hours=7))
MIN_POSTCLOSE_COVERAGE = float(os.getenv("V28_POSTCLOSE_MIN_COVERAGE", "0.90"))
MIN_SECONDARY_COVERAGE = float(os.getenv("V28_POSTCLOSE_MIN_SECONDARY_COVERAGE", "0.90"))
MAX_LOG_GAP = float(os.getenv("V28_POSTCLOSE_MAX_LOG_GAP", "0.003"))

def load_vndirect_secondary_cache(path) -> dict[str, list[dict[str, Any]]]:
    """Read the VNDIRECT EOD rows already refreshed by this forecast run.

    This avoids a second market-wide network request after load_histories() has
    just refreshed and persisted the same independent VNDIRECT source. A stale
    cache cannot make publication pass because bridge_completed_session() still
    requires same-session rows and the configured coverage threshold.
    """
    try:
        cache_path = Path(path)
        if not cache_path.exists():
            return {}
        with gzip.open(cache_path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, EOFError, ValueError, json.JSONDecodeError):
        return {}
    if str(payload.get("source") or "") != "VNDIRECT_PUBLIC_EOD":
        return {}
    histories = payload.get("histories") or {}
    return {
        str(symbol).upper(): [row for row in rows if isinstance(row, dict)]
        for symbol, rows in histories.items()
        if isinstance(rows, list)
    }



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
        "staleSymbols": 0,
        "staleSymbolSample": [],
        "primary": "TRADINGVIEW_VIETNAM_SCREEN",
        "secondary": "VNDIRECT_PUBLIC_EOD",
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

    stale = sorted(
        symbol for symbol in current
        if not histories.get(symbol)
        or str((histories[symbol] or [{}])[-1].get("date") or "")[:10] != session_date
    )
    verified_current = sorted(
        symbol for symbol in common
        if histories.get(symbol)
        and str((histories[symbol] or [{}])[-1].get("date") or "")[:10] == session_date
    )
    excluded = sorted(current - set(verified_current))
    verified_coverage = len(verified_current) / len(current)
    required_publication_coverage = max(float(min_coverage), float(min_secondary_coverage))
    if verified_coverage + 1e-12 < required_publication_coverage:
        audit["status"] = "REJECTED_VERIFIED_PUBLICATION_COVERAGE"
        audit["verifiedCurrentSymbols"] = len(verified_current)
        audit["verifiedCoverage"] = round(verified_coverage, 6)
        audit["requiredPublicationCoverage"] = required_publication_coverage
        audit["excludedSymbols"] = len(excluded)
        audit["excludedSymbolSample"] = excluded[:20]
        freshness["postCloseBridge"] = audit
        raise RuntimeError(
            f"Verified current-session publication coverage for {session_date} "
            f"{verified_coverage:.1%} below {required_publication_coverage:.1%}"
        )

    historical_price_cross_source = freshness.get("priceCrossSource") or {}
    current_agreements = {}
    current_gaps = []
    for symbol in verified_current:
        primary_close = float(primary[symbol]["close"])
        secondary_close = float(secondary[symbol]["close"])
        absolute_log_gap = abs(math.log(primary_close / secondary_close))
        tolerance = max(MAX_LOG_GAP, 2 * _tick(primary_close) / primary_close)
        current_gaps.append(absolute_log_gap)
        current_agreements[symbol] = {
            "status": "PASS",
            "session": session_date,
            "primary": "TRADINGVIEW_VIETNAM_SCREEN",
            "reference": "VNDIRECT_PUBLIC_EOD",
            "primaryClose": primary_close,
            "referenceClose": secondary_close,
            "absoluteLogGap": absolute_log_gap,
            "tolerance": tolerance,
        }

    freshness["historicalPriceCrossSource"] = historical_price_cross_source
    freshness["priceCrossSource"] = {
        "status": "PASS",
        "method": "SAME_COMPLETED_SESSION_TRADINGVIEW_VS_VNDIRECT_CLOSE",
        "session": session_date,
        "comparedSymbols": len(verified_current),
        "referenceEligibleSymbols": len(current),
        "universeSymbols": len(current),
        "eligibleCoverage": verified_coverage,
        "requiredEligibleCoverage": required_publication_coverage,
        "universeCoverage": verified_coverage,
        "requiredUniverseCoverage": required_publication_coverage,
        "coverage": verified_coverage,
        "requiredCoverage": required_publication_coverage,
        "mismatchCount": 0,
        "mismatches": [],
        "medianAbsoluteLogGap": (
            sorted(current_gaps)[len(current_gaps)//2] if current_gaps else None
        ),
        "p95AbsoluteLogGap": (
            sorted(current_gaps)[min(len(current_gaps)-1, int(.95 * len(current_gaps)))]
            if current_gaps else None
        ),
        "symbols": current_agreements,
    }

    audit.update({
        "appendedSymbols": appended,
        "alreadyCurrentSymbols": already,
        "staleSymbols": len(stale),
        "staleSymbolSample": stale[:20],
        "verifiedCurrentSymbols": len(verified_current),
        "verifiedCoverage": round(verified_coverage, 6),
        "requiredPublicationCoverage": required_publication_coverage,
        "excludedSymbols": len(excluded),
        "excludedSymbolSample": excluded[:20],
        "status": "PASS",
        "completedSessionVerified": True,
        "independentCloseConfirmed": True,
        "partialUniverse": bool(excluded),
        "publicationScope": "INDEPENDENTLY_VERIFIED_CURRENT_ONLY" if excluded else "FULL_CURRENT_UNIVERSE",
    })
    freshness.update({
        "forecastAsOf": session_date,
        "postCloseQuoteAsOf": session_date,
        "postCloseBridge": audit,
        "currentHOSESymbols": verified_current,
        "excludedCurrentSessionSymbols": excluded,
        "excludedStaleSymbols": stale,
    })
    return histories, freshness
