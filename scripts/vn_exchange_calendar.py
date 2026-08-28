"""Fail-closed Vietnam exchange calendar utilities used by forecast production."""
from __future__ import annotations
from datetime import date, datetime, time as clock, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
PRICE_READY_AFTER = clock(15, 5)
HOLIDAYS_BY_YEAR = {
    2026: frozenset({
        date(2026,1,1), date(2026,1,2),
        date(2026,2,16), date(2026,2,17), date(2026,2,18), date(2026,2,19), date(2026,2,20),
        date(2026,4,27), date(2026,4,30), date(2026,5,1),
        date(2026,8,31), date(2026,9,1), date(2026,9,2),
    })
}
CERTIFIED_YEARS = frozenset(HOLIDAYS_BY_YEAR)
CALENDAR_SOURCE = "OFFICIAL_HOSE_HNX_VNX_2026_TRADING_HOLIDAY_SCHEDULE"


def is_trading_day(day: date, *, require_certified: bool = False) -> bool:
    if day.weekday() >= 5:
        return False
    holidays = HOLIDAYS_BY_YEAR.get(day.year)
    if holidays is None:
        if require_certified:
            raise RuntimeError(
                f"Trading calendar year {day.year} is not certified; forecast publication is blocked."
            )
        return True
    return day not in holidays


def previous_trading_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor, require_certified=True):
        cursor -= timedelta(days=1)
    return cursor


def latest_completed_session(now=None, *, ready_after=PRICE_READY_AFTER) -> date:
    local = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    candidate = local.date()
    trading_today = is_trading_day(candidate, require_certified=True)
    if not trading_today or local.timetz().replace(tzinfo=None) < ready_after:
        if trading_today:
            candidate -= timedelta(days=1)
        while not is_trading_day(candidate, require_certified=True):
            candidate -= timedelta(days=1)
    return candidate


def next_trading_dates(origin, sessions=5):
    current = date.fromisoformat(origin) if isinstance(origin, str) else origin
    out = []
    while len(out) < max(0, sessions):
        current += timedelta(days=1)
        if is_trading_day(current, require_certified=True):
            out.append(current.isoformat())
    return out


def trading_session_age(observed, as_of):
    """Count recent certified sessions; clearly old evidence is simply stale.

    Release freshness only distinguishes recent from stale.  Multi-year archive
    rows do not need an exact holiday count and must not force us to pretend an
    uncertified historical holiday calendar is authoritative.
    """
    if not observed:
        return 99
    cursor = date.fromisoformat(str(observed)[:10]) if not isinstance(observed, date) else observed
    end = date.fromisoformat(str(as_of)[:10]) if not isinstance(as_of, date) else as_of
    if cursor >= end:
        return 0
    if (end - cursor).days > 31 and ({cursor.year, end.year} - CERTIFIED_YEARS):
        return 99
    age = 0
    while cursor < end:
        cursor += timedelta(days=1)
        if is_trading_day(cursor, require_certified=True):
            age += 1
    return age
