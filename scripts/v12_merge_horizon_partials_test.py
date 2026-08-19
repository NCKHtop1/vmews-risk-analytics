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
        align={'method':'VNINDEX_ORIGIN_TO_EXACT_STOCK_MATURITY_DATE','joinKey':'TICKER_NEWS_ID','correctedOutcomes':1000-10*h,'missingBenchmarkOutcomes':10*h,'stockMaturityDifferentFromOrdinalIndexH':20*h,'missingPolicy':'ABSTAIN_NOT_RAW_RETURN'}
        if corrupt=='align_contract' and h==3:align['missingPolicy']='BAD_POLICY'
        audit={'version':'AUDIT','generatedAt':f'2026-08-18T00:00:0{h}Z','routes':{'FROZEN':2 if corrupt=='data' and h==3 else 1},'entityFilter':{'input':100,'rejected':2,'benchmarkAlignment':align}}
        records=[]
        for n,key in enumerate(['FPT::evt1','FPT::evt2']):
            # The partial daily AR is deliberately wrong. In a real isolated Hh shard the
            # previous-horizon ar(H-1) may still carry pre-exact-wrapper semantics. The merger
            # must ignore this derived field and rebuild daily AR from the five merged exact CARs.
            car_value=None if n==1 and h==3 else .003*h
            records.append({'eventKey':key,'ticker':'FPT','availableDate':f'2026-08-{10+n:02d}','preReturn2':.01,'priceAfter':{str(h):100+h+n},'benchmarkReturn':{str(h):.001*h},'benchmarkAvailable':{str(h):True},'benchmarkTargetDate':{str(h):f'2026-08-{10+n+h:02d}'},'abnormalReturn':{str(h):1000.+h},'cumulativeAbnormalReturn':{str(h):car_value},'matureDate':{str(h):f'2026-08-{10+n+h:02d}'}})
        event={'version':'EVENT','generatedAt':f'2026-08-18T00:00:0{h}Z','pointInTimePolicy':'PIT','summary':{'records':2,'symbols':1,'maturedH5Records':2 if h==5 else 0,'benchmarkH5Available':2 if h==5 else 0,'benchmarkH5Coverage':1. if h==5 else 0.},'records':records}
        for name,obj in [('forecast-model-v12.json',model),('forecast-current-v12.json',current),('forecast-dashboard-v12.json',dash),('forecast-backtest-v12.json',back),('data-audit-v12.json',audit),('event-intelligence-v12.json',event)]:dump(d/name,obj)
def main():
    with tempfile.TemporaryDirectory() as td:
        r=pathlib.Path(td);build(r/'partials');z=merge_partials(r/'partials',r/'out');assert z['status']=='PASS' and z['promotion']=='PASS';m=json.load(open(r/'out'/'forecast-model-v12.json'));e=json.load(open(r/'out'/'event-intelligence-v12.json'));a=json.load(open(r/'out'/'data-audit-v12.json'));assert sorted(m['horizons'])==['1','2','3','4','5'];assert m['promotion']['directPriceHorizons']==[1,2,3,4,5]
        for h in range(1,6):
            for x in (f'eventPriorAR{h}',f'eventPriorHit{h}',f'eventPriorN{h}',f'eventPriorUncertainty{h}'):assert x in m['featureNames'] and x in m['experts']['EVENT']
        for f in ('priceAfter','benchmarkReturn','benchmarkAvailable','benchmarkTargetDate','abnormalReturn','cumulativeAbnormalReturn','matureDate'):assert sorted(e['records'][0][f])==['1','2','3','4','5']
        # Complete CAR chain: daily AR must be reconstructed exactly from merged adjacent CAR,
        # never inherited from the deliberately corrupted per-shard abnormalReturn values.
        car=e['records'][0]['cumulativeAbnormalReturn'];dar=e['records'][0]['abnormalReturn']
        assert abs(dar['1']-car['1'])<1e-15
        for h in range(2,6):assert abs(dar[str(h)]-(car[str(h)]-car[str(h-1)]))<1e-15,(h,dar,car)
        assert all(abs(float(v))<1 for v in dar.values()),dar
        # Missing adjacent CAR means abstain at both the missing horizon and the immediately next
        # horizon. We never bridge a missing exact benchmark/maturity observation.
        car_gap=e['records'][1]['cumulativeAbnormalReturn'];dar_gap=e['records'][1]['abnormalReturn']
        assert car_gap['3'] is None and dar_gap['3'] is None and dar_gap['4'] is None,(car_gap,dar_gap)
        assert dar_gap['5'] is not None and abs(dar_gap['5']-(car_gap['5']-car_gap['4']))<1e-15
        ba=a['entityFilter']['benchmarkAlignment'];assert ba['scope']=='HORIZON_SPECIFIC_EXACT_STOCK_MATURITY' and sorted(ba['byHorizon'])==['1','2','3','4','5'];assert ba['byHorizon']['1']['correctedOutcomes']!=ba['byHorizon']['5']['correctedOutcomes']
    for kind,token in [('data','data-audit-common'),('feature','model-feature-common'),('align_contract','benchmark-alignment-contract')]:
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td);build(r/'partials',kind)
            try:merge_partials(r/'partials',r/'out')
            except RuntimeError as x:assert token in str(x),x
            else:raise AssertionError(f'{kind} corruption was not rejected')
    print('V12 HORIZON PARTIAL MERGE TEST PASS')
if __name__=='__main__':main()