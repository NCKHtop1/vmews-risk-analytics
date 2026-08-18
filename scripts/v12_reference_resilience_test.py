from types import SimpleNamespace
import v12_reference_resilience as r

# Eliminate wall-clock sleeping in the deterministic unit regression while recording policy.
sleeps=[]
r.time.sleep=lambda seconds:sleeps.append(float(seconds))

class Base:
    def __init__(self):self.y=0;self.t=0
    def yahoo_history(self,symbol):
        self.y+=1
        if self.y==1:raise RuntimeError('ReadTimeout: transient')
        return [{'date':'2026-01-01','close':1}],{'provider':'TEST'}
    def _throttle_vnstock(self):self.t+=1

base=Base();vci_calls={'n':0};unified_calls={'n':0};provider_calls={'n':0}
def vci(symbol,attempts):
    vci_calls['n']+=1
    if vci_calls['n']==1:
        attempts.append({'stage':'VCI_CORPORATE_ACTION_EVENT_REFERENCE','ok':False,'error':'HTTP 429 rate limit exceeded'})
        return set(),None
    audit={'source':'TEST_VCI','eventCount':1,'exrightDateCount':1}
    attempts.append({'stage':'VCI_CORPORATE_ACTION_EVENT_REFERENCE','ok':True,**audit})
    return {'2025-12-01'},audit

def unified(symbol,years,attempts,stage='VNSTOCK_PRIMARY'):
    unified_calls['n']+=1
    if unified_calls['n']==1:
        attempts.append({'stage':stage,'ok':False,'providerCode':'UNIFIED','error':'SystemExit: Rate limit exceeded; wait 56 seconds'})
        return None
    audit={'providerCode':'UNIFIED','rows':700}
    attempts.append({'stage':stage,'ok':True,**audit})
    return ([{'date':'2026-01-01','close':1}],audit)

def provider(symbol,source,start,end,attempts,stage):
    provider_calls['n']+=1
    if provider_calls['n']==1:
        attempts.append({'stage':stage,'ok':False,'providerCode':source,'reason':'provider_error','error':'HTTP 429 Too Many Requests'})
        return None
    audit={'providerCode':source,'rows':700}
    attempts.append({'stage':stage,'ok':True,**audit})
    return ([{'date':'2026-01-01','close':1}],audit)

c=SimpleNamespace(base=base,_vci_corporate_action_dates=vci,_capture_unified=unified,_capture_provider=provider)
a=r.install(c,max_attempts=3,backoff_seconds=(0,0))
rows,ya=c.base.yahoo_history('AAA')
assert base.y==2 and ya['referenceAttempts']==2,(base.y,ya)
attempts=[];dates,va=c._vci_corporate_action_dates('AAA',attempts)
assert dates=={'2025-12-01'} and vci_calls['n']==2 and base.t==2,(dates,vci_calls,base.t,attempts)
assert va['referenceAttempts']==2
ua=[];u=c._capture_unified('AAA',8,ua,'VNSTOCK_PRIMARY')
assert u is not None and unified_calls['n']==2 and ua[-1]['sourceAttempts']==2,(u,unified_calls,ua)
pa=[];p=c._capture_provider('AAA','VCI','2020-01-01','2026-01-01',pa,'VNSTOCK_VCI_RECOVERY')
assert p is not None and provider_calls['n']==2 and pa[-1]['sourceAttempts']==2,(p,provider_calls,pa)
assert sum(1 for x in sleeps if x>=r._RATE_LIMIT_COOLDOWN_SECONDS)==3,sleeps
assert a['gateMutation'] is False and a['priceOrReturnMutation'] is False and a['version']=='VMEWS-V12-REFERENCE-RESILIENCE-1.3.0'
assert a['unifiedTransientCircuit'] is True and a['yahooReferenceTransientCircuit'] is True

# Permanent 404 must remain fail-safe and must not be retried.
class PermanentBase:
    def __init__(self):self.y=0;self.t=0
    def yahoo_history(self,symbol):self.y+=1;raise RuntimeError('HTTP Error 404: Not Found')
    def _throttle_vnstock(self):self.t+=1
pb=PermanentBase();pv={'n':0};pu={'n':0};pp={'n':0}
def permanent_vci(symbol,attempts):
    pv['n']+=1;attempts.append({'stage':'VCI_CORPORATE_ACTION_EVENT_REFERENCE','ok':False,'error':'HTTP Error 404: Not Found'});return set(),None
def permanent_unified(symbol,years,attempts,stage='VNSTOCK_PRIMARY'):
    pu['n']+=1;attempts.append({'stage':stage,'ok':False,'error':'ValueError: malformed permanent response'});return None
def permanent_provider(symbol,source,start,end,attempts,stage):
    pp['n']+=1;attempts.append({'stage':stage,'ok':False,'error':'ValueError: malformed permanent response'});return None
c2=SimpleNamespace(base=pb,_vci_corporate_action_dates=permanent_vci,_capture_unified=permanent_unified,_capture_provider=permanent_provider)
r.install(c2,max_attempts=3,backoff_seconds=(0,0))
try:c2.base.yahoo_history('ZZZ');raise AssertionError('404 unexpectedly accepted')
except RuntimeError as exc:assert '404' in str(exc)
assert pb.y==1,pb.y
a2=[];d2,v2=c2._vci_corporate_action_dates('ZZZ',a2)
assert pv['n']==1 and v2 is None and pb.t==1,(pv,pb.t,a2)
u2=[];assert c2._capture_unified('ZZZ',8,u2) is None and pu['n']==1,(pu,u2)
p2=[];assert c2._capture_provider('ZZZ','VCI','a','b',p2,'RECOVERY') is None and pp['n']==1,(pp,p2)

# A deep symbol that failed CA certification only because its first pass hit an explicit
# transient provider window gets exactly one clean second pass. A permanent data
# disagreement remains fail-safe and is not retried.
class StoreBase:
    MIN_ROWS=520
    def yahoo_history(self,symbol):return [],{}
    def _throttle_vnstock(self):pass
sb=StoreBase();retry_calls=[];reset_calls=[]
def store_vci(symbol,attempts):return set(),{}
def store_unified(symbol,years,attempts,stage='VNSTOCK_PRIMARY'):return None
def store_provider(symbol,source,start,end,attempts,stage):return None
sample_rows=[{'date':'2020-01-01','close':1}]*520
def initial_build(symbols):
    return (
        {'AAA':list(sample_rows),'BBB':list(sample_rows)},
        {
            'AAA':{'originalRows':520,'eligible':False,'corporateAction':{'verified':False},'attempts':[{'stage':'VCI','ok':False,'error':'HTTP 429 rate limit'}]},
            'BBB':{'originalRows':520,'eligible':False,'corporateAction':{'verified':False},'attempts':[{'stage':'QUALITY','ok':False,'error':'permanent data disagreement'}]},
        },
        {},
    )
def second_pass(symbol):
    retry_calls.append(symbol)
    return list(sample_rows),{'originalRows':520,'eligible':True,'corporateAction':{'verified':True},'attempts':[{'stage':'RETRY','ok':True}]}
c3=SimpleNamespace(
    base=sb,_vci_corporate_action_dates=store_vci,_capture_unified=store_unified,
    _capture_provider=store_provider,build_source_capture_store=initial_build,
    capture_price_history=second_pass,reset_provider_circuits=lambda:reset_calls.append(1),
)
a3=r.install(c3,max_attempts=3,backoff_seconds=(0,0))
store3,audits3,failures3=c3.build_source_capture_store(['AAA','BBB'])
assert retry_calls==['AAA'],retry_calls
assert audits3['AAA']['eligible'] is True and audits3['AAA']['sourceStoreRecovery']['accepted'] is True,audits3['AAA']
assert [x['stage'] for x in audits3['AAA']['attempts']]==['VCI','SOURCE_STORE_TRANSIENT_RECOVERY_BOUNDARY','RETRY']
assert audits3['BBB']['eligible'] is False and 'sourceStoreRecovery' not in audits3['BBB'],audits3['BBB']
assert len(reset_calls)==1 and sum(1 for x in sleeps if x>=r._RATE_LIMIT_COOLDOWN_SECONDS)==4,(reset_calls,sleeps)
assert a3['sourceStoreTransientSecondPass'] is True and a3['gateMutation'] is False and a3['priceOrReturnMutation'] is False

# A symbol that was not captured at all because every route hit a transient outage also
# gets one clean second pass. This repairs transport failure only; it does not alter gates.
failure_retry_calls=[]
def initial_failure_build(symbols):
    return {},{},{
        'CCC':{
            'error':'transient outage',
            'attempts':[{'stage':'VNSTOCK_PRIMARY','ok':False,'error':'ReadTimeout: provider unavailable'}],
        },
        'DDD':{
            'error':'permanent bad data',
            'attempts':[{'stage':'VNSTOCK_PRIMARY','ok':False,'error':'ValueError: malformed payload'}],
        },
    }
def failure_second_pass(symbol):
    failure_retry_calls.append(symbol)
    return list(sample_rows),{
        'eligible':False,
        'corporateAction':{'verified':True},
        'attempts':[{'stage':'RETRY_CAPTURE','ok':True}],
    }
c4=SimpleNamespace(
    base=sb,_vci_corporate_action_dates=store_vci,_capture_unified=store_unified,
    _capture_provider=store_provider,build_source_capture_store=initial_failure_build,
    capture_price_history=failure_second_pass,reset_provider_circuits=lambda:None,
)
a4=r.install(c4,max_attempts=2,backoff_seconds=(0,0))
store4,audits4,failures4=c4.build_source_capture_store(['CCC','DDD'])
assert failure_retry_calls==['CCC'],failure_retry_calls
assert 'CCC' in store4 and 'CCC' in audits4 and 'CCC' not in failures4,(store4,audits4,failures4)
assert audits4['CCC']['sourceStoreRecovery']['accepted'] is True,audits4['CCC']
assert audits4['CCC']['eligible'] is False,audits4['CCC']
assert 'DDD' in failures4 and 'DDD' not in store4,failures4
assert a4['sourceStoreTransientCaptureFailureSecondPass'] is True

# Provider-wide transient outages must stop consuming the time budget symbol-by-symbol.
# Two symbols may exhaust the bounded retry policy; the third is short-circuited without
# another underlying network call. Resetting circuits permits a later clean second pass.
class OutageBase:
    def __init__(self):self.y=0;self.t=0
    def yahoo_history(self,symbol):
        self.y+=1
        raise RuntimeError('ReadTimeout: provider-wide outage')
    def _throttle_vnstock(self):self.t+=1
ob=OutageBase();ou={'n':0};reset5=[]
def outage_vci(symbol,attempts):return set(),{}
def outage_unified(symbol,years,attempts,stage='VNSTOCK_PRIMARY'):
    ou['n']+=1
    attempts.append({'stage':stage,'ok':False,'providerCode':'UNIFIED','error':'ReadTimeout: provider-wide outage'})
    return None
def outage_provider(symbol,source,start,end,attempts,stage):return None
c5=SimpleNamespace(
    base=ob,_vci_corporate_action_dates=outage_vci,_capture_unified=outage_unified,
    _capture_provider=outage_provider,reset_provider_circuits=lambda:reset5.append(1),
)
a5=r.install(c5,max_attempts=2,backoff_seconds=(0,0))
for symbol in ('AAA','BBB'):
    try:c5.base.yahoo_history(symbol);raise AssertionError('transient outage unexpectedly succeeded')
    except RuntimeError:pass
assert ob.y==4,ob.y
try:c5.base.yahoo_history('CCC');raise AssertionError('open Yahoo circuit unexpectedly called provider')
except RuntimeError as exc:assert 'provider_circuit_open' in str(exc),str(exc)
assert ob.y==4,ob.y

for symbol in ('AAA','BBB'):
    attempts=[]
    assert c5._capture_unified(symbol,8,attempts) is None,(symbol,attempts)
assert ou['n']==4,ou
attempts=[]
assert c5._capture_unified('CCC',8,attempts) is None
assert ou['n']==4,(ou,attempts)
assert attempts[-1]['reason']=='provider_circuit_open' and attempts[-1]['providerCircuitOpen'] is True,attempts

c5.reset_provider_circuits()
assert len(reset5)==1,reset5
try:c5.base.yahoo_history('DDD');raise AssertionError('reset Yahoo outage unexpectedly succeeded')
except RuntimeError:pass
assert ob.y==6,ob.y
attempts=[];assert c5._capture_unified('DDD',8,attempts) is None
assert ou['n']==6,(ou,attempts)
assert a5['componentCircuitTerminalFailures']==2 and a5['gateMutation'] is False

print('V12 REFERENCE RESILIENCE + RUN-LOCAL OUTAGE CIRCUIT TEST PASS')
