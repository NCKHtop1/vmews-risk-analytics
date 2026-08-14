from datetime import date,timedelta
import math
import v12_rumor_runtime
v12_rumor_runtime.apply()
from v12_evidence import prepare_articles,EvidenceFeatureStore,resolve_rumor_state,_tokens

# 1) State transitions must only use information available by as-of date.
rumor={'id':'r1','title':'Doanh nghiệp ABC được đồn đoán sáp nhập với XYZ','titleTokens':sorted(_tokens('Doanh nghiệp ABC được đồn đoán sáp nhập với XYZ')),'publisher':'RumorWire','sourceClass':'RUMOR_UNVERIFIED','event':'OPERATIONS_MA','availableDate':'2026-01-05'}
main1={'id':'m1','title':'ABC có thể sáp nhập với XYZ theo nguồn thị trường','titleTokens':sorted(_tokens('ABC có thể sáp nhập với XYZ theo nguồn thị trường')),'publisher':'PressA','sourceClass':'MAINSTREAM','event':'OPERATIONS_MA','availableDate':'2026-01-06'}
main2={'id':'m2','title':'Thị trường tiếp tục nói về khả năng ABC sáp nhập XYZ','titleTokens':sorted(_tokens('Thị trường tiếp tục nói về khả năng ABC sáp nhập XYZ')),'publisher':'PressB','sourceClass':'MAINSTREAM','event':'OPERATIONS_MA','availableDate':'2026-01-07'}
official={'id':'o1','title':'ABC chính thức công bố kế hoạch sáp nhập với XYZ','titleTokens':sorted(_tokens('ABC chính thức công bố kế hoạch sáp nhập với XYZ')),'publisher':'HOSE','sourceClass':'OFFICIAL','event':'OPERATIONS_MA','availableDate':'2026-01-08'}
denial={'id':'d1','title':'ABC chính thức phủ nhận tin đồn sáp nhập với XYZ','titleTokens':sorted(_tokens('ABC chính thức phủ nhận tin đồn sáp nhập với XYZ')),'publisher':'HOSE','sourceClass':'CLARIFICATION','event':'OPERATIONS_MA','availableDate':'2026-01-08'}
assert resolve_rumor_state(rumor,[rumor,main1,main2,official],'2026-01-05')['state']=='UNVERIFIED'
assert resolve_rumor_state(rumor,[rumor,main1,main2,official],'2026-01-07')['state']=='CORROBORATED'
assert resolve_rumor_state(rumor,[rumor,main1,main2,official],'2026-01-08')['state']=='CONFIRMED'
assert resolve_rumor_state(rumor,[rumor,main1,main2,denial],'2026-01-08')['state']=='DENIED'

# 2) Synthetic price/volume history: pre-rumor price and volume leads must be measured, never future-filled.
start=date(2025,10,1);rows=[]
for i in range(110):
    d=(start+timedelta(days=i)).isoformat();close=100.0*(1.001**i);vol=100.0
    if i in (98,99):close*=1.04;vol=350.0
    rows.append({'date':d,'open':close,'high':close,'low':close,'close':close,'modelClose':close,'volume':vol})
pub=rows[100]['date']+'T10:00:00+07:00'
sent={'symbols':{'ABC':{'items':[{'id':'r2','title':'ABC được đồn đoán có thương vụ M&A lớn','publisher':'RumorA','sourceClass':'RUMOR_UNVERIFIED','event':'OPERATIONS_MA','label':'POS','confidence':.8,'materiality':.9,'sourceQuality':.5,'publishedAt':pub,'link':'#'}]}}}
articles,outcomes=prepare_articles(sent,{'ABC':rows},{'ABC':'TEST'},None);r=articles['ABC'][0]
assert r['availableDate']==rows[100]['date']
assert r.get('preR2',0)>0.03,r.get('preR2')
assert r.get('preVolumeZ2',0)>1.0,r.get('preVolumeZ2')
assert 'preR2' in outcomes[0] and 'preVolumeZ2' in outcomes[0]
store=EvidenceFeatureStore(articles,outcomes,{'ABC':'TEST'});f=store.features('ABC',rows[100]['date'])
for k in ['rumorQuality20','rumorDuplication20','rumorPreVolumeZ2','rumorPreVolumeZ5','rumorPriceLeadShare','rumorVolumeLeadShare']:
    assert k in f,k
assert f['rumorPriceLeadShare']==1.0,f
assert f['rumorVolumeLeadShare']==1.0,f
ci=store.current_intelligence('ABC',rows[100]['date']);rr=ci['rumors'][0]
assert rr['truthConfidence'] is None
assert rr['truthMethod']=='NO_GOLD_TRUTH_LABEL'
assert rr['anonymousSourceAvailable'] is False and rr['socialSignalAvailable'] is False
print('V12 RUMOR INTELLIGENCE TEST PASS',{'stateBefore':'UNVERIFIED','stateCorroborated':'CORROBORATED','stateConfirmed':'CONFIRMED','stateDenied':'DENIED','preR2':r['preR2'],'preVolumeZ2':r['preVolumeZ2'],'features':{k:f[k] for k in ['rumorPriceLeadShare','rumorVolumeLeadShare','rumorDuplication20']}})
