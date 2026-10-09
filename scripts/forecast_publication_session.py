"""Strict, explicit guard for the HOSE 15:05 EOD cutover.

A 10-30 minute model build may cross 15:05 while its vetted independent
OHLC/close evidence still belongs to the previous completed session. During
this short handoff, publish a more recent *correctly dated* vetted backfill;
NEVER relabel it current, accept older unverified prices, or waive source gates.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from vn_exchange_calendar import (
    VN_TZ, PRICE_READY_AFTER, is_trading_day,
    latest_completed_session, previous_trading_day,
)

MAX_CUTOVER_GRACE_MINUTES = 75


def publication_session_status(as_of, now=None):
    local = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    try:
        candidate = date.fromisoformat(str(as_of)[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid validated model session {as_of!r}") from exc
    expected = latest_completed_session(local)
    if candidate == expected:
        return {
            "status": "CURRENT_VERIFIED_SESSION",
            "validatedSession": candidate.isoformat(),
            "expectedSessionNow": expected.isoformat(),
            "staleCore": False,
        }
    if (
        is_trading_day(local.date(), require_certified=True)
        and expected == local.date()
        and candidate == previous_trading_day(local.date())
    ):
        shift = datetime.combine(local.date(), PRICE_READY_AFTER, tzinfo=VN_TZ)
        elapsed = (local - shift).total_seconds()
        if 0 <= elapsed <= MAX_CUTOVER_GRACE_MINUTES * 60:
            return {
                "status": "PREVIOUS_VERIFIED_SESSION_DURING_CUTOVER",
                "validatedSession": candidate.isoformat(),
                "expectedSessionNow": expected.isoformat(),
                "staleCore": True,
                "graceMinutes": MAX_CUTOVER_GRACE_MINUTES,
                "reason": (
                    "The run crossed the EOD 15:05 boundary. A dated, independently "
                    "audited previous session may advance the last-good snapshot "
                    "during bounded provider handoff, but must not be ranked as current."
                ),
            }
    raise ValueError(
        f"STALE_OR_FUTURE_FORECAST_REJECTED validated={candidate.isoformat()} "
        f"expected={expected.isoformat()} at={local.isoformat()}"
    )
