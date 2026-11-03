import sys
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import news_impact_prospective as p
import hybrid_news_impact as h

NOW="2026-11-03T09:00:00Z"
def news(first="2026-11-03T08:00:00Z",cert=True):
 return {"schema":h.SCHEMA,"status":"SHADOW_ONLY",
         "counts":{"eligibleNotifications":0},
         "publicationPolicy":{"killSwitch":"LOCKED_OFF"},
         "researchCandidates":[{"storyId":"story_fed","family":"RATE_POLICY",
          "collectorFirstSeenAt":first,"sourceTimeCertified":cert,
          "directIssuerMentions":["MBB"],"validatedAffectedTickers":[],
          "validatedAffectedSectors":[],"notificationEligible":False}]}

class ProspectiveTests(unittest.TestCase):
 def test_first_seen_immutable_across_replays(self):
  one=p.merge({},news(),NOW)
  two=p.merge(one,news("2026-11-03T08:40:00Z"),"2026-11-03T09:45:00Z")
  self.assertEqual(one["eventCount"],1)
  self.assertEqual(two["eventCount"],1)
  self.assertEqual(two["newEvents"],0)
  self.assertEqual(two["receiptOrFamilyConflicts"],1)
  self.assertEqual(two["events"][0]["collectorFirstSeenAt"],"2026-11-03T08:00:00+00:00")
  self.assertFalse(two["notificationsEnabled"])
 def test_uncertified_news_never_creates_evidence(self):
  x=p.merge({},news(cert=False),NOW)
  self.assertEqual(x["eventCount"],0)
  self.assertEqual(x["quarantinedWithoutReceipt"],1)
 def test_reject_unreviewed_claimed_impact(self):
  x=news()
  x["researchCandidates"][0]["validatedAffectedTickers"]=["MBB"]
  with self.assertRaisesRegex(ValueError,"claimed"):
   p.merge({},x,NOW)
 def test_corrupt_persisted_ledger_must_not_reset(self):
  with self.assertRaisesRegex(ValueError,"ledger"):
   p.merge({"schema":p.SCHEMA,"events":[{"storyId":"bad"}]},news(),NOW)
 def test_old_news_aged_out(self):
  old=p.merge({},news("2026-01-01T08:00:00Z"),"2026-01-01T09:00:00Z")
  newer=p.merge(old,{"schema":h.SCHEMA,"status":"SHADOW_ONLY","counts":{"eligibleNotifications":0},"publicationPolicy":{"killSwitch":"LOCKED_OFF"},"researchCandidates":[]},NOW)
  self.assertEqual(newer["eventCount"],0)
 def test_reject_wrong_model_approval(self):
  x=news()
  x["publicationPolicy"]["killSwitch"]="OPEN"
  with self.assertRaisesRegex(ValueError,"kill switch"):
   p.merge({},x,NOW)

if __name__=="__main__":
 unittest.main()
