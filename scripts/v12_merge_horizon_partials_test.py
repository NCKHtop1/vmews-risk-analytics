from __future__ import annotations
import json,pathlib,tempfile
from v12_merge_horizon_partials import merge_partials
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x),encoding='utf-8')
def ev(h):return list(dict.fromkeys(['eventPriorAR5','eventPriorHit5','eventPriorN5',f'eventPriorAR{h}',f'eventPriorHit{h}',f'eventPriorN{h}',f'eventPriorUncertainty{h}']))
def build(root,corrupt=None):
    for h in range(1,6):
        d=root/f'h{h}';e=ev(h);features=['a','rumorLeadScore20']+e+['stretch20Vol','b'];experts={'NUMERICAL':['a','b'],'EVENT':['newsN20']+e}
        if corrupt=='feature' and h==3:features.append('unexpectedDifferentFeature')
        model={'version':'VMEWS-FORECAST-12.0.0','createdAt':f'2026-08-18T00:00:0{h}Z','target':'direct','featureNames':features,'experts':experts,'universe':{'rows':1000,'dates':100,'start':'2020-01-01','end':'2026-08-18'},'governance':{'priceSourcePolicy':'legacy','stacking':'OOF'},'dataSources':{'flowVersion':'x','eventVersion':'y'},'horizons':{str(h):{'priceStatus':'PASS','directionStatus':'PASS' if h!=4 else 'REVIEW','sealedAudit':{'rankIC':.03}}},'promotion':{'status':'REVIEW','directPriceHorizons':[h]}}
        current={'version':'VMEWS-CURRENT-12.0.0','generatedAt':f'2026-08-18T00:00:0{h}Z','symbols':{'FPT':{'symbol':'FPT','date':'2026-08-18','close':100.,'modelClose':100.,'technical':40.,'market':{'mret1':.1},'riskStatus':'GREEN','riskFlags':0,'evidence':{'n':1},'flow':{'foreignAvailable':1.},'horizons':{str(h):{'expectedReturn':.01*h,'expectedPrice':100+h}}}}}
        dash={'version':'VMEWS-DASHBOARD-12.4.0','generatedAt':f'2026-08-18T00:00:0{h}Z','modelVersion':'VMEWS-FORECAST-12.0.0','asOf':'2026-08-18','promotion':model['promotion'],'symbols':current['symbols'],'charts':{'FPT':[{'date':'2026-08-18','close':100.}]},'lists':{'watch':[{'symbol':'FPT'}] if h==5 else [],'yellow':[],'red':[]},'dataAuditSummary':{'currentSymbolsPassed':1}}
        back={'version':'VMEWS-BACKTEST-12.4.0','generatedAt':f'2026-08-18T00:00:0{h}Z','design':'same-design','horizons':{str(h):{'priceStatus':'PASS'}},'cases':{str(h):[{'symbol':'FPT','predictedReturn':.01*h}]}}
        audit={'version':'AUDIT','generatedAt':f'2026-08-18T00:00:0{h}Z','routes':{'FROZEN':2 if corrupt=='data' and h==3 else 1}}
        records=[]
        for n,key in enumerate(['FPT::evt1','FPT::evt2']):records.append({'eventKey':key,'ticker':'FPT','availableDate':f'2026-08-{10+n:02d}','preReturn2':.01,'priceAfter':{str(h):100+h+n},'benchmarkReturn':{str(h):.001*h},'benchmarkAvailable':{str(h):True},'benchmarkTargetDate':{str(h):f'2026-08-{10+n+h:02d}'},'abnormalReturn':{str(h):.002*h},'cumulativeAbnormalReturn':{str(h):.003*h},'matureDate':{str(h):f'2026-08-{10+n+h:02d}'}})
        event={'version':'EVENT','generatedAt':f'2026-08-18T00:00:0{h}Z','pointInTimePolicy':'PIT','summary':{'records':2,'symbols':1,'maturedH5Records':2 if h==5 else 0,'benchmarkH5Available':2 if h==5 else 0,'benchmarkH5Coverage':1. if h==5 else 0.},'records':records}
        for name,obj in [('forecast-model-v12.json',model),('forecast-current-v12.json',current),('forecast-dashboard-v12.json',dash),('forecast-backtest-v12.json',back),('data-audit-v12.json',audit),('event-intelligence-v12.json',event)]:dump(d/name,obj)
def main():
    with tempfile.TemporaryDirectory() as td:
        r=pathlib.Path(td);build(r/'partials');z=merge_partials(r/'partials',r/'out');assert z['status']=='PASS' and z['promotion']=='PASS';m=json.load(open(r/'out'/'forecast-model-v12.json'));e=json.load(open(r/'out'/'event-intelligence-v12.json'));assert sorted(m['horizons'])==['1','2','3','4','5'];assert m['promotion']['directPriceHorizons']==[1,2,3,4,5]
        for h in range(1,6):
            for x in (f'eventPriorAR{h}',f'eventPriorHit{h}',f'eventPriorN{h}',f'eventPriorUncertainty{h}'):assert x in m['featureNames'] and x in m['experts']['EVENT']
        for f in ('priceAfter','benchmarkReturn','benchmarkAvailable','benchmarkTargetDate','abnormalReturn','cumulativeAbnormalReturn','matureDate'):assert sorted(e['records'][0][f])==['1','2','3','4','5']
    for kind,token in [('data','data-audit'),('feature','model-feature-common')]:
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td);build(r/'partials',kind)
            try:merge_partials(r/'partials',r/'out')
            except RuntimeError as x:assert token in str(x),x
            else:raise AssertionError(f'{kind} corruption was not rejected')
    print('V12 HORIZON PARTIAL MERGE TEST PASS')
if __name__=='__main__':main()
