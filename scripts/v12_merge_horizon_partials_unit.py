import copy,json,pathlib,tempfile
from v12_merge_horizon_partials import HORIZONS,REQUIRED,merge_partials

BASE_FEATURES=['ret1','ret5','eventPriorAR5','eventPriorHit5','eventPriorN5']
BASE_EVENT=['newsN5','eventPriorAR5','eventPriorHit5','eventPriorN5']
MAPS=('priceAfter','benchmarkReturn','benchmarkAvailable','benchmarkTargetDate','abnormalReturn','cumulativeAbnormalReturn','matureDate')

def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,separators=(',',':')),encoding='utf-8')

def partial(h):
    hf=[] if h==5 else [f'eventPriorAR{h}',f'eventPriorHit{h}',f'eventPriorN{h}']
    hf=hf+[f'eventPriorUncertainty{h}']
    model={
      'version':'V','target':'T','featureNames':BASE_FEATURES+hf,
      'experts':{'NUMERICAL':['ret1'],'REGIME':['ret5'],'EVENT':BASE_EVENT+hf},
      'universe':{'rows':1000},'governance':{'g':'x'},'dataSources':{'source':'frozen'},
      'horizons':{str(h):{'priceStatus':'PASS','directionStatus':'PASS'}},
    }
    current={'version':'C','symbols':{'AAA':{'symbol':'AAA','date':'2026-01-01','close':10,'horizons':{str(h):{'expectedReturn':h/100}}}}}
    dashboard={'version':'D','modelVersion':'V','asOf':'2026-01-01','charts':{},'dataAuditSummary':{},'lists':{'watch':[]},'symbols':copy.deepcopy(current['symbols'])}
    backtest={'version':'B','design':'fixed','horizons':{str(h):{'priceStatus':'PASS'}},'cases':{str(h):[]}}
    data={'status':'PASS','routes':{'frozen':1}}
    rec={'eventKey':'E1','title':'same','ticker':'AAA'}
    for field in MAPS:rec[field]={str(h): True if field=='benchmarkAvailable' else (f'2026-01-0{h}' if field in {'benchmarkTargetDate','matureDate'} else float(h))}
    event={
      'version':'E','pointInTimePolicy':'PIT','summary':{
        'records':1,'symbols':1,'maturedH5Records':1 if h==5 else 0,
        'benchmarkH5Available':1 if h==5 else 0,'benchmarkH5Coverage':1.0 if h==5 else 0.0,
      },'records':[rec]
    }
    return {
      'forecast-model-v12.json':model,'forecast-current-v12.json':current,
      'forecast-dashboard-v12.json':dashboard,'forecast-backtest-v12.json':backtest,
      'data-audit-v12.json':data,'event-intelligence-v12.json':event,
    }

def materialize(root,parts):
    for h,p in parts.items():
        for name,obj in p.items():dump(root/f'h{h}'/name,obj)

with tempfile.TemporaryDirectory() as td:
    root=pathlib.Path(td)/'partials';out=pathlib.Path(td)/'out'
    parts={h:partial(h) for h in HORIZONS};materialize(root,parts)
    a=merge_partials(root,out);assert a['status']=='PASS'
    m=json.loads((out/'forecast-model-v12.json').read_text())
    for h in HORIZONS:
        assert f'eventPriorUncertainty{h}' in m['featureNames'],m['featureNames']
        assert str(h) in m['horizons']
    e=json.loads((out/'event-intelligence-v12.json').read_text());r=e['records'][0]
    for field in MAPS:assert set(r[field])==set(map(str,HORIZONS)),(field,r[field])
    assert e['summary']['maturedH5Records']==1

with tempfile.TemporaryDirectory() as td:
    root=pathlib.Path(td)/'partials';out=pathlib.Path(td)/'out'
    parts={h:partial(h) for h in HORIZONS};parts[3]['forecast-model-v12.json']['universe']['rows']=999
    materialize(root,parts)
    try:merge_partials(root,out)
    except RuntimeError as exc:assert 'model-static-common' in str(exc)
    else:raise AssertionError('unrelated model-common corruption was not rejected')

with tempfile.TemporaryDirectory() as td:
    root=pathlib.Path(td)/'partials';out=pathlib.Path(td)/'out'
    parts={h:partial(h) for h in HORIZONS};parts[4]['event-intelligence-v12.json']['records'][0]['title']='corrupt'
    materialize(root,parts)
    try:merge_partials(root,out)
    except RuntimeError as exc:assert 'event-record-common' in str(exc)
    else:raise AssertionError('event common-field corruption was not rejected')

print('V12 HORIZON MERGER UNIT PASS')
