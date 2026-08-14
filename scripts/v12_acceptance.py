import json,math,pathlib
from datetime import datetime,timezone
ROOT=pathlib.Path('.');DATA=ROOT/'data';failures=[];passes=[]
def check(name,condition,detail=''):
    (passes if condition else failures).append(name if condition else {'name':name,'detail':str(detail)[:800]})
def load(name):
    p=DATA/name;check(f'{name} exists',p.exists(),p);return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
def finite_json(x):
    if isinstance(x,float):return math.isfinite(x)
    if isinstance(x,dict):return all(finite_json(v) for v in x.values())
    if isinstance(x,list):return all(finite_json(v) for v in x)
    return True
model=load('forecast-model-v12.json');current=load('forecast-current-v12.json');dash=load('forecast-dashboard-v12.json');back=load('forecast-backtest-v12.json');audit=load('data-audit-v12.json')
for name,z in [('forecast-model-v12.json',model),('forecast-current-v12.json',current),('forecast-dashboard-v12.json',dash),('forecast-backtest-v12.json',back),('data-audit-v12.json',audit)]:check(f'{name} finite JSON',finite_json(z))
passed=int(audit.get('symbolsPassed') or 0);failed=int(audit.get('symbolsFailed') or 0);routes=audit.get('routes') or {};check('DATA coverage >= 330',passed>=330,{'passed':passed,'failed':failed,'routes':routes});check('DATA route coverage >= 95%',passed/max(1,passed+failed)>=.95,routes);attempted=sum(any(x.get('stage')=='VNSTOCK_PRIMARY' for x in z.get('attempts',[])) for z in (audit.get('symbols') or {}).values());check('DATA VNStock primary attempted on all passed symbols',attempted>=passed*.98,attempted);check('DATA index route available',bool((audit.get('index') or {}).get('rows')),audit.get('index'))
ev=audit.get('eventCoverage') or {};check('EVENT symbols >= 300',int(ev.get('symbols') or 0)>=300,ev);check('EVENT articles >= 10000',int(ev.get('articles') or 0)>=10000,ev);check('EVENT matured outcomes >= 10000',int(ev.get('eventOutcomes') or 0)>=10000,ev);check('RUMOR corpus >= 20',int(ev.get('rumors') or 0)>=20,ev)
features=model.get('featureNames') or []
for bad in ['futureReturn','actualReturn','confirmT2','newsFollowsPrice','matureDate5']:check(f'PIT forbidden feature absent: {bad}',bad not in features)
gov=model.get('governance') or {};check('PIT event governance declared','publishedAt' in str(gov.get('eventPIT')),gov.get('eventPIT'));check('OOF stacking governance declared','OOF' in str(gov.get('stacking')),gov.get('stacking'));check('sealed audit governance declared','sealed' in str(gov.get('sealedAudit')).lower(),gov.get('sealedAudit'))
fc=audit.get('flowCoverage') or {};check('FLOW foreign coverage >= 15%',float(fc.get('foreignCoverage') or 0)>=.15,fc);check('FLOW missingness explicit','foreignAvailable' in features and 'propAvailable' in features)
horizons=model.get('horizons') or {};check('ML direct horizons 1-5 exist',all(str(h) in horizons for h in range(1,6)),list(horizons))
for h in range(1,6):
    z=horizons.get(str(h),{});active=z.get('activeExperts') or [];sealed=z.get('sealedAudit') or {};check(f'T+{h} NUMERICAL active','NUMERICAL' in active,active);check(f'T+{h} REGIME active','REGIME' in active,active);check(f'T+{h} audit n >= 5000',int(sealed.get('n') or 0)>=5000,sealed.get('n'));check(f'T+{h} audit IC finite',math.isfinite(float(sealed.get('rankIC') or 0)));check(f'T+{h} calibration coverage plausible',.45<=float(sealed.get('coverage20_80') or 0)<=.78,sealed.get('coverage20_80'))
    for name in ['EVENT','FLOW','FUNDAMENTAL_EVENT','RUMOR']:check(f'T+{h} expert selection evaluates {name}',name in (z.get('expertPromotion') or {}))
    for name in active:check(f'T+{h} ablation available {name}',name in (z.get('ablation') or {}),z.get('ablation'))
promotion=model.get('promotion') or {};direct=promotion.get('directHorizons') or [];check('MODEL promotion PASS',promotion.get('status')=='PASS',promotion);check('MODEL T+3 and T+5 promoted',3 in direct and 5 in direct,direct);check('MODEL >= 3 horizons promoted',len(direct)>=3,direct)
symbols=current.get('symbols') or {};check('CURRENT symbols >= 320',len(symbols)>=320,len(symbols))
for s,z in list(symbols.items())[:80]:
    close=float(z.get('close') or 0);check(f'{s} current close > 0',close>0,close)
    for h in range(1,6):
        q=(z.get('horizons') or {}).get(str(h),{})
        if not q:continue
        er=float(q.get('expectedReturn'));ep=float(q.get('expectedPrice'));lo=float(q.get('q20'));hi=float(q.get('q80'));pup=float(q.get('probUp'));check(f'{s} T+{h} expected price identity',abs(ep-close*math.exp(er))<=max(1.,ep*1e-9));check(f'{s} T+{h} quantile order',lo<=er<=hi,(lo,er,hi));check(f'{s} T+{h} probability valid',0<=pup<=1,pup)
cases=back.get('cases') or {}
for h in range(1,6):
    a=cases.get(str(h)) or [];check(f'BACKTEST T+{h} cases >= 50',len(a)>=50,len(a))
    for x in a[:50]:
        check(f'BACKTEST T+{h} origin valid',bool(x.get('originDate')) and float(x.get('originPrice') or 0)>0);pred=float(x.get('predictedReturn'));ep=float(x.get('expectedPrice'));origin=float(x.get('originPrice'));check(f'BACKTEST T+{h} price/return identity',abs(ep-origin*math.exp(pred))<=max(1.,ep*1e-9))
check('DASH charts cover current universe',len(dash.get('charts') or {})>=len(symbols)*.95,(len(dash.get('charts') or {}),len(symbols)))
for s,a in list((dash.get('charts') or {}).items())[:50]:
    check(f'DASH {s} chart >= 80 rows',len(a)>=80,len(a));check(f'DASH {s} chart chronological',not a or all(a[i]['date']<a[i+1]['date'] for i in range(len(a)-1)))
phase={'version':'VMEWS-PHASE-GATES-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'tests':len(passes)+len(failures),'passed':len(passes),'failed':len(failures),'failures':failures,'phases':{k:not any(str(x['name']).startswith(prefix) for x in failures) for k,prefix in [('data','DATA'),('event','EVENT'),('rumor','RUMOR'),('flow','FLOW'),('ml','MODEL'),('backtest','BACKTEST'),('dashboard','DASH')]}};phase['status']='PASS' if not failures else 'FAIL';(DATA/'phase-gates-v12.json').write_text(json.dumps(phase,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');print(json.dumps(phase,ensure_ascii=False,indent=2));raise SystemExit(1 if failures else 0)
