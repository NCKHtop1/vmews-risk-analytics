"""Fail-closed Vietnam exchange calendar utilities used by forecast production.

The 2026 holiday set follows the official HOSE/HNX/VNX published schedule.
Target-date generation refuses to cross into an uncertified future year rather
than silently treating every weekday as a trading session.
"""

from __future__ import annotations

from datetime import date, datetime, time as clock, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
PRICE_READY_AFTER = clock(15, 5)

# Official 2026 trading holidays. Compensation Saturdays are working days for
# government offices only; the exchanges explicitly do NOT trade on them.
HOLIDAYS_BY_YEAR: dict[int, frozenset[date]] = {
    2026: frozenset(
        {
            date(2026, 1, 1), date(2026, 1, 2),
            date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
            date(2026, 2, 19), date(2026, 2, 20),
            date(2026, 4, 27), date(2026, 4, 30), date(2026, 5, 1),
            date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2),
        }
    ),
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
                f"Trading calendar year {day.year} is not certified; refusing to infer a target date."
            )
        return True
    return day not in holidays


def previous_trading_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def latest_completed_session(
    now: datetime | None = None,
    *,
    ready_after: clock = PRICE_READY_AFTER,
) -> date:
    local = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    candidate = local.date()
    if not is_trading_day(candidate) or local.timetz().replace(tzinfo=None) < ready_after:
        if is_trading_day(candidate) and local.timetz().replace(tzinfo=None) < ready_after:
            candidate -= timedelta(days=1)
        while not is_trading_day(candidate):
            candidate -= timedelta(days=1)
    return candidate


def next_trading_dates(origin: str | date, sessions: int = 5) -> list[str]:
    current = date.fromisoformat(origin) if isinstance(origin, str) else origin
    if sessions < 1:
        return []
    out: list[str] = []
    while len(out) < sessions:
        current += timedelta(days=1)
        # Future displayed targets must never rely on an uncertified calendar.
        if is_trading_day(current, require_certified=True):
            out.append(current.isoformat())
    return out


def trading_session_age(observed: str | date | None, as_of: str | date) -> int:
    if not observed:
        return 99
    cursor = date.fromisoformat(str(observed)[:10]) if not isinstance(observed, date) else observed
    end = date.fromisoformat(str(as_of)[:10]) if not isinstance(as_of, date) else as_of
    if cursor >= end:
        return 0
    age = 0
    while cursor < end:
        cursor += timedelta(days=1)
        if is_trading_day(cursor):
            age += 1
    return age
