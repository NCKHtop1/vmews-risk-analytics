import math,pathlib
from datetime import date,timedelta
ROOT=pathlib.Path(__file__).resolve().parent
parts=sorted((ROOT/'v12_train_parts').glob('*.pyinc'))
code='\n'.join(p.read_text(encoding='utf-8') for p in parts)
ns={'__name__':'v12_benchmark_unit','__file__':str(ROOT/'train_forecast_v12.py')};exec(compile(code,'v12-benchmark-unit-assembled.py','exec'),ns,ns)
start=date(2026,1,1);market_dates=[(start+timedelta(days=i)).isoformat() for i in range(40)]
index=[{'date':d,'close':1000+3*i,'modelClose':1000+3*i,'volume':0} for i,d in enumerate(market_dates)]
# Simulate a stock-specific non-trading date so T+5 maturity is not the fifth VNINDEX session.
stock_dates=[d for i,d in enumerate(market_dates) if i!=8]
rows=[{'date':d,'close':100+1.5*i,'modelClose':100+1.5*i,'volume':1000+i} for i,d in enumerate(stock_dates)]
pub=stock_dates[5]+'T08:00:00+07:00'
sentiment={'symbols':{'FPT':{'items':[{'id':'evt1','publishedAt':pub,'title':'FPT công bố kết quả kinh doanh kiểm thử','label':'POS','sourceQuality':.9,'materiality':.8,'confidence':.9,'event':'EARNINGS','publisher':'TEST','sourceClass':'MAINSTREAM','stream':'MAIN'}]}}}
articles,outcomes=ns['prepare_articles'](sentiment,{'FPT':rows},{'FPT':'Technology'},index);assert outcomes,outcomes;o=outcomes[0];rec=articles['FPT'][0];i=rec['availableIndex'];target=rows[i+5]['date'];assert target!=market_dates[market_dates.index(rec['availableDate'])+5],(target,rec['availableDate'])
assert o['matureDate5']==target and o['benchmarkTargetDate5']==target,o
origin_i=market_dates.index(rec['availableDate']);target_i=market_dates.index(target);expected=math.log(index[target_i]['modelClose']/index[origin_i]['modelClose']);assert abs(o['benchmarkR5']-expected)<1e-12,(o['benchmarkR5'],expected);assert abs(o['ar5']-(o['r5']-expected))<1e-12,o
assert o.get('preBenchmarkAvailable5') is True and isinstance(o.get('preAR5'),float),o
# Exercise the assembled event feature store itself; this catches missing runtime symbols that syntax-only checks cannot see.
store=ns['EvidenceFeatureStore'](articles,outcomes,{'FPT':'Technology'});feat=store.features('FPT',rec['availableDate']);assert isinstance(feat,dict) and all(k in feat for k in ('hierSent20','eventPriorAR1','eventPriorAR5','eventPriorUncertainty5')),feat
# Missing benchmark is abstention for both post- and pre-event abnormal return.
articles2,outcomes2=ns['prepare_articles'](sentiment,{'FPT':rows},{'FPT':'Technology'},[]);assert outcomes2;z=outcomes2[0];assert z.get('benchmarkAvailable5') is False and z.get('benchmarkR5') is None and z.get('ar5') is None,z;assert z.get('preBenchmarkAvailable5') is False and z.get('preBenchmarkR5') is None and z.get('preAR5') is None,z
# Provider-local IDs may collide across tickers. Internal joins must remain ticker+newsId safe.
vcb_rows=[{'date':d,'close':70+0.35*i,'modelClose':70+0.35*i,'volume':1800+i} for i,d in enumerate(market_dates)]
collision_sent={'symbols':{
 'FPT':{'items':[{'id':'shared-id','publishedAt':pub,'title':'FPT xác nhận kết quả kinh doanh','label':'POS','sourceQuality':.8,'materiality':.7,'confidence':.8,'event':'EARNINGS','publisher':'FPT-SOURCE','sourceClass':'MAINSTREAM','stream':'MAIN'}]},
 'VCB':{'items':[{'id':'shared-id','publishedAt':pub,'title':'VCB xác nhận kết quả kinh doanh','label':'NEG','sourceQuality':.95,'materiality':.9,'confidence':.9,'event':'EARNINGS','publisher':'VCB-SOURCE','sourceClass':'OFFICIAL','stream':'OFFICIAL'}]}
}}
ca,co=ns['prepare_articles'](collision_sent,{'FPT':rows,'VCB':vcb_rows},{'FPT':'Technology','VCB':'Banking'},index);assert len(co)==2,(ca,co);by_symbol={x['symbol']:x for x in co};assert set(by_symbol)=={'FPT','VCB'},by_symbol
assert ca['FPT'][0]['publisher']=='FPT-SOURCE' and ca['FPT'][0]['stream']=='MAIN',ca['FPT'][0]
assert ca['VCB'][0]['publisher']=='VCB-SOURCE' and ca['VCB'][0]['stream']=='OFFICIAL',ca['VCB'][0]
f_i=ca['FPT'][0]['availableIndex'];v_i=ca['VCB'][0]['availableIndex'];assert by_symbol['FPT']['matureDate5']==rows[f_i+5]['date'];assert by_symbol['VCB']['matureDate5']==vcb_rows[v_i+5]['date']
artifact=ns['build_event_intelligence_artifact'](ca,co,{'FPT':rows,'VCB':vcb_rows});keys=[r['eventKey'] for r in artifact['records']];assert sorted(keys)==['FPT::shared-id','VCB::shared-id'],keys;assert artifact['summary']['duplicateEventKeys']==0,artifact['summary']
# Exercise sealed-holdout audit with NumPy arrays. This specifically guards against ndarray truth-value bugs that only appear after the expensive full panel fit.
np=ns['np'];n=2400;idx=np.arange(n,dtype=int);dlist=np.asarray([f'2026-04-{1+(j//80):02d}' for j in range(n)],dtype=object);yy=np.linspace(-.03,.03,n);score=yy+np.sin(np.arange(n))*.0001;pp=np.clip(.5+score*5,.01,.99);med=yy*.8;lo=med-.015;hi=med+.015
ns['OOF_CAPTURE'][1]={'kindSelectionLockDate':'2026-02-01','predictionAvailabilityEndExclusive':'2026-02-15'}
blind_z={'auditIndices':idx,'auditScore':score,'auditP':pp,'auditMed':med,'auditLo':lo,'auditHi':hi,'sealedAudit':{'rankIC':.2,'spread':.01,'scenarioMAEImprove':.1,'coverage20_80':.6},'embargoAudit':{'sealedAuditStart':'2026-04-01','maxCalBLabelMaturity':'2026-03-01'},'walkForwardReplay':{'status':'PASS','chronologyVerified':True,'futureRowsUsedForTraining':0,'futureMetaRowsUsedForTraining':0,'futureCalibrationRowsUsedForTraining':0,'metaTrainMaxMaturity':'2026-03-15'}}
blind=ns['_fixed_blind_holdout_audit'](yy,dlist,blind_z,1);assert isinstance(blind,dict) and blind.get('horizon')==1 and len(blind.get('blocks') or [])==4,blind
print('V12 EXACT VNINDEX + EVIDENCE STORE + SEALED HOLDOUT UNIT PASS',{'origin':rec['availableDate'],'stockT5':target,'ordinalMarketT5':market_dates[origin_i+5],'benchmarkR5':o['benchmarkR5'],'ar5':o['ar5'],'collisionKeys':keys,'eventFeatureCount':len(feat),'blindStatus':blind.get('status')})
