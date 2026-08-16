import pathlib
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parent
parts=sorted((ROOT/'v12_train_parts').glob('*.pyinc'))
code='\n'.join(p.read_text(encoding='utf-8') for p in parts)
ns={'__name__':'v12_quantile_monotone_unit','__file__':str(ROOT/'train_forecast_v12.py')}
exec(compile(code,'v12-quantile-monotone-assembled.py','exec'),ns,ns)

rng=np.random.default_rng(1205)
# Nonlinear but order-preserving conditional return map. The quantile calibration layer is
# a remapping of an already ranked direct-return score, so all released scenario quantiles
# and point-map candidates must remain non-decreasing without blind-holdout labels.
score=np.linspace(-2.5,2.5,3600)
y=.006*np.tanh(score)+rng.normal(scale=.012,size=len(score))
layer,iso,qadj=ns['calibrate'](y[:1800],score[:1800],y[1800:2700],score[1800:2700])
probe=np.linspace(float(score.min()),float(score.max()),2000)
_,med,lo,hi,_=ns['apply_calibration'](probe,layer,iso,qadj)
for name,arr in [('q20',lo),('point',med),('q80',hi)]:
    d=np.diff(np.asarray(arr,float));assert np.min(d)>=-1e-10,(name,float(np.min(d)),getattr(layer,'method',None),getattr(layer,'pointMode',None))
assert np.all(lo<=med) and np.all(med<=hi)
assert 'MONOTONE' in str(getattr(layer,'method','')).upper(),getattr(layer,'method',None)

pa=getattr(layer,'pointSelectionAudit',{})
assert getattr(layer,'pointMode',None) in ('Q50','DIRECT_SCORE','BINNED_MONOTONE_MEDIAN'),getattr(layer,'pointMode',None)
assert pa.get('sealedLabelsUsed')==0,pa
assert pa.get('selectedFamily',getattr(layer,'pointMode',None))==getattr(layer,'pointMode',None),pa
assert int(getattr(layer,'conformalN',0))>0,getattr(layer,'conformalN',None)

# Explicitly regression-test the robust binned monotone median map on a zero-inflated,
# monotone conditional-return relation. This is fit on synthetic pre-blind-like data only.
rng3=np.random.default_rng(44)
s3=np.linspace(-3,3,1800)
latent=.009*np.tanh(1.2*s3)
y3=latent+rng3.normal(scale=.008,size=len(s3))
y3[np.abs(y3)<.003]=0.0
bm=ns['_fit_binned_monotone_median'](s3[:1200],y3[:1200],15)
assert bm and bm['target']=='BINNED_MONOTONE_CONDITIONAL_MEDIAN' and bm['fitRows']==1200,bm
bp=ns['_predict_binned_monotone'](bm,s3[1200:])
assert np.min(np.diff(bp))>=-1e-12,float(np.min(np.diff(bp)))
assert np.std(bp)>0 and np.mean(np.abs(bp)>=.001)>0.05,(float(np.std(bp)),float(np.mean(np.abs(bp)>=.001)))

# Gamma is a return-scale calibration parameter, not a complexity parameter. When several
# pre-blind candidates are statistically indistinguishable from the empirical MAE minimizer,
# regularize toward identity (g=1) rather than mechanically toward zero. Sealed 90-100% labels
# are not supplied to this selector.
rng2=np.random.default_rng(912);m2=rng2.normal(scale=.02,size=1200);y2=.5*m2+rng2.normal(scale=.03,size=1200)
g2,n2,a2=ns['_select_return_shrink'](y2,m2)
assert n2==1200 and a2['selectionRule']=='ONE_STANDARD_ERROR_TOWARD_IDENTITY',a2
assert a2.get('sealedLabelsUsed')==0,a2
assert a2['selectedMAE']<=a2['oneSELimit']+1e-15,(g2,a2)
assert a2['oneSEEligibleN']>1 and a2['empiricalBestSE']>0,a2
assert abs(g2-1.0)<=abs(a2['empiricalBestShrink']-1.0)+1e-12,(g2,a2)
assert g2>=a2['empiricalBestShrink']-1e-12,(g2,a2)

print('V12 QUANTILE MONOTONE UNIT PASS',{'method':getattr(layer,'method',None),'pointMode':getattr(layer,'pointMode',None),'returnShrink':float(getattr(layer,'returnShrink',1.0)),'qadj':float(qadj),'oneSEIdentityShrink':float(g2),'empiricalBestShrink':float(a2['empiricalBestShrink']),'binnedMedianKnots':len(bm['x'])})
