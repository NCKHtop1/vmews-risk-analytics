import copy
import gzip
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from forecast_freshness_audit import audit
from forecast_v16_external_data import load_fund_universe, SourceError
from vn_exchange_calendar import VN_TZ

class FreshnessTest(unittest.TestCase):
    def artifacts(self):
        row={'date':'2026-09-28','close':65000,'dataFreshness':'CURRENT','horizons':{str(n):{'targetDate':day} for n,day in enumerate(['2026-09-29','2026-09-30','2026-10-01','2026-10-02','2026-10-05'],1)}}
        dash={'asOf':'2026-09-28','generatedAt':'2026-09-29T03:30:00+07:00','symbols':{'FPT':row},'charts':{'FPT':[{'date':'2026-09-28','close':65000,'rawClose':65000}]}}
        return dash,copy.deepcopy(dash),copy.deepcopy(dash)
    def test_morning_requires_previous_completed_session_and_all_targets(self):
        docs=self.artifacts();now=datetime(2026,9,29,5,tzinfo=VN_TZ)
        self.assertEqual(audit(*docs,now=now)['status'],'PASS')
        docs[0]['symbols']['FPT']['horizons']['1']['targetDate']='2026-09-28'
        self.assertEqual(audit(*docs,now=now)['status'],'FAIL')
    def test_stale_symbol_is_rejected_even_with_current_header(self):
        docs=self.artifacts();docs[0]['symbols']['FPT']['date']='2026-09-25'
        self.assertIn('FPT: STALE_PRICE',audit(*docs,now=datetime(2026,9,29,6,tzinfo=VN_TZ))['errors'][0])
    def test_fund_mapping_uses_full_listing_not_forecast_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.json.gz'
            symbols=[f'{a}{b}{c}' for a in 'ABC' for b in 'ABCDEFGHIJKL' for c in 'ABCDEFGHIJKL']
            with gzip.open(p,'wt') as f:json.dump({'currentHOSESymbols':symbols},f)
            self.assertEqual(load_fund_universe(p),set(symbols))
            p=Path(tmp)/'dashboard.json';p.write_text(json.dumps({'symbols':dict.fromkeys(symbols[:366],{})}))
            self.assertEqual(len(load_fund_universe(p)),366)
            p.write_text(json.dumps({'symbols':{'FPT':{}}}))
            with self.assertRaises(SourceError):load_fund_universe(p)

if __name__=='__main__':unittest.main()
