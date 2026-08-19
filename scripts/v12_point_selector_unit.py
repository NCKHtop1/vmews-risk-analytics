import pathlib,sys
from datetime import date,timedelta
import numpy as np

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
ROOT=pathlib.Path(__file__).resolve().parent
parts=sorted((ROOT/'v12_train_parts').glob('*.pyinc'))
code='\n'.join(p.read_text(encoding='utf-8') for p in parts)
ns={'__name__':'v12_point_selector_unit','__file__':str(ROOT/'train_forecast_v12.py')}
exec(compile(code,'v12-point-selector-assembled.py','exec'),ns,ns)

# The selector must expose the gate-aligned V2 contract and exact-maturity audit language.
source=(ROOT/'v12_train_parts'/'01ek_chronological_point_controller.pyinc').read_text(encoding='utf-8')
for token in (
    'CHRONOLOGICAL_ORIGIN_DATE_POINT_SELECTION_V2',
    'EXACT_MATURITY_PURGED_EXPANDING_ROLLING_ORIGIN',
    'dailyMAEEdge','minimumDispersionRatio','minimumP90MagnitudeRatio',
    'sealedLabelsUsed','XSEC_RANK_ONLY','marketDriftIntercept',
):
    assert token in source,token

# Same-origin rank-only family: zero mean per date, row-order invariant, and learns a positive
# magnitude scale when the synthetic target truly contains stable cross-sectional rank alpha.
rng=np.random.default_rng(9817)
days=np.asarray([(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(30)],dtype=object)
D=np.repeat(days,40)
score=rng.normal(size=len(D))
rank=ns['_xsec_rank_signal'](score,D)
common=np.repeat(rng.normal(scale=.006,size=len(days)),40)
y=.012*rank+common+rng.normal(scale=.003,size=len(D))
fit=ns['_chrono_daily_rank_scale'](y,score,D)
assert fit is not None and 0<float(fit['scale'])<=.20,fit
pred=float(fit['scale'])*rank
for d in days:
    q=D==d
    assert abs(float(np.mean(pred[q])))<1e-12,(d,np.mean(pred[q]))
perm=rng.permutation(len(D));rp=ns['_xsec_rank_signal'](score[perm],D[perm]);back=np.empty_like(rp);back[perm]=rp
assert np.allclose(rank,back)
assert float(ns['rank_stats'](y,pred,D)['ic'])>.80

# The realistic 18-date 80-85 block plus 9 safe early-85-90 dates yields 21 chronological OOS
# origin dates across expanding folds, enough to judge the same >=20-day evidence family as the
# final gate without touching 90-100%.
fit_days=np.asarray([(date(2025,3,7)+timedelta(days=7*i)).isoformat() for i in range(18)],dtype=object)
ext_days=np.asarray([(date(2025,7,18)+timedelta(days=7*i)).isoformat() for i in range(9)],dtype=object)
folds=ns['_chrono_rolling_folds'](fit_days,ext_days)
assert len(folds)==4,folds
all_val=np.concatenate([f['validationDays'] for f in folds])
assert len(all_val)==21 and len(set(all_val.astype(str)))==21,all_val
assert list(all_val.astype(str))==sorted(all_val.astype(str))

# Exact symbol-specific maturity purge regression.  Deliberately make some rows from the origin
# immediately before the first validation fold mature AFTER that validation starts.  A date-only
# or ordinal h-gap selector would admit them; the V2 selector must exclude them row-by-row.
rows_per_day=80
fd=np.repeat(fit_days,rows_per_day);fy=np.arange(len(fd),dtype=float);fs=np.linspace(-1,1,len(fd))
fm=np.empty(len(fd),dtype=object)
for i,d in enumerate(fit_days):
    q=np.where(fd==d)[0]
    next_d=(date.fromisoformat(str(d))+timedelta(days=2)).isoformat()
    fm[q]=next_d
first_val=str(folds[0]['validationDays'][0])
prev_day=str(fit_days[np.where(fit_days==folds[0]['validationDays'][0])[0][0]-1])
late_ids=np.where(fd==prev_day)[0][:20]
fm[late_ids]=(date.fromisoformat(first_val)+timedelta(days=1)).isoformat()
cd=np.repeat(ext_days,rows_per_day);cy=np.zeros(len(cd));cs=np.linspace(-.5,.5,len(cd))
split={'fitDays':fit_days,'validationDays':ext_days,'conformalDays':np.asarray(['2026-01-01'],dtype=object)}
seen=[]
old_fit=ns['_chrono_fit_bundle'];old_pred=ns['_chrono_bundle_predictions'];old_metric=ns['_chrono_oos_metric']
try:
    def fake_fit(yy,ss,dd):
        seen.append(set(int(x) for x in np.asarray(yy,float)))
        return {'dummy':True}
    def fake_pred(bundle,ss,dd):
        return {'Q50':np.zeros(len(ss),float),'XSEC_RANK_ONLY':np.asarray(ss,float)*.001}
    def fake_metric(yy,pp,dd,h):
        return {'dailyMAEEdge':{'bootstrap90':[-.001,.001],'mean':0.0},'rankIC':0.0,'gateAlignedPass':False}
    ns['_chrono_fit_bundle']=fake_fit;ns['_chrono_bundle_predictions']=fake_pred;ns['_chrono_oos_metric']=fake_metric
    chosen,metrics,audit,eligible=ns['_chrono_select_family'](fy,fs,fd,fm,cy,cs,cd,split)
finally:
    ns['_chrono_fit_bundle']=old_fit;ns['_chrono_bundle_predictions']=old_pred;ns['_chrono_oos_metric']=old_metric
assert seen and not (set(int(x) for x in late_ids)&seen[0]),(late_ids,seen[0])
assert all(x.get('exactMaturityPurged') is True and x.get('futureLabelsUsed')==0 for x in audit),audit
assert all((x.get('maxTrainLabelMaturity') or '0000')<x['validationDateRange'][0] for x in audit),audit

# Sealed deployment-calibration guard: return the frozen pre-blind tuple before even converting
# a 90-100% label object.  Poison.__array__ makes any accidental label read fail immediately.
class Poison:
    def __array__(self,*args,**kwargs):
        raise AssertionError('sealed label array was read by calibration')
strict=ns['_chrono_strict_calibrate']
sentinel=(object(),object(),.123456)
ns['_V12_PRIMARY_PREBLIND_CALIBRATION']=sentinel
ns['V12_CURRENT_SEALED_START']='2026-03-01'
res=strict(Poison(),np.asarray([0.0]),Poison(),np.asarray([0.0]),np.asarray(['2026-01-01'],dtype=object),np.asarray(['2026-03-02'],dtype=object))
assert res[0] is sentinel[0] and res[1] is sentinel[1] and res[2]==sentinel[2]

# Whole-date split regression with exact maturity: unsafe validation dates are removed as complete
# dates rather than fragmenting only the late-maturing symbols.
cal=np.asarray(['2026-01-01','2026-01-02','2026-01-03','2026-01-04','2026-01-05','2026-01-06','2026-01-07','2026-01-08']*3,dtype=object)
con=np.asarray(['2026-01-09','2026-01-10','2026-01-11','2026-01-12']*3,dtype=object)
mat=np.asarray(['2026-01-10']*3+['2026-01-12']*3+['2026-01-11']*3+['2026-01-12']*3,dtype=object)
z=ns['_chrono_date_split'](cal,con,mat)
assert z is not None
for d in set(con[z['validationIndex']].astype(str)):
    assert int(np.sum(con[z['validationIndex']].astype(str)==d))==int(np.sum(con.astype(str)==d))

print('V12 POINT SELECTOR UNIT PASS',{'rollingFolds':len(folds),'rollingOOSDates':len(all_val),'rankOnlyScale':fit['scale'],'sealedCalibrationRead':0,'exactMaturityPurge':'PASS'})
