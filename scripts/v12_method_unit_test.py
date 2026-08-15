import math,pathlib,sys
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

# Rumor claim functions must distinguish similar claims and denial/confirmation state.
a=ns['_claim_tokens']('FPT tin đồn mua lại công ty ABC');b=ns['_claim_tokens']('FPT được cho là mua lại ABC');c=ns['_claim_tokens']('VCB tăng lãi suất tiền gửi');assert ns['_claim_sim'](a,b)>ns['_claim_sim'](a,c);assert ns['_truth_label']('Công ty chính thức xác nhận thương vụ')=='CONFIRMED';assert ns['_truth_label']('Doanh nghiệp phủ nhận tin đồn')=='DENIED'

print('V12 METHOD RUNTIME UNIT PASS',{'parts':len(parts),'quantile':getattr(layer,'method',None),'returnShrink':float(layer.returnShrink),'qadj':float(qadj),'maturityPurge':'PASS','incrementalIC':inc,'pboSplits':pbo['splits'],'pbo':pbo['pbo'],'pboCandidates':pbo['candidateCount'],'routeEligibilityContract':'PASS'})
