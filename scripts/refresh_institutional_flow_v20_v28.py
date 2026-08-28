"""Holiday-aware production wrapper for V20 institutional-flow refresh."""
from __future__ import annotations
from datetime import datetime, timedelta
import refresh_institutional_flow_v20 as legacy
from vn_exchange_calendar import VN_TZ, is_trading_day


def completed_session(now=None):
    local=(now or datetime.now(VN_TZ)).astimezone(VN_TZ); session=local.date()
    if is_trading_day(session) and local.timetz().replace(tzinfo=None)<legacy.FLOW_READY_AFTER:
        session-=timedelta(days=1)
    while not is_trading_day(session): session-=timedelta(days=1)
    return session

legacy.completed_session=completed_session
if __name__=="__main__": legacy.main()
