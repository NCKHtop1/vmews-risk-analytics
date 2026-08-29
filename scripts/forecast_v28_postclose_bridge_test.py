from __future__ import annotations
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"scripts"))
from forecast_v28_postclose_bridge import bridge_completed_session
VN_TZ=timezone(timedelta(hours=7))

def frame_for(symbols,date_text="2026-08-28"):
    ts=datetime.fromisoformat(f"{date_text}T15:10:00+07:00").timestamp(); rows=[]
    for i,symbol in enumerate(symbols):
        close=50000+i*100
        rows.append({"name":symbol,"exchange":"HOSE","open":close-100,"high":close+200,"low":close-200,"close":close,
                     "change":.5,"volume":1_000_000+i,"update_mode":"streaming","update_time":ts})
    return pd.DataFrame(rows)

def secondary_for(symbols,date_text="2026-08-28",bump=None):
    out={}
    for i,symbol in enumerate(symbols):
        close=50000+i*100+(1000 if symbol==bump else 0)
        out[symbol]=[{"date":date_text,"close":close}]
    return out

def histories(symbols,as_of="2026-08-27"):
    return {s:[{"date":as_of,"open":49000,"high":51000,"low":48500,"close":50000,"modelClose":50000,"volume":900000,"provider":"fixture","exchange":"HOSE"}] for s in symbols}

class PostCloseBridgeTest(unittest.TestCase):
    def test_advances_only_after_two_source_same_day_proof(self):
        symbols=[f"S{i:02d}" for i in range(10)]; h=histories(symbols); freshness={"forecastAsOf":"2026-08-27","currentHOSESymbols":symbols,"providerBySymbol":{}}
        out,meta=bridge_completed_session(h,freshness,now=datetime(2026,8,28,16,tzinfo=VN_TZ),frame=frame_for(symbols),secondary_rows=secondary_for(symbols),min_coverage=.9,min_secondary_coverage=.9)
        self.assertEqual(meta["forecastAsOf"],"2026-08-28"); self.assertEqual(meta["postCloseBridge"]["status"],"PASS")
        self.assertEqual(meta["postCloseBridge"]["secondaryCoverage"],1.0); self.assertEqual(meta["postCloseBridge"]["mismatchCount"],0)
        for s in symbols:
            self.assertEqual(out[s][-1]["date"],"2026-08-28"); self.assertFalse(out[s][-1]["ohlcUnavailable"]); self.assertTrue(out[s][-1]["closeIndependentlyConfirmed"])

    def test_rejects_stale_primary_coverage(self):
        symbols=[f"S{i:02d}" for i in range(10)]; freshness={"forecastAsOf":"2026-08-27","currentHOSESymbols":symbols,"providerBySymbol":{}}
        with self.assertRaises(RuntimeError): bridge_completed_session(histories(symbols),freshness,now=datetime(2026,8,28,16,tzinfo=VN_TZ),frame=frame_for(symbols[:8]),secondary_rows=secondary_for(symbols),min_coverage=.9)
        self.assertEqual(freshness["forecastAsOf"],"2026-08-27")

    def test_rejects_second_source_gap_or_disagreement(self):
        symbols=[f"S{i:02d}" for i in range(10)]
        for secondary in (secondary_for(symbols[:8]),secondary_for(symbols,bump="S01")):
            freshness={"forecastAsOf":"2026-08-27","currentHOSESymbols":symbols,"providerBySymbol":{}}
            with self.assertRaises(RuntimeError): bridge_completed_session(histories(symbols),freshness,now=datetime(2026,8,28,16,tzinfo=VN_TZ),frame=frame_for(symbols),secondary_rows=secondary,min_secondary_coverage=.9)
            self.assertEqual(freshness["postCloseBridge"]["status"],"REJECTED_SECOND_SOURCE")

    def test_preopen_keeps_already_completed_session(self):
        symbols=["FPT","VCB"]; h=histories(symbols); freshness={"forecastAsOf":"2026-08-27","currentHOSESymbols":symbols,"providerBySymbol":{}}
        out,meta=bridge_completed_session(h,freshness,now=datetime(2026,8,28,8,tzinfo=VN_TZ),frame=frame_for(symbols),secondary_rows=secondary_for(symbols),min_coverage=.9)
        self.assertEqual(meta["forecastAsOf"],"2026-08-27"); self.assertEqual(meta["postCloseBridge"]["status"],"NOT_APPLICABLE_ALREADY_CURRENT"); self.assertEqual(out["FPT"][-1]["date"],"2026-08-27")

    def test_weekend_and_holiday_bridge_friday_completed_session(self):
        symbols=["FPT","VCB"]
        for now in (datetime(2026,8,29,9,tzinfo=VN_TZ),datetime(2026,9,2,16,tzinfo=VN_TZ)):
            h=histories(symbols); freshness={"forecastAsOf":"2026-08-27","currentHOSESymbols":symbols,"providerBySymbol":{}}
            out,meta=bridge_completed_session(h,freshness,now=now,frame=frame_for(symbols,"2026-08-28"),secondary_rows=secondary_for(symbols,"2026-08-28"),min_coverage=.9,min_secondary_coverage=.9)
            self.assertEqual(meta["forecastAsOf"],"2026-08-28"); self.assertEqual(meta["postCloseBridge"]["sessionDate"],"2026-08-28"); self.assertEqual(meta["postCloseBridge"]["status"],"PASS"); self.assertEqual(out["FPT"][-1]["date"],"2026-08-28")

if __name__=="__main__": unittest.main(verbosity=2)
