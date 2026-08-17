from types import SimpleNamespace
import v12_reference_resilience as r

# Eliminate wall-clock sleeping in the deterministic unit regression.
r.time.sleep=lambda *_:None

class Base:
    def __init__(self):self.y=0;self.t=0
    def yahoo_history(self,symbol):
        self.y+=1
        if self.y==1:raise RuntimeError('ReadTimeout: transient')
        return [{'date':'2026-01-01','close':1}],{'provider':'TEST'}
    def _throttle_vnstock(self):self.t+=1

base=Base();vci_calls={'n':0}
def vci(symbol,attempts):
    vci_calls['n']+=1
    if vci_calls['n']==1:
        attempts.append({'stage':'VCI_CORPORATE_ACTION_EVENT_REFERENCE','ok':False,'error':'HTTP 429 rate limit exceeded'})
        return set(),None
    audit={'source':'TEST_VCI','eventCount':1,'exrightDateCount':1}
    attempts.append({'stage':'VCI_CORPORATE_ACTION_EVENT_REFERENCE','ok':True,**audit})
    return {'2025-12-01'},audit

c=SimpleNamespace(base=base,_vci_corporate_action_dates=vci)
a=r.install(c,max_attempts=3,backoff_seconds=(0,0))
rows,ya=c.base.yahoo_history('AAA')
assert base.y==2 and ya['referenceAttempts']==2,(base.y,ya)
attempts=[];dates,va=c._vci_corporate_action_dates('AAA',attempts)
assert dates=={'2025-12-01'} and vci_calls['n']==2 and base.t==2,(dates,vci_calls,base.t,attempts)
assert va['referenceAttempts']==2 and a['gateMutation'] is False and a['priceOrReturnMutation'] is False

# Permanent 404 must remain fail-safe and must not be retried.
class PermanentBase:
    def __init__(self):self.y=0;self.t=0
    def yahoo_history(self,symbol):self.y+=1;raise RuntimeError('HTTP Error 404: Not Found')
    def _throttle_vnstock(self):self.t+=1
pb=PermanentBase();pv={'n':0}
def permanent_vci(symbol,attempts):
    pv['n']+=1;attempts.append({'stage':'VCI_CORPORATE_ACTION_EVENT_REFERENCE','ok':False,'error':'HTTP Error 404: Not Found'});return set(),None
c2=SimpleNamespace(base=pb,_vci_corporate_action_dates=permanent_vci)
r.install(c2,max_attempts=3,backoff_seconds=(0,0))
try:c2.base.yahoo_history('ZZZ');raise AssertionError('404 unexpectedly accepted')
except RuntimeError as exc:assert '404' in str(exc)
assert pb.y==1,pb.y
a2=[];d2,v2=c2._vci_corporate_action_dates('ZZZ',a2)
assert pv['n']==1 and v2 is None and pb.t==1,(pv,pb.t,a2)
print('V12 REFERENCE RESILIENCE TEST PASS')
