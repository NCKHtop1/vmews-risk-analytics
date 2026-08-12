import importlib.util
import pathlib
from datetime import datetime, time as dtime

BASE_PATH = pathlib.Path(__file__).with_name('radar.py')
spec = importlib.util.spec_from_file_location('vmews_radar_base_eod', BASE_PATH)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

_ORIGINAL_LOAD_ROWS = base.load_rows

def _cash_session(now):
    return now.weekday() < 5 and dtime(8, 45) <= now.time() < dtime(15, 20)

def load_rows_completed_eod(symbol, asof=None, min_rows=None):
    rows, audit = _ORIGINAL_LOAD_ROWS(symbol, asof, min_rows)
    if not asof:
        now = datetime.now(base.VN_TZ)
        if _cash_session(now):
            today = now.date().isoformat()
            before = len(rows)
            rows = [r for r in rows if str(r.get('date') or '') < today]
            removed = before - len(rows)
            if removed:
                audit = {
                    **audit,
                    'completedEodGuard': True,
                    'partialBarsRemoved': removed,
                    'vietnamDate': today,
                    'latestCompletedEod': rows[-1]['date'] if rows else None,
                }
            if len(rows) < int(min_rows or base.MIN_DETAIL_ROWS):
                raise RuntimeError(
                    f'{symbol}: completed-EOD guard leaves only {len(rows)} sessions during the Vietnam cash session'
                )
    return rows, audit

base.load_rows = load_rows_completed_eod
base.VERSION = 'STOCK-EWS-5.3.0-PRODUCTION-EOD-GUARDED'
handler = base.handler
