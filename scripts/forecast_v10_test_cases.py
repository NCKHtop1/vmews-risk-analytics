import json, math, glob, re
from pathlib import Path
from forecast_v4_features import stock_features
ROOT=Path(__file__).resolve().parents[1]
M=json.loads((ROOT/'data/forecast-model-v10.json').read_text(encoding='utf-8'));N=json.loads((ROOT/'data/research-news-v10.json').read_text(encoding='utf-8'));S=json.loads((ROOT/'data/sentiment-v10.json').read_text(encoding='utf-8'));E=json.loads((ROOT/'data/news-event-study.json').read_text(encoding='utf-8'));HTML=(ROOT/'forecast-final.html').read_text(encoding='utf-8');JS=(ROOT/'forecast-final-v10.js').read_text(encoding='utf-8')
def finite(x):
 try:return math.isfinite(float(x))
 except:return False
def buckets(bs,name):
 assert len(bs)>=6,(name,len(bs));prev=-float('inf')
 for b in bs:
  assert finite(b['lo']) and finite(b['hi']) and b['lo']<=b['hi'] and b['lo']>=prev-1e-12,(name,b);assert b['n']>=30 and 0<=b['positiveRate']<=1,(name,b);assert b['q20']<=b['q80'];prev=b['hi']
def lin(m,x):return float(m['intercept'])+sum(float(a)*float(b) for a,b in zip(m['coef'],x))
def sigmoid(x):return 1/(1+math.exp(-max(-35,min(35,x))))
def getb(bs,x):
 for b in bs:
  if x>=b['lo'] and x<=b['hi']:return b
 return bs[0] if x<bs[0]['lo'] else bs[-1]
def infer(raw):
 rows,fs=stock_features(raw)
 if not fs:return None
 f=fs[-1];out={}
 for h in ('3','5'):
  z=M['horizons'][h];v=[]
  for i,k in enumerate(M['featureNames']):
   x=f.get(k,z['impute'][i]);x=float(x) if finite(x) else float(z['impute'][i]);sd=float(z['std'][i]);v.append((x-float(z['mean'][i]))/(sd if abs(sd)>1e-12 else 1))
  a=lin(z['alphaModel'],v);d=sigmoid(lin(z['directionModel'],v));out[h]=(a,d,getb(z['alphaCalibrationBuckets'],a),getb(z['directionCalibrationBuckets'],d))
 return out
def adjusted(c):
 c=list(map(float,c));a=[None]*len(c);a[-1]=c[-1]
 for i in range(len(c)-2,-1,-1):z=math.log(c[i+1]/c[i]);z=0 if abs(z)>.22 else z;a[i]=a[i+1]/math.exp(z)
 return a
# TC01 identity and breadth
assert M['version']=='VMEWS-FORECAST-10.1.0' and M['promotion']['status']=='PASS';assert M['universe']['symbols']>=250 and M['universe']['rows']>=100000;assert M['governance'].get('crossSectionalFeaturesInNumericalModel') is False
# TC02 strict train/live feature parity
forbidden={'relRet1','relRet5','relRet20','rankRet5','rankRet20','rankTechnical','breadth1','breadth5','breadth20','trend20Share','riskShare','csad1','csad5','dispersion20','marketRet1','marketRet5','marketRet20','marketTechnical','vixLevel','vixRet20','usdVndRet20','dxyRet20','us10yRet20','brentRet20'};assert not(forbidden&set(M['featureNames'])),forbidden&set(M['featureNames'])
# TC03 parameters and calibration contracts
p=len(M['featureNames'])
for h in ('3','5'):
 z=M['horizons'][h];assert z['status']=='PASS' and z['gates']['rankingApproved'] and z['gates']['directionApproved'] and z['gates']['alphaCalibrationApproved'];assert all(len(z[k])==p and all(finite(x) for x in z[k]) for k in ('impute','mean','std'));assert len(z['alphaModel']['coef'])==p and len(z['directionModel']['coef'])==p;buckets(z['alphaCalibrationBuckets'],h+'a');buckets(z['directionCalibrationBuckets'],h+'d')
# TC04 sealed audit and regime stability
for h in ('3','5'):
 a=M['horizons'][h]['sealedAudit'];assert a['n']>=10000 and a['alphaIC']>.02 and a['alphaSpread']>.002;assert a['bootstrap']['ic95'][0]>-.005;assert a['directionBalancedAccuracy']>.515 and a['directionMCC']>.02;assert M['horizons'][h]['gates']['betterThanMomentumRank'];
 for seg in ('firstHalf','secondHalf','bear','bull'):
  s=a['segments'].get(seg);assert s and s['n']>=500 and s['alphaIC']>.005,(h,seg,s)
# TC05 corporate-action chart guard
raw=[100,100,50,51,52];a=adjusted(raw);assert max(abs(a[i]/a[i-1]-1) for i in range(1,len(a)))<.05,(raw,a)
# TC06 real local inference
files=glob.glob(str(ROOT/'data/hose-fallbacks/*.json'))+glob.glob(str(ROOT/'data/deep-alerts/*.json'));seen=set();tested=[]
for pth in files:
 try:z=json.loads(Path(pth).read_text(encoding='utf-8'));sym=str(z.get('symbol') or Path(pth).stem).upper();hist=z.get('history') or []
 except:continue
 if sym in seen or len(hist)<520:continue
 seen.add(sym);pred=infer(hist)
 if not pred:continue
 for h,(aa,d,ab,db) in pred.items():assert finite(aa) and abs(aa)<.25 and 0<d<1 and ab and db,(sym,h,aa,d)
 tested.append(sym)
 if len(tested)>=20:break
assert len(tested)>=5,tested
# TC07 news breadth and hygiene
assert N['version']=='VMEWS-NEWS-10.0.0' and N['universe']>=300 and N['coverage'].get('FRT',{}).get('used',0)>=5;with_news=sum(x.get('used',0)>=1 for x in N['coverage'].values());assert with_news>=250,with_news
sources={'OFFICIAL','MAINSTREAM','RUMOR_UNVERIFIED','CLARIFICATION'};events={'REGULATORY','EARNINGS','OWNERSHIP','CORPORATE_ACTION','FINANCING','OPERATIONS_MA','ANALYST','GENERAL'}
for sym,items in N['symbols'].items():
 titles=[re.sub(r'\s+',' ',str(x.get('title') or '')).strip().lower() for x in items];assert len(titles)==len(set(titles)),sym
 for x in items:assert x.get('sourceClass') in sources and x.get('event') in events and 0<=float(x.get('sourceQuality',0))<=1 and 0<=float(x.get('materiality',0))<=1,(sym,x)
# TC08 sentiment stays context-only
assert S['version']=='VMEWS-SENTIMENT-10.0.0' and len(S.get('symbols',{}))>=250 and S['symbols'].get('FRT',{}).get('n',0)>=5;assert not any('sentiment' in k.lower() or 'news' in k.lower() for k in M['featureNames'])
# TC09 event study, unsupervised clusters, rumor diagnostics
assert E['version']=='VMEWS-NEWS-EVENT-STUDY-1.2.0' and E['pointInTimeEligibleForForecast'] is False;assert E['events']>=1000 and E['symbolsWithPrice']>=300 and len(E.get('clusters',{}))>=6;r=E['rumorStudy'];assert r['n']>=10 and r.get('preEvent',{}).get('2') and r.get('horizons',{}).get('5') and finite(r.get('preMoveShare2'));frt=E.get('symbols',{}).get('FRT',{}).get('latestEvent');assert frt and frt.get('cluster') is not None and frt.get('historicalSameCluster')
# TC10 UI contract
for bad in ('Đọc hướng đi ngắn hạn cùng trạng thái rủi ro','Hệ thống tách riêng khả năng xếp hạng tương đối','Mô hình chỉ vẽ các horizon','Khối ngoại / tự doanh'):assert bad not in HTML
assert '/flow?' not in JS and 'P(tăng)' not in JS and "x!==null&&x!==undefined&&x!==''" in JS and 'Math.abs(z)>.22' in JS and 'displayClose' in JS and 'directionCalibrationBuckets' in JS and 'alphaCalibrationBuckets' in JS
print(json.dumps({'ok':True,'testCases':10,'localSymbolsTested':tested,'model':M['version'],'symbols':M['universe']['symbols'],'rows':M['universe']['rows'],'newsSymbolsWithNews':with_news,'eventStudyEvents':E['events'],'rumors':r['n']},ensure_ascii=False))
