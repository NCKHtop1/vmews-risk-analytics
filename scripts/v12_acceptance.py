import json,math,pathlib,statistics
from datetime import datetime,timezone
ROOT=pathlib.Path('.');DATA=ROOT/'data';failures=[];passes=[];phase_fail={str(i):[] for i in range(1,10)}
def check(phase,name,condition,detail=''):
    row={'phase':int(phase),'name':name,'detail':str(detail)[:1600]}
    if condition:passes.append(row)
    else:failures.append(row);phase_fail[str(phase)].append(row)
def load(name,phase,required=True):
    p=DATA/name;ok=p.exists();check(phase,f'{name} exists',ok,p)
    if not ok:return {}
    try:return json.loads(p.read_text(encoding='utf-8'))
    except BaseException as e:check(phase,f'{name} parses',False,e);return {}
def finite_json(x):
    if isinstance(x,float):return math.isfinite(x)
    if isinstance(x,dict):return all(finite_json(v) for v in x.values())
    if isinstance(x,list):return all(finite_json(v) for v in x)
    return True
def pct(vals,q):
    a=sorted(float(x) for x in vals if isinstance(x,(int,float)) and math.isfinite(float(x)))
    if not a:return None
    return a[min(len(a)-1,max(0,int(round((len(a)-1)*q))))]
def f(x,d=0.0):
    try:v=float(x);return v if math.isfinite(v) else d
    except:return d
def span_days(a,b):
    try:return (datetime.fromisoformat(str(b)[:10])-datetime.fromisoformat(str(a)[:10])).days
    except:return -1

model=load('forecast-model-v12.json',5);current=load('forecast-current-v12.json',5);dash=load('forecast-dashboard-v12.json',8);back=load('forecast-backtest-v12.json',7);audit=load('data-audit-v12.json',1);eventdb=load('event-intelligence-v12.json',2);flowdb=load('flow-v12.json',4);flowaudit=load('flow-audit-v12.json',4);activeaudit=load('active-flow-audit-v12.json',4)
for ph,name,z in [(5,'forecast-model-v12.json',model),(5,'forecast-current-v12.json',current),(8,'forecast-dashboard-v12.json',dash),(7,'forecast-backtest-v12.json',back),(1,'data-audit-v12.json',audit),(2,'event-intelligence-v12.json',eventdb),(4,'flow-v12.json',flowdb),(4,'flow-audit-v12.json',flowaudit),(4,'active-flow-audit-v12.json',activeaudit)]:check(ph,f'{name} finite JSON',finite_json(z))

# PHASE 1 — DATA FOUNDATION
cur_symbols=current.get('symbols') or {};current_passed=int(audit.get('currentSymbolsPassed') or audit.get('symbolsPassed') or 0);current_failed=int(audit.get('currentSymbolsFailed') or audit.get('symbolsFailed') or 0);current_cov=f(audit.get('currentRouteCoverageRatio'),current_passed/max(1,current_passed+current_failed));routes=audit.get('routes') or {};symbol_audits=audit.get('symbols') or {}
check(1,'current eligible coverage >= 330 symbols',current_passed>=330,{'passed':current_passed,'failed':current_failed,'routes':routes});check(1,'current route coverage >= 95%',current_cov>=.95,current_cov)
attempted=sum(any(x.get('stage')=='VNSTOCK_PRIMARY' for x in (z.get('attempts') or [])) for s,z in symbol_audits.items() if not cur_symbols or s in cur_symbols);check(1,'VNStock primary attempted for >=95% current universe',attempted>=max(1,current_passed)*.95,{'attempted':attempted,'passed':current_passed})
cas=[(z.get('corporateAction') or {}).get('verified') is True for z in symbol_audits.values()];check(1,'corporate-action reconciliation verified >=98%',bool(cas) and sum(cas)/len(cas)>=.98,{'verified':sum(cas),'n':len(cas)})
mads=[z.get('crossSourceReturnMAD') for z in symbol_audits.values() if isinstance(z.get('crossSourceReturnMAD'),(int,float))];check(1,'cross-source return reconciliation p95 <=0.30%',bool(mads) and f(pct(mads,.95),99)<=.003,{'n':len(mads),'p95':pct(mads,.95),'max':max(mads) if mads else None})
# The source capture uses a stricter venue-aware return guard: current-HOSE intervals retain the
# 12% model-return guard while independently verified pre-transfer UPCoM intervals use the
# official asymmetric +/-15% venue band.  Do not reject a valid historical UPCoM move merely
# because a single global 12% constant was previously applied to every venue/date.  Conversely,
# no source record passes if the audited venue guard, ordinary-move guard or corporate-action
# reconciliation reports a violation.
venue_guard_bad=[]
for s,z in symbol_audits.items():
    ca=z.get('corporateAction') or {}
    if ca.get('verified') is not True or ca.get('modelReturnGuardViolation') is True or int(ca.get('ordinaryLargeMoveViolations') or 0)>0 or bool(ca.get('corporateActionViolations') or []):venue_guard_bad.append({'symbol':s,'largestModelLogJump':ca.get('largestModelLogJump'),'historicalVenueTransitionDate':ca.get('historicalVenueTransitionDate'),'preTransferVenue':ca.get('preTransferVenue'),'modelReturnGuardViolation':ca.get('modelReturnGuardViolation'),'ordinaryLargeMoveViolations':ca.get('ordinaryLargeMoveViolations'),'corporateActionViolations':ca.get('corporateActionViolations')})
check(1,'adjusted model jumps respect verified venue-aware guards',not venue_guard_bad,venue_guard_bad[:20])
idx=audit.get('index') or {};check(1,'VNINDEX/index fallback history >=520 rows',int(idx.get('rows') or 0)>=520,idx)
u=audit.get('universeAudit') or {};historical=set((u.get('historicalOnly') or {}).keys());check(1,'survivorship audit present',bool(u),u.keys() if isinstance(u,dict) else None);check(1,'historical-only cohort excluded from current forecast',not historical.intersection(cur_symbols),historical.intersection(cur_symbols))
uni=model.get('universe') or {};check(1,'historical model panel >=120k rows',int(uni.get('rows') or 0)>=120000,uni);history_days=span_days(uni.get('start'),uni.get('end'));check(1,'history spans at least 7 years',history_days>=math.ceil(365.25*7),{'days':history_days,**uni});check(1,'no synthetic padding policy declared','synthetic' in str(audit.get('policy') or '').lower() and 'no' in str(audit.get('policy') or '').lower(),audit.get('policy'))

# PHASE 2 — EVENT INTELLIGENCE
entity=audit.get('entityFilter') or {};streams=entity.get('streamCoverage') or {};ev=audit.get('eventCoverage') or {};es=eventdb.get('summary') or {};records=eventdb.get('records') or []
check(2,'entity gate evaluated >=10k candidates',int(entity.get('input') or 0)>=10000,entity.get('input'));check(2,'entity false positives are actually rejected',int(entity.get('rejected') or 0)>0,entity.get('rejected'));check(2,'ambiguous ticker-language collision tests represented',all(x in set(entity.get('ambiguousSymbols') or []) for x in ['HCM','CDC','GTA','THG','VIP','FIT','NHA']),entity.get('ambiguousSymbols'));check(2,'official evidence stream >=500',int(streams.get('OFFICIAL') or 0)>=500,streams);check(2,'narrative stream >=5000',int(streams.get('MAIN') or streams.get('NARRATIVE') or 0)>=5000,streams)
check(2,'historical event DB >=10k records',int(es.get('records') or 0)>=10000,es);check(2,'historical event DB covers >=300 tickers',int(es.get('symbols') or 0)>=300,es);check(2,'historical event DB spans 2019-or-earlier to 2026',str(es.get('first') or '9999')<='2019-12-31' and str(es.get('last') or '0000')>='2026-06-01',es);check(2,'matured event outcomes >=10k',int(ev.get('eventOutcomes') or 0)>=10000,ev)
required_event={'newsId','publishedAt','availableDate','ticker','sector','source','sourceType','eventType','sentimentScore','materialityScore','noveltyScore','sourceCredibility','confidence','clusterId','priceAtAvailability','priceAfter','abnormalReturn','cumulativeAbnormalReturn','matureDate'};sample=records[:300];check(2,'event DB schema includes PIT/source/event/AR/CAR fields',bool(sample) and all(required_event.issubset(x) for x in sample),set().union(*(set(x) for x in sample[:3])) if sample else None)
source_types=es.get('sourceTypes') or {};check(2,'normalized official source type >=500',int(source_types.get('OFFICIAL') or 0)>=500,source_types);check(2,'normalized narrative source type >=5000',int(source_types.get('NARRATIVE') or 0)>=5000,source_types);check(2,'official stream semantics restored before event/rumor processing',entity.get('officialStreamRestored') is True,entity.get('officialStreamRestored'));features=model.get('featureNames') or [];check(2,'horizon-specific matured Bayesian event priors exist',all(f'eventPriorAR{h}' in features and f'eventPriorHit{h}' in features and f'eventPriorN{h}' in features and f'eventPriorUncertainty{h}' in features for h in range(1,6)),[x for x in features if x.startswith('eventPrior')]);check(2,'event labels never enter numerical featureNames',not any(x in features for x in ['actualReturn','priceAfter','abnormalReturn','cumulativeAbnormalReturn','matureDate1','matureDate5']),[x for x in features if 'mature' in x.lower() or 'actual' in x.lower()])

# PHASE 3 — RUMOR ENGINE
ra=(ev.get('rumorClaimAudit') or (entity.get('rumorClaimAudit') or {}));rumor_records=[x for x in records if x.get('sourceType')=='RUMOR' or x.get('sourceClass')=='RUMOR_UNVERIFIED'];claim_ids=set(x.get('clusterId') for x in rumor_records if x.get('clusterId'));resolved=[x for x in rumor_records if x.get('claimResolutionDate')]
check(3,'rumor corpus >=20 records',len(rumor_records)>=20,len(rumor_records));check(3,'rumor cluster metadata is PIT as-of publication',ra.get('pitClusterMetadata') is True,ra);check(3,'rumor confirmation engine is official-stream aware',ra.get('officialStreamAware') is True,ra);check(3,'rumor claim clustering materialized >=20 clusters',int(ra.get('clusters') or len(claim_ids))>=20,ra);check(3,'rumor claim IDs retained in event DB',len(claim_ids)>=20,len(claim_ids));check(3,'rumor propagation/source-diversity/duplication features exist',all(x in features for x in ['rumorPropagation20','rumorSourceDiversity20','rumorDuplication20']),[x for x in features if x.startswith('rumor')]);check(3,'rumor price and volume lead-lag features exist',all(x in features for x in ['rumorPreMove2','rumorPreMove5','rumorPreVolume20','rumorLeadScore20']),[x for x in features if x.startswith('rumor')]);check(3,'rumor truth-state feature set exists',all(x in features for x in ['rumorConfirmed20','rumorDenied20','rumorUnverified20']),[x for x in features if x.startswith('rumor')]);check(3,'rumor resolution engine finds at least one later official clarification',int(ra.get('resolvedClusters') or len(set(x.get('clusterId') for x in resolved)))>=1,ra);check(3,'rumor PIT governance forbids resolution backfill','never backfilled' in str((model.get('governance') or {}).get('rumorPIT','')).lower(),(model.get('governance') or {}).get('rumorPIT'))

# PHASE 4 — FLOW / FUNDAMENTAL / MARKET REGIME
fs=flowdb.get('summary') or {};fa=flowaudit.get('summary') or {};check(4,'V12 flow archive is used',str((model.get('dataSources') or {}).get('flowVersion','')).startswith('VMEWS-FLOW-12'),model.get('dataSources'));check(4,'flow archive source audit PASS',fs.get('status')=='PASS' and fa.get('status')=='PASS',{'flow':fs,'audit':fa});check(4,'proprietary PIT history has >=80 symbols with 100+ nonzero rows',int(fs.get('prop100plus') or 0)>=80,fs);check(4,'foreign flow PIT coverage >=60%',f(fs.get('foreignCoverage'))>=.60 and int(fs.get('foreign100plus') or 0)>=150,fs);check(4,'flow feature missingness explicit',all(x in features for x in ['foreignAvailable','propAvailable']),[x for x in features if 'Available' in x])
fund=audit.get('fundamentalPIT') or {};check(4,'non-PIT accounting statements are explicitly blocked',fund.get('certified') is False and fund.get('numericalAccountingFeaturesEnabled') is False,fund);check(4,'fundamental event expert exists without pretending quarterly ratios are PIT','FUNDAMENTAL_EVENT' in (model.get('experts') or {}),model.get('experts',{}).keys())
active_like=[x for x in features if any(k in x.lower() for k in ['activebuy','activesell','aggressor','unmatchedbuy','unmatchedsell','difvolumebuysell'])];active_cert=activeaudit.get('certified') is True and activeaudit.get('numericalFeaturesEnabled') is True;active_abstain=activeaudit.get('status')=='ABSTAIN' and activeaudit.get('certified') is False and activeaudit.get('numericalFeaturesEnabled') is False and not active_like;check(4,'active/aggressor flow is either PIT-certified or explicit ABSTAIN',active_cert or active_abstain,{'audit':activeaudit,'activeFeatures':active_like});regime_req=['breadth1','breadth5','breadth20','csad1','csad5','csad20','herdingCompression','turnoverConcentration','leadershipSpread','volumeBreadth'];check(4,'market psychology/regime features complete',all(x in features for x in regime_req),[x for x in regime_req if x not in features])

# PHASE 5 — TRUE ML FORECAST
horizons=model.get('horizons') or {};check(5,'direct ML horizons T+1..T+5 all exist',all(str(h) in horizons for h in range(1,6)),list(horizons));gov=model.get('governance') or {};check(5,'OOF stacking governance explicit','OOF' in str(gov.get('stacking')),gov.get('stacking'));check(5,'Ridge/LightGBM challenger selection explicit','LightGBM' in str(gov.get('modelSelection')) and 'Ridge' in str(gov.get('modelSelection')),gov.get('modelSelection'))
for h in range(1,6):
    z=horizons.get(str(h),{});active=z.get('activeExperts') or [];choices=z.get('expertModelSelection') or {};prom=z.get('expertPromotion') or {};core=prom.get('REGIME_CORE') or {}
    if h==5:
        regime_contract=(core.get('promoted') is ('REGIME' in active) and core.get('sealedLabelsUsed')==0 and core.get('reference')==['NUMERICAL'] and core.get('candidate')==['NUMERICAL','REGIME'] and '70%-80%' in str(core.get('selectionWindow') or '') and core.get('purgeMethod')=='LABEL_MATURITY_DATE')
    else:regime_contract='REGIME' in active
    check(5,f'T+{h} numerical core and audited regime admission contract','NUMERICAL' in active and regime_contract,{'active':active,'REGIME_CORE':core});check(5,f'T+{h} all six expert families evaluated',all(x in choices for x in ['NUMERICAL','REGIME','EVENT','FLOW','FUNDAMENTAL_EVENT','RUMOR']),choices.keys())
    for name in ['EVENT','FLOW','FUNDAMENTAL_EVENT','RUMOR']:
        p=prom.get(name) or {};check(5,f'T+{h} optional {name} has evidence gate',isinstance(p,dict) and 'evidenceGatePassed' in p,p)
        if p.get('promoted'):
            inc=p.get('incrementalICTest') or {};ci=inc.get('bootstrap90') or [None,None];check(5,f'T+{h} promoted {name} has positive incremental OOS value',f(p.get('deltaIC'))>.001 and f(p.get('deltaMAEImprove'))>0 and f(inc.get('pValue'),1)<.0125 and isinstance(ci,list) and len(ci)==2 and isinstance(ci[0],(int,float)) and f(ci[0])>0 and inc.get('test')=='HAC_NEWey_WEST_ONE_SIDED' and inc.get('bootstrap')=='MOVING_BLOCK',p)

# PHASE 6 — DISTRIBUTION / PRICE CONVERSION
for h in range(1,6):
    z=horizons.get(str(h),{});dist=z.get('distributionAudit') or {};sealed=z.get('sealedAudit') or {};check(6,f'T+{h} uses true quantile regression','QUANTILE' in str(dist.get('method','')).upper(),dist);check(6,f'T+{h} q20/q50/q80 declared',dist.get('quantiles')==[.2,.5,.8] or dist.get('quantiles')==[0.2,0.5,0.8],dist);check(6,f'T+{h} conformal calibration has enough observations',int(dist.get('conformalRows') or 0)>=100 and int(dist.get('calibrationRows') or 0)>=100,dist);check(6,f'T+{h} scenario beats no-change MAE baseline',f(sealed.get('scenarioMAEImprove'),-99)>0,sealed.get('scenarioMAEImprove'));check(6,f'T+{h} empirical q20-q80 coverage 52-72%',.52<=f(sealed.get('coverage20_80'))<=.72,sealed.get('coverage20_80'))
# Sample actual user-facing identities, but P(up) only when separately validated.
check(6,'current forecast universe >=320 symbols',len(cur_symbols)>=320,len(cur_symbols))
for s,z in list(cur_symbols.items())[:80]:
    close=f(z.get('close'))
    for h in range(1,6):
        q=(z.get('horizons') or {}).get(str(h),{});check(6,f'{s} T+{h} expected-price identity',bool(q) and close>0 and abs(f(q.get('expectedPrice'))-close*math.exp(f(q.get('expectedReturn'))))<=max(1.,abs(f(q.get('expectedPrice')))*1e-9),q)
        if q.get('priceValidated'):check(6,f'{s} T+{h} validated quantile order',f(q.get('q20'))<=f(q.get('expectedReturn'))<=f(q.get('q80')),q)
        if q.get('directionValidated'):check(6,f'{s} T+{h} validated P(up) numeric',0<=f(q.get('probUp'),-1)<=1,q.get('probUp'))

# PHASE 7 — FULL BACKTEST / MODEL RISK
for h in range(1,6):
    z=horizons.get(str(h),{});active_now=z.get('activeExperts') or [];sealed=z.get('sealedAudit') or {};pbo=z.get('pboAudit') or {};wf=z.get('walkForwardReplay') or {};reg=z.get('regimeAudit') or {};abl=z.get('ablation') or {};check(7,f'T+{h} sealed OOS n>=5000',int(sealed.get('n') or 0)>=5000,sealed);check(7,f'T+{h} rank IC >2%',f(sealed.get('rankIC'))>.02,sealed.get('rankIC'));check(7,f'T+{h} top-bottom spread >0.10%',f(sealed.get('spread'))>.001,sealed.get('spread'));check(7,f'T+{h} daily IC stability >=20 days',int(sealed.get('icDays') or 0)>=20 and f(sealed.get('icPositiveDayShare'))>=.50,sealed);check(7,f'T+{h} PBO audit PASS',pbo.get('status')=='PASS' and int(pbo.get('splits') or 0)>=30 and f(pbo.get('pbo'),1)<=.50,pbo);check(7,f'T+{h} literal walk-forward replay PASS',wf.get('status')=='PASS' and wf.get('futureRowsUsedForTraining') is not None and int(wf.get('futureRowsUsedForTraining'))==0 and len(wf.get('blocks') or [])>=3,wf);check(7,f'T+{h} purge equals horizon',int(wf.get('purgeSessions') or -1)==h,wf.get('purgeSessions'));check(7,f'T+{h} regime audit covers strong/weak/year',all(x in reg for x in ['BREADTH_STRONG','BREADTH_WEAK','BY_YEAR']),reg.keys());check(7,f'T+{h} ablation exists for every active expert',all(x in abl for x in active_now),abl.keys())
    if len(active_now)==1:
        only=active_now[0];az=abl.get(only) or {};check(7,f'T+{h} sole-expert ablation is locked pre-sealed null',az.get('baseline')=='NO_EXPERT_PRESEALED_NULL' and az.get('baselineMethod')=='UNCONDITIONAL_80_85_PLUS_CONFORMAL_85_90' and az.get('selectionLabelsUsed')==0 and az.get('sealedLabelsUsedForSelection')==0 and az.get('usedForSelection') is False and az.get('baselineCalibrationWindow')=='80%-85%' and az.get('baselineConformalWindow')=='85%-90%' and az.get('sealedAuditWindow')=='90%-100%' and int(az.get('baselineCalibrationRows') or 0)>=100 and int(az.get('baselineConformalRows') or 0)>=100,az)
    # Direction is optional for display, but if declared PASS it must truly beat base rate.
    if z.get('directionStatus')=='PASS':check(7,f'T+{h} validated direction beats base rate',f(sealed.get('brierSkill'),-99)>0 and f(sealed.get('balancedAccuracy'))>.51 and f(sealed.get('mcc'))>.015,sealed)
    cases=(back.get('cases') or {}).get(str(h)) or [];check(7,f'T+{h} auditable historical cases >=50',len(cases)>=50,len(cases))
    for x in cases[:30]:
        origin=f(x.get('originPrice'));pred=f(x.get('predictedReturn'));ep=f(x.get('expectedPrice'));ctx=x.get('contextAtOrigin') or {};check(7,f'T+{h} historical expected-price identity',origin>0 and abs(ep-origin*math.exp(pred))<=max(1.,abs(ep)*1e-9),x);check(7,f'T+{h} T0 evidence snapshot retained',all(k in ctx for k in ['prior20','breadth20','newsN20','rumorN20','foreignAvailable','propAvailable']),ctx.keys());check(7,f'T+{h} actual future raw price retained',isinstance(x.get('actualRawPrice'),(int,float)) and f(x.get('actualRawPrice'))>0,x.get('actualRawPrice'))
promotion=model.get('promotion') or {};check(7,'all five direct price horizons pass final model-risk gates',promotion.get('status')=='PASS' and promotion.get('directPriceHorizons')==[1,2,3,4,5],promotion)

# PHASE 8 — UI / DATA CONTRACT
js=(ROOT/'forecast-final-v12.js').read_text(encoding='utf-8') if (ROOT/'forecast-final-v12.js').exists() else '';html=(ROOT/'forecast-final.html').read_text(encoding='utf-8') if (ROOT/'forecast-final.html').exists() else ''
check(8,'V12 frontend asset exists',bool(js));check(8,'direct expectedPrice is used in chart','expectedPrice' in js and 'q20Price' in js and 'q80Price' in js);check(8,'chart tooltip/hover implementation present',any(x in js.lower() for x in ['tooltip','mousemove','hover']));check(8,'frontend respects priceValidated gate','priceValidated' in js);check(8,'frontend respects directionValidated gate','directionValidated' in js);check(8,'evidence contribution UI present','expertContributions' in js);check(8,'rumor intelligence UI present','rumor' in js.lower());check(8,'backtest drilldown present','backtest' in js.lower() and 'actualRawPrice' in js);check(8,'page labels forecast as research not trade signal','research' in (html+js).lower())
check(8,'dashboard charts cover >=95% current universe',len(dash.get('charts') or {})>=len(cur_symbols)*.95,(len(dash.get('charts') or {}),len(cur_symbols)))

# PHASE 9 — PRODUCTION PRECONDITIONS. Browser/CDN/hash/outage are completed by the release workflow after this research gate.
check(9,'research model is fully promotable before release workflow',promotion.get('status')=='PASS',promotion);check(9,'V12 flow archive is immutable-input candidate',str(flowdb.get('version','')).startswith('VMEWS-FLOW-12'),flowdb.get('version'));check(9,'data source paths/version are recorded',bool(model.get('dataSources')),model.get('dataSources'));check(9,'no unvalidated current price is presented as validated',all(all((not q.get('priceValidated')) or (horizons.get(str(h),{}).get('priceStatus')=='PASS') for h,q in [(int(k),v) for k,v in (z.get('horizons') or {}).items()]) for z in cur_symbols.values()),'validation mismatch')

phase={
    'version':'VMEWS-PHASE-GATES-12.6.0','generatedAt':datetime.now(timezone.utc).isoformat(),'tests':len(passes)+len(failures),'passed':len(passes),'failed':len(failures),'failures':failures,
    'phases':{str(i):{'name':{1:'Data foundation',2:'Event Intelligence',3:'Rumor Engine',4:'Flow/Fundamental/Market regime',5:'True ML forecast',6:'Distribution',7:'Full backtest',8:'UI contract',9:'Production preconditions'}[i],'status':'PASS' if not phase_fail[str(i)] else 'FAIL','failed':len(phase_fail[str(i)])} for i in range(1,10)}
};phase['status']='PASS' if not failures else 'FAIL';(DATA/'phase-gates-v12.json').write_text(json.dumps(phase,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');print(json.dumps(phase,ensure_ascii=False,indent=2));raise SystemExit(1 if failures else 0)