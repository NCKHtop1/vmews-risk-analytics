import json
import unittest
from datetime import datetime, timedelta, timezone
from scan_private_alpha import compute, validate_rules, evaluate_condition

NOW=datetime(2026,10,23,3,20,tzinfo=timezone.utc)
SOURCE=(NOW-timedelta(minutes=4)).isoformat()
CONFIG={"schemaVersion":1,"rules":[
 {"id":"ALPHA_01","join":"AND","conditions":[
   {"field":"macd","op":"cross_up","otherField":"macdSignal","nearPct":.01},
   {"field":"rsi14","op":"gt","value":50}
 ]},
 {"id":"ALPHA_02","join":"AND","conditions":[
   {"field":"rsi14","op":"cross_down","value":70,"nearPct":.02}
 ]}
]}
SYMBOL={"tier":"CORE","cadence":"LIVE_15M","barDate":"2026-10-23","sourceTime":SOURCE,
 "previous":{"macd":-2,"macdSignal":-1,"rsi14":70.5},
 "current":{"macd":1,"macdSignal":0,"rsi14":68.2}}
SNAP={"status":"ok","sourceTime":SOURCE,"symbols":{"MBB":SYMBOL}}
class PrivateAlphaTests(unittest.TestCase):
    def test_masked_output_contains_ids_and_stages_not_conditions(self):
        result=compute(SNAP,CONFIG,now=NOW)
        self.assertEqual(result["status"],"verified")
        self.assertEqual(len(result["alerts"]),2)
        self.assertEqual({x["alphaId"] for x in result["alerts"]},{"ALPHA_01","ALPHA_02"})
        self.assertEqual(result["states"]["ALPHA_01|MBB"],"confirmed")
        payload=json.dumps(result)
        for secret in ("macd","macdSignal","rsi14","nearPct","conditions","cross_up"):
            self.assertNotIn(secret,payload)
    def test_unchanged_market_snapshot_cannot_resend_alert(self):
        prior=compute(SNAP,CONFIG,now=NOW)
        self.assertIsNone(compute(SNAP,CONFIG,previous=prior,now=NOW))
    def test_stale_and_weekend_sources_fail_closed(self):
        with self.assertRaises(ValueError):
            compute(SNAP,CONFIG,now=NOW+timedelta(hours=2))
        with self.assertRaises(ValueError):
            compute(SNAP,CONFIG,now=datetime(2026,10,24,3,20,tzinfo=timezone.utc))
    def test_near_cross_is_preparing_not_completed_trade(self):
        row={"previous":{"macd":-.1,"macdSignal":0},"current":{"macd":-.005,"macdSignal":0}}
        met,near=evaluate_condition(row,{"field":"macd","op":"cross_up","otherField":"macdSignal","nearPct":.01})
        self.assertFalse(met);self.assertTrue(near)
    def test_reject_proprietary_rules_invalid_and_duplicate(self):
        for extra in ({"id":"BAD","conditions":[{"field":"rsi14","op":"gt","value":50}]},
                      {"id":"ALPHA_01","conditions":[{"field":"unknown","op":"gt","value":3}]}):
            with self.assertRaises(ValueError):
                validate_rules({"schemaVersion":1,"rules":[extra]})
        with self.assertRaises(ValueError):
            validate_rules({"schemaVersion":1,"rules":[CONFIG["rules"][0],CONFIG["rules"][0]]})
    def test_exclude_discovery_and_old_observation_even_if_metric_matches(self):
        source=dict(SNAP)
        source["symbols"]={"AAA":{**SYMBOL,"tier":"DISCOVERY","cadence":"EOD","barDate":"2026-10-20"}}
        out=compute(source,CONFIG,now=NOW)
        self.assertEqual(out["alerts"],[])

if __name__=="__main__":unittest.main()
