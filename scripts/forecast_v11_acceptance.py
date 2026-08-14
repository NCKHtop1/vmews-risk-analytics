import json,math,re,sys
from pathlib import Path
import numpy as np
ROOT=Path('.')
checks=[]
def ck(name,cond,detail=''):
    ok=bool(cond);checks.append((name,ok,str(detail)));print(('PASS ' if ok else 'FAIL ')+name+(f' :: {detail}' if detail else ''));return ok
def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def fin(x):
    try:return math.isfinite(float(x))
    except:return False
model=load('data/forecast-model-v11.json');cur=load('data/forecast-current-v11.json');dash=load('data/forecast-dashboard-v11.json');nh=load('data/news-history-v11.json');sent=load('data/sentiment-v11.json');ev=load('data/news-event-study-v11.json');flow=load('data/flow-v11.json');fst=load('data/flow-study-v11.json')
html=(ROOT/'forecast-final.html').read_text(encoding='utf-8');js=(ROOT/'forecast-final-v11.js').read_text(encoding='utf-8')
# Contract and point-in-time architecture
ck('model version V11',model.get('version')=='VMEWS-FORECAST-11.0.0',model.get('version'));ck('current version V11',cur.get('version')=='VMEWS-FORECAST-11.0.0');ck('dashboard model version',dash.get('modelVersion')==model.get('version'));ck('five direct horizons',set(model.get('horizons',{}))==set('12345'),list(model.get('horizons',{})));ck('large HOSE universe',model['universe']['symbols']>=350,model['universe']['symbols']);ck('large PIT panel',model['universe']['rows']>=120000,model['universe']['rows']);ck('long history start',model['universe']['start']<'2020-01-01',model['universe']['start']);ck('audit end recent',model['universe']['end']>='2026-07-01',model['universe']['end']);ck('current broad coverage',cur['count']>=350,cur['count']);ck('dashboard broad coverage',dash['counts']['symbols']>=350,dash['counts']);ck('chart broad coverage',dash['counts']['chartSymbols']>=340,dash['counts']['chartSymbols'])
for h in range(1,6):
    z=model['horizons'][str(h)];a=z['sealedAudit'];g=z['gates'];ck(f'T+{h} sealed n',a['n']>=9000,a['n']);ck(f'T+{h} alpha IC finite positive',fin(a['alphaIC']) and a['alphaIC']>.005,a['alphaIC']);ck(f'T+{h} spread finite positive',fin(a['alphaSpread']) and a['alphaSpread']>.0005,a['alphaSpread']);ck(f'T+{h} balanced direction sane',fin(a['balancedAccuracy']) and a['balancedAccuracy']>=.50,a['balancedAccuracy']);ck(f'T+{h} MCC nonnegative',fin(a['mcc']) and a['mcc']>=0,a['mcc']);ck(f'T+{h} Brier not catastrophic',fin(a['brierSkill']) and a['brierSkill']>-.04,a['brierSkill']);ck(f'T+{h} ECE bounded',fin(a['ece']) and a['ece']<.12,a['ece']);ck(f'T+{h} scenario rank',fin(a['scenarioRankIC']) and a['scenarioRankIC']>-.005,a['scenarioRankIC']);ck(f'T+{h} interval coverage',fin(a['coverage20_80']) and .45<=a['coverage20_80']<=.75,a['coverage20_80']);ck(f'T+{h} calibration buckets',len(z['calibration'])>=7,len(z['calibration']));ck(f'T+{h} direct choice exists',z.get('choice',{}).get('reg') in {'RIDGE','HGB'} and z.get('choice',{}).get('cls') in {'LINEAR','HGB'},z.get('choice'))
# Current symbol invariants, wide ticker sample
sample=sorted(cur['symbols'])[:25]+[s for s in ['FPT','FRT','PNJ','VCB','HPG','MBB','SSI','VHM','MWG','DGC'] if s in cur['symbols']]
for s in dict.fromkeys(sample):
    z=cur['symbols'][s];ck(f'{s} has all horizons',all(str(h) in z.get('horizons',{}) for h in range(1,6)));ck(f'{s} risk bounded',fin(z.get('technical')) and 0<=z['technical']<=100,z.get('technical'));ck(f'{s} market psychology present',all(k in z.get('market',{}) for k in ['breadth20','csad20','herdingCompression','turnoverConcentration']));
    for h in range(1,6):
        x=z['horizons'][str(h)];ck(f'{s} T+{h} scenario finite',all(fin(x.get(k)) for k in ['alpha','historicalUpRate','medianReturn','q20','q80']),x);ck(f'{s} T+{h} quantile order',x['q20']<=x['medianReturn']<=x['q80'],(x['q20'],x['medianReturn'],x['q80']))
# News coverage: broad history, supervised labels, official/mainstream/rumor separation
ns=nh['summary'];ck('news universe broad',nh['universe']>=350,nh['universe']);ck('news articles substantial',ns['articles']>=5000,ns);ck('news symbols broad',ns['symbolsWithNews']>=340,ns);ck('news median per symbol >=10',ns['medianPerSymbol']>=10,ns);ck('news 10+ coverage',ns['symbols10plus']>=300,ns);ck('sentiment articles parity',sent['summary']['articles']>=int(.95*ns['articles']),sent['summary']);ck('sentiment symbols broad',sent['summary']['symbols']>=340,sent['summary']);ck('sentiment has POS',sent['summary']['positive']>100);ck('sentiment has NEG',sent['summary']['negative']>100);ck('sentiment has NEU',sent['summary']['neutral']>100)
sourceClasses=set();streams=set();events=set();methods=set()
for z in sent['symbols'].values():
    for x in z['items']:
        sourceClasses.add(x.get('sourceClass'));streams.add(x.get('stream'));events.add(x.get('event'));methods.add(x.get('method'))
ck('official/mainstream source taxonomy',{'OFFICIAL','MAINSTREAM'}<=sourceClasses,sourceClasses);ck('two news streams',{'MAIN','RUMOR'}<=streams,streams);ck('event taxonomy broad',len(events)>=6,events);ck('DL sentiment actually used','phobert' in methods,methods)
ck('event study large',ev['events']>=4000,ev['events']);ck('event study broad symbols',len(ev['symbols'])>=340,len(ev['symbols']));ck('unsupervised clusters',len(ev['clusters'])>=16,len(ev['clusters']));ck('rumor study exists',ev['rumorStudy']['events']>=20,ev['rumorStudy']['events']);ck('event hierarchy exists','eventLabel' in ev['groups'] and 'cluster' in ev['groups']);ck('T+2 confirmation declared','outcomes are labels only' in ev.get('pointInTime',''),ev.get('pointInTime'))
pooled=0
for s,z in ev['symbols'].items():
    p=z.get('pooledLatest')
    if p and p.get('n',0)>=8:pooled+=1
ck('hierarchical pooled event coverage',pooled>=250,pooled)
# Flow coverage and history
fs=flow['summary'];ck('flow symbols broad',fs['symbolsWithFlow']>=300,fs);ck('flow 100+ rows broad',fs['symbols100plus']>=250,fs);ck('flow median rows >=100',fs['medianRows']>=100,fs);ck('flow current broad',len(flow.get('current',{}))>=300,len(flow.get('current',{})));ck('flow study observations large',fst['sampledObservations']>=15000,fst['sampledObservations']);ck('foreign state study',len(fst['groups']['foreign'])==5);ck('prop state study',len(fst['groups']['prop'])==5)
for typ in ('foreign','prop'):
    adequate=sum((z or {}).get('n',0)>=250 for z in fst['groups'][typ].values());ck(f'{typ} adequate pooled states',adequate>=3,{k:(v or {}).get('n',0) for k,v in fst['groups'][typ].items()})
# Dashboard semantics and no dead placeholder UI
for bad in ['Đọc hướng đi ngắn hạn','Hệ thống tách riêng','Mô hình chỉ vẽ','CHƯA CÓ','MẪU MỎNG','không phải giá mục tiêu','PhoBERT + finance rules']:
    ck(f'UI excludes phrase {bad}',bad not in html+js)
for wanted in ['Mã HOSE cần theo dõi','YELLOW','RED','Tin tức & phản ứng giá','Backtest ngoài mẫu','Các yếu tố cần cân nhắc']:
    ck(f'UI has {wanted}',wanted in html)
for wanted in ["for(let i=1;i<=5;i++)","flow5(f,'foreign')","event5(n)","herdingCompression","newsFollowsPrice","forecast-dashboard-v11.json"]:
    ck(f'frontend contract {wanted}',wanted in js)
ck('watchlist nonempty',len(dash['lists']['watch'])>=8,len(dash['lists']['watch']));ck('risk lists structurally present','yellow' in dash['lists'] and 'red' in dash['lists']);ck('fan chart has interval fill',"fillStyle='rgba(226,171,70,.12)'" in js);ck('fan chart direct horizons',"[0,1,2,3,4,5]" in js)
# Data source integrity / no NaN in exported JSON
for p in ['data/forecast-model-v11.json','data/forecast-current-v11.json','data/forecast-dashboard-v11.json','data/news-history-v11.json','data/sentiment-v11.json','data/news-event-study-v11.json','data/flow-v11.json','data/flow-study-v11.json']:
    text=(ROOT/p).read_text(encoding='utf-8');ck(f'{p} no NaN token','NaN' not in text and 'Infinity' not in text)
# Make sure test matrix is genuinely large.
ck('>=100 assertions executed before final gate',len(checks)>=100,len(checks))
failed=[x for x in checks if not x[1]];report={'version':'VMEWS-V11-ACCEPTANCE-1.0.0','tests':len(checks),'passed':len(checks)-len(failed),'failed':len(failed),'failures':[{'name':a,'detail':d} for a,_,d in failed]};(ROOT/'data/forecast-v11-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));sys.exit(1 if failed else 0)
