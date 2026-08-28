"""Exchange-calendar aware release-audit wrapper."""
from __future__ import annotations
import forecast_v20_release_audit as legacy
from vn_exchange_calendar import latest_completed_session, trading_session_age

legacy._business_age=lambda observed,as_of: trading_session_age(observed,as_of)
legacy.completed_session=lambda: latest_completed_session()
if __name__=="__main__": legacy.main()
