import math,pathlib,sys,types
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
ROOT=pathlib.Path(__file__).resolve().parent
parts=sorted((ROOT/'v12_train_parts').glob('*.pyinc'))
code='\n'.join(p.read_text(encoding='utf-8') for p in parts)
ns={'__name__':'v12_method_unit','__file__':str(ROOT/'train_forecast_v12.py')}
exec(compile(code,'v12-method-unit-assembled.py','exec'),ns,ns)
assert callable(ns.get('run_v12_pipeline'))

# Quantile + conformal runtime, including strictly pre-blind return shrinkage.
rng=np.random.default_rng(73)
score=rng.normal(size=2500)
y=.004*score+rng.normal(scale=.018,size=len(score))
layer,iso,qadj=ns['calibrate'](y[:1200],score[:1200],y[1200:1800],score[1200:1800])
p,med,lo,hi,n=ns['apply_calibration'](score[1800:],layer,iso,qadj)
assert len(p)==700 and np.all(np.isfinite(p)) and np.all(np.isfinite(med))
assert np.all(lo<=med) and np.all(med<=hi) and np.all((p>=0)&(p<=1))
assert 'QUANTILE' in str(getattr(layer,'method','')).upper()
assert .25<=float(getattr(layer,'returnShrink',0))<=1.0
assert int(getattr(layer,'shrinkSelectionN',0))>=100 and int(getattr(layer,'conformalN',0))>=100
assert '90-100% remains sealed' in str(getattr(layer,'calibrationSplitPolicy',''))

# A deliberately over-magnified median must be shrunk using calibration rows only.
ysh=rng.normal(scale=.012,size=1200);msh=2.0*ysh+rng.normal(scale=.002,size=1200);g,gn,ga=ns['_select_return_shrink'](ysh,msh)
assert gn==1200 and .25<=g<.8,(g,ga)
assert ga['selectedMAE']<ga['baseMAE'],ga

# Exact maturity purge: panel origins can be sampled every 5 sessions, but labels are purged by their real maturity date, never by origin ordinal distance.
dates=np.asarray([f'2025-{1+(i//28):02d}-{1+(i%28):02d}' for i in range(196)],dtype=object)
D=np.repeat(dates,3)
def mature_for_h(h):
    by={d:(dates[i+h] if i+h<len(dates) else '9999-12-31') for i,d in enumerate(dates)}
    return np.asarray([by[d] for d in D],dtype=object)
ns['V12_LABEL_MATURITY']={h:mature_for_h(h) for h in range(1,6)}
ns['V12_ACTIVE_HORIZON']=5
m=ns['interval_masks'](D,dates);M5=ns['V12_LABEL_MATURITY'][5];i80=int(.80*len(dates));i85=int(.85*len(dates));i90=int(.90*len(dates));d80,d85,d90=dates[i80],dates[i85],dates[i90]
assert np.all(~m['calA'] | ((D>=d80)&(D<d85)&(M5<d85)))
assert np.all(~m['calB'] | ((D>=d85)&(D<d90)&(M5<d90)))
assert np.all(~m['audit'] | (D>=d90))
valid=np.ones(len(D),dtype=bool);tr,te=ns['date_mask'](D,dates,.70,.80,5,valid);test_start=dates[int(.70*len(dates))]
assert np.all(M5[tr]<test_start),('maturity leak',max(M5[tr]),test_start)
assert np.all((D[te]>=test_start)&(D[te]<dates[int(.80*len(dates))]))

# Incremental IC significance on repeated cross-sections.
days=np.asarray([f'2026-01-{1+i:02d}' for i in range(20) for _ in range(30)])
y2=rng.normal(size=len(days));base=rng.normal(size=len(days));candidate=y2*.75+rng.normal(scale=.35,size=len(days));inc=ns['_incremental_ic_test'](y2,base,candidate,days);assert inc['days']>=15 and inc['meanDeltaIC']>0 and inc['pValue']<.0125 and inc['bootstrap90'][0]>0,inc

# CSCV/PBO uses only the architecture path admissible after pre-sealed promotion.
dates3=np.asarray([f'{2020+i//240:04d}-{1+(i//20)%12:02d}-{1+i%20:02d}' for i in range(100)])
D3=np.repeat(dates3,25);latent=rng.normal(size=len(D3));y3=.03*latent+rng.normal(scale=.03,size=len(D3));ep={'NUMERICAL':latent+rng.normal(scale=.7,size=len(D3)),'REGIME':.4*latent+rng.normal(size=len(D3)),'EVENT':rng.normal(size=len(D3)),'FLOW':rng.normal(size=len(D3)),'FUNDAMENTAL_EVENT':rng.normal(size=len(D3)),'RUMOR':rng.normal(size=len(D3))};pbo=ns['_pbo_metric'](ep,y3,D3,['NUMERICAL','REGIME']);assert pbo['splits']>=30 and pbo['candidateCount']==3 and 0<=pbo['pbo']<=1,pbo
assert pbo['candidatePolicy']=='ADMISSIBLE_SELECTION_PATH' and set(pbo['rejectedOptionalExcluded'])=={'EVENT','FLOW','FUNDAMENTAL_EVENT','RUMOR'},pbo

# Current-route availability is explicitly separate from >=520-row model eligibility.
assert callable(ns.get('_probe_current_short_route'))
source=pathlib.Path(ROOT/'v12_train_parts'/'00c_universe.pyinc').read_text(encoding='utf-8')
for token in ('currentTrainingEligible','currentRoutePassed','currentShortHistoryRoutePassed','trainingEligible'):
    assert token in source,token
assert 'len(rows)>=60' in source and 'currentCoverage' in source

# Current sector taxonomy is descriptive-only. Historical numerical event features must be invariant
# to the current taxonomy, while the current reference builder may enrich coverage from VCI.
sector_rows=[
    {'symbol':'AAA','icb_level':1,'icb_name':'Industrials'},
    {'symbol':'AAA','icb_level':2,'icb_name':'Capital Goods'},
    {'symbol':'AAA','icb_level':4,'icb_name':'Machinery'},
    {'symbol':'BBB','icb_level':1,'icb_name':'Financials'},
]
sm=ns['_sector_reference_from_rows'](sector_rows);assert sm['AAA']=='Capital Goods' and sm['BBB']=='Financials',sm
old_vnstock_sector=sys.modules.get('vnstock')
class _SectorDF:
    def to_dict(self,orient):assert orient=='records';return list(sector_rows)
class _SectorListing:
    def __init__(self,source='VCI'):assert source=='VCI'
    def symbols_by_industries(self,show_log=False):return _SectorDF()
fake_sector_pkg=types.ModuleType('vnstock');fake_sector_pkg.Listing=_SectorListing;sys.modules['vnstock']=fake_sector_pkg
try:
    merged=ns['build_sector_map']({'ranking':[{'symbol':'CCC','sector':'Seed Sector'}]})
    assert merged['AAA']=='Capital Goods' and merged['BBB']=='Financials' and merged['CCC']=='Seed Sector',merged
    assert ns['build_sector_map'].last_audit['providerStatus']=='PASS' and ns['build_sector_map'].last_audit['providerSymbols']==2,ns['build_sector_map'].last_audit
finally:
    if old_vnstock_sector is None:sys.modules.pop('vnstock',None)
    else:sys.modules['vnstock']=old_vnstock_sector
edates=[f'2026-01-{i:02d}' for i in range(1,31)]+[f'2026-02-{i:02d}' for i in range(1,11)]
prows=[{'date':d,'close':100.0+i,'modelClose':100.0+i,'volume':1000.0} for i,d in enumerate(edates)]
sent={'symbols':{'AAA':{'items':[{'id':'sector-pit-1','publishedAt':edates[10]+'T08:00:00+07:00','title':'AAA current taxonomy must not enter history','label':'POS','sourceQuality':1.0,'materiality':1.0,'confidence':1.0,'event':'GENERAL'}]}}}
arts,outcomes=ns['prepare_articles'](sent,{'AAA':prows},{'AAA':'TECH'},[]);assert arts['AAA'][0]['sector']=='OTHER',arts['AAA'][0]
sa=ns['EvidenceFeatureStore'](arts,outcomes,{'AAA':'TECH'});sb=ns['EvidenceFeatureStore'](arts,outcomes,{'AAA':'BANK'})
assert sa.sector_map=={} and sb.sector_map=={} and sa.current_reference_sector_map['AAA']=='TECH' and sb.current_reference_sector_map['AAA']=='BANK'
fa=sa.features('AAA',edates[20]);fb=sb.features('AAA',edates[20]);keys=ns['EVENT_FEATURES']+ns['RUMOR_FEATURES'];assert all(abs(float(fa[k])-float(fb[k]))<1e-15 for k in keys),(fa,fb)

# Exercise VNStock short-history, provider quota SystemExit, and cached-history fallback.
# A provider-level sys.exit must become route evidence, never terminate the training process.
ds=ns['_v12ds'];probe=ns['_probe_current_short_route'];old_norm=ds._normalize_df;old_throttle=ds._throttle_vnstock;old_yahoo=ds.yahoo_history;old_cached=ds.cached_history
old_vnstock=sys.modules.get('vnstock');old_vnstock_ui=sys.modules.get('vnstock.ui')
rows80=[{'date':'2026-08-14','open':10000.0,'high':10000.0,'low':10000.0,'close':10000.0,'volume':1.0} for _ in range(80)]
class _FakeMarket:
    def equity(self,symbol):return self
    def ohlcv(self,**kwargs):return object()
fake_pkg=types.ModuleType('vnstock');fake_ui=types.ModuleType('vnstock.ui');fake_ui.Market=_FakeMarket;fake_pkg.ui=fake_ui
sys.modules['vnstock']=fake_pkg;sys.modules['vnstock.ui']=fake_ui
try:
    ds._throttle_vnstock=lambda:None
    ds._normalize_df=lambda df,symbol,provider:(list(rows80),1.0)
    q=probe('NEW','2026-08-14');assert q['routeAvailable'] and q['route']=='VNSTOCK_CURRENT_SHORT_HISTORY' and not q['trainingEligible'],q
    class _QuotaExitMarket:
        def __init__(self):raise SystemExit('forced provider quota termination')
    fake_ui.Market=_QuotaExitMarket
    def _fail_yahoo(symbol):raise RuntimeError('forced Yahoo probe failure')
    ds.yahoo_history=_fail_yahoo;ds.cached_history=lambda symbol:(list(rows80),{'provider':'mock-cache'})
    q2=probe('NEW','2026-08-14');assert q2['routeAvailable'] and q2['route']=='CACHE_CURRENT_SHORT_HISTORY' and not q2['trainingEligible'],q2
    assert q2['attempts'][0]['stage']=='VNSTOCK_CURRENT_ROUTE_PROBE' and 'SystemExit' in q2['attempts'][0]['error'],q2
finally:
    ds._normalize_df=old_norm;ds._throttle_vnstock=old_throttle;ds.yahoo_history=old_yahoo;ds.cached_history=old_cached
    if old_vnstock is None:sys.modules.pop('vnstock',None)
    else:sys.modules['vnstock']=old_vnstock
    if old_vnstock_ui is None:sys.modules.pop('vnstock.ui',None)
    else:sys.modules['vnstock.ui']=old_vnstock_ui

# Rumor claim functions must distinguish similar claims and denial/confirmation state.
a=ns['_claim_tokens']('FPT tin đồn mua lại công ty ABC');b=ns['_claim_tokens']('FPT được cho là mua lại ABC');c=ns['_claim_tokens']('VCB tăng lãi suất tiền gửi');assert ns['_claim_sim'](a,b)>ns['_claim_sim'](a,c);assert ns['_truth_label']('Công ty chính thức xác nhận thương vụ')=='CONFIRMED';assert ns['_truth_label']('Doanh nghiệp phủ nhận tin đồn')=='DENIED'

print('V12 METHOD RUNTIME UNIT PASS',{'parts':len(parts),'quantile':getattr(layer,'method',None),'returnShrink':float(layer.returnShrink),'qadj':float(qadj),'maturityPurge':'PASS','incrementalIC':inc,'pboSplits':pbo['splits'],'pbo':pbo['pbo'],'pboCandidates':pbo['candidateCount'],'routeEligibilityContract':'PASS','sectorPITIsolation':'PASS','shortRouteRuntime':'PASS','providerSystemExitFallback':'PASS'})
