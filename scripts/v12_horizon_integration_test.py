import pathlib,sys
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
ROOT=pathlib.Path(__file__).resolve().parent
parts=sorted((ROOT/'v12_train_parts').glob('*.pyinc'))
code='\n'.join(p.read_text(encoding='utf-8') for p in parts)
ns={'__name__':'v12_horizon_integration','__file__':str(ROOT/'train_forecast_v12.py')}
exec(compile(code,'v12-horizon-integration-assembled.py','exec'),ns,ns)
rng=np.random.default_rng(12012)
FEATURES=ns['FEATURES'];EXPERTS=ns['EXPERTS'];idx=ns['expert_indexes']()
# 240 chronological dates x 30 stocks: enough for OOF, calibration, sealed audit, PBO and replay code paths.
n_dates=240;n_stock=30;n=n_dates*n_stock
dates=np.asarray([f'{2020+i//240:04d}-{1+(i//20)%12:02d}-{1+i%20:02d}' for i in range(n_dates)])
D=np.repeat(dates,n_stock)
X=rng.normal(scale=.5,size=(n,len(FEATURES)))
# Make sparse evidence families realistic rather than random-always-on.
for name in ['EVENT','FLOW','FUNDAMENTAL_EVENT','RUMOR']:
    fi=idx[name]
    mask=rng.random(n)<({'EVENT':.30,'FLOW':.42,'FUNDAMENTAL_EVENT':.12,'RUMOR':.06}[name])
    X[:,fi]=0.0
    X[np.ix_(mask,fi)]=rng.normal(scale=.4,size=(mask.sum(),len(fi)))
# Return target has a modest genuine numerical/regime signal; optional experts are mostly noise and should not be required to promote.
num_i=idx['NUMERICAL'][:min(4,len(idx['NUMERICAL']))];reg_i=idx['REGIME'][:min(3,len(idx['REGIME']))]
signal=.005*np.nanmean(X[:,num_i],axis=1)+.003*np.nanmean(X[:,reg_i],axis=1)
y=signal+rng.normal(scale=.018,size=n)
z=ns['fit_horizon'](X,y,D,dates,3,idx)
required=['active','choice','selection','sealedAudit','gates','ablation','distributionAudit','pboAudit','walkForwardReplay','embargoAudit','deployment']
missing=[k for k in required if k not in z]
assert not missing,missing
assert z['distributionAudit'].get('method') and 'QUANTILE' in z['distributionAudit']['method'].upper(),z['distributionAudit']
assert z['pboAudit'].get('splits',0)>=30,z['pboAudit']
assert z['embargoAudit'].get('labelPurgeSessions')==3,z['embargoAudit']
assert z['walkForwardReplay'].get('futureRowsUsedForTraining')==0,z['walkForwardReplay']
assert 'NUMERICAL' in z['active'] and 'REGIME' in z['active'],z['active']
for name in ['EVENT','FLOW','FUNDAMENTAL_EVENT','RUMOR']:
    assert name in z['choice'] and name in z['selection'],(name,z.keys())
print('V12 HORIZON INTEGRATION PASS',{
    'features':len(FEATURES),'rows':n,'active':z['active'],'sealed':z['sealedAudit'],
    'gates':z['gates'],'distribution':z['distributionAudit'],'pbo':{k:z['pboAudit'].get(k) for k in ['status','pbo','splits']},
    'walkForward':{k:z['walkForwardReplay'].get(k) for k in ['status','futureRowsUsedForTraining','purgeSessions']},'embargo':z['embargoAudit']
})
