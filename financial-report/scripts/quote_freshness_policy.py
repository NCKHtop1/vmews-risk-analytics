"""Independent, fail-closed trading-session freshness policy for FinQuery quotes.

This is a delivery guard, not a price publisher or a trading signal. It checks
source freshness against the exchange calendar, not just source-vs-mirror lag.
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

CALENDAR_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(CALENDAR_DIR) not in sys.path:
    sys.path.insert(0, str(CALENDAR_DIR))


ACTIVE_MAX_AGE_MINUTES = 20
HEARTBEAT_MAX_AGE_MINUTES = 15
MIN_FRESH_COVERAGE = .90
SESSION_REQUIRED_FROM = time(9, 15)
AFTERNOON_FRESH_FROM = time(13, 15)
FINAL_SESSION_FROM = time(15, 5)


class QuoteFreshnessError(ValueError):
    """A source dataset may be internally valid but not fit for current trading."""


def _stamp(value, label, now):
    if not isinstance(value, str) or not value:
        raise QuoteFreshnessError(f"{label} missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise QuoteFreshnessError(f"{label} invalid") from exc
    if parsed.tzinfo is None:
        raise QuoteFreshnessError(f"{label} timezone missing")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(minutes=5):
        raise QuoteFreshnessError(f"{label} from future")
    return parsed


def _age_min(now, stamp):
    return max(0., (now - stamp).total_seconds() / 60)


def _session_phase(now):
    # Import lazily: some isolated smoke checks import this module with sparse checkout.
    # A real freshness assessment still fails closed when the certified calendar is absent.
    try:
        from vn_exchange_calendar import VN_TZ, is_trading_day, latest_completed_session
    except ImportError as exc:
        raise QuoteFreshnessError('certified VN exchange calendar is unavailable') from exc
    local = now.astimezone(VN_TZ)
    try:
        trading = is_trading_day(local.date(), require_certified=True)
        completed = latest_completed_session(now)
    except RuntimeError as exc:
        raise QuoteFreshnessError(f"calendar not certified: {exc}") from exc
    clock = local.time().replace(tzinfo=None)
    if not trading:
        return "closed", completed, False
    if clock < SESSION_REQUIRED_FROM:
        return "preopen", completed, False
    if clock <= time(11, 30):
        return "morning", local.date(), True
    if clock < AFTERNOON_FRESH_FROM:
        return "lunch", local.date(), False
    if clock <= FINAL_SESSION_FROM:
        return "afternoon", local.date(), True
    return "postclose", local.date(), False


def assess_quote_source(data, *, now=None):
    """Require correct exchange session and a real source heartbeat during trading.

    Return machine-readable evidence; raise QuoteFreshnessError for any breach.
    Do not mark new bars, prices or models as valid solely because this passes.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise QuoteFreshnessError("current clock timezone missing")
    now = now.astimezone(timezone.utc)
    if not isinstance(data, dict) or data.get("status") != "ok":
        raise QuoteFreshnessError("source status is not ok")

    phase, expected_date, active = _session_phase(now)
    latest = _stamp(data.get("latestSourceTime"), "latestSourceTime", now)
    from vn_exchange_calendar import VN_TZ
    latest_day = latest.astimezone(VN_TZ).date()
    if latest_day != expected_date:
        raise QuoteFreshnessError(
            f"source session stale: observed {latest_day}, expected {expected_date} ({phase})"
        )

    result = {
        "phase": phase,
        "expectedSession": expected_date.isoformat(),
        "observedSession": latest_day.isoformat(),
        "latestAgeMinutes": round(_age_min(now, latest), 1),
        "inSessionFreshnessRequired": active,
    }
    if not active:
        return result

    quote_age = _age_min(now, latest)
    if quote_age > ACTIVE_MAX_AGE_MINUTES:
        raise QuoteFreshnessError(
            f"source quote stale: {quote_age:.1f}min > {ACTIVE_MAX_AGE_MINUTES}min"
        )

    checked = _stamp(data.get("checkedAt"), "checkedAt", now)
    heartbeat_age = _age_min(now, checked)
    if heartbeat_age > HEARTBEAT_MAX_AGE_MINUTES:
        raise QuoteFreshnessError(
            f"collector heartbeat stale: {heartbeat_age:.1f}min > {HEARTBEAT_MAX_AGE_MINUTES}min"
        )

    quotes = data.get("quotes")
    expected = int(data.get("expected") or 0)
    if not isinstance(quotes, dict) or expected < 100:
        raise QuoteFreshnessError("source quote universe missing or below 100")
    required = math.ceil(expected * MIN_FRESH_COVERAGE)
    recent = 0
    for quote in quotes.values():
        if not isinstance(quote, dict) or quote.get("status") == "retained":
            continue
        price = quote.get("price")
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            continue
        if not math.isfinite(price) or price <= 0:
            continue
        try:
            source_time = _stamp(quote.get("sourceTime"), "quote.sourceTime", now)
        except QuoteFreshnessError:
            continue
        if (source_time.astimezone(VN_TZ).date() == expected_date
                and _age_min(now, source_time) <= ACTIVE_MAX_AGE_MINUTES):
            recent += 1
    if recent < required:
        raise QuoteFreshnessError(
            f"fresh source quote coverage {recent}/{expected}, required {required}"
        )
    result.update({"heartbeatAgeMinutes": round(heartbeat_age, 1),
                   "freshQuotes": recent, "expectedQuotes": expected})
    return result
