import argparse,hashlib,json,math,os,re,statistics
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(os.environ.get('GITHUB_WORKSPACE',Path(__file__).resolve().parents[1])).resolve()
LIVE=ROOT/'data/forecast-live';SNAPS=LIVE/'snapshots';TAPES=ROOT/'data/live-track/snapshots'
VER='VMEWS-FORECAST-LIVE-1.0.0';H=(3,5);MAC={'vixLevel','vixRet20','usdVndRet20','dxyRet20','us10yRet20','brentRet20'}

class CoverageAbstention(RuntimeError):pass

def require_cross_sectional_coverage(count,minimum=8):
 if count<minimum:raise CoverageAbstention(f'Forecast archive coverage below cross-sectional minimum: {count}/{minimum}')

def load(p,d=None):
 try:return json.loads(Path(p).read_text(encoding='utf-8'))
 except:return {} if d is None else d
def dump(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def f(x):
 try:
  v=float(x);return v if math.isfinite(v) else None
 except:return None
def avg(a):
 z=[float(x) for x in a if f(x) is not None];return statistics.fmean(z) if z else None
def med(a):
 z=[float(x) for x in a if f(x) is not None];return statistics.median(z) if z else 0.
def sig(x):return 1/(1+math.exp(-max(-35,min(35,float(x)))))
def dot(m,x):return float(m.get('intercept') or 0)+sum(float(a)*b for a,b in zip(m.get('coef') or [],x))
def vec(names,z,c,market=False):
 I=c.get('marketImpute' if market else 'impute') or [];M=c.get('marketMean' if market else 'mean') or [];S=c.get('marketStd' if market else 'std') or [];o=[]
 for i,k in enumerate(names):
  v=f(z.get(k))
  if k in MAC or v is None:v=float(I[i] if i<len(I) else 0)
  m=float(M[i] if i<len(M) else 0);s=float(S[i] if i<len(S) and abs(float(S[i]))>1e-12 else 1);o.append((v-m)/s)
 return o
def bucket(bs,x):
 for b in bs or []:
  if float(b['lo'])<=x<=float(b['hi']):return b
 return (bs or [None])[0] if not bs or x<float(bs[0]['lo']) else bs[-1]

def snapshot():
 from train_forecast_v6 import build_panel
 P,_=build_panel(str(ROOT));model=load(ROOT/'data/forecast-model-v9.json');scan=load(ROOT/'data/market-scan.json');sent=load(ROOT/'data/sentiment-v8.json',{'symbols':{}})
 if model.get('version')!='VMEWS-FORECAST-9.0.0' or model.get('promotion',{}).get('status')!='PASS':raise RuntimeError('V9 model gate not PASS')
 d=max(x['date'] for x in P);cur=[x for x in P if x['date']==d];sd=str(scan.get('modelDate') or '')[:10]
 if sd and sd!=d:raise RuntimeError(f'PIT mismatch panel={d} scan={sd}')
 rr={str(x.get('symbol') or '').upper():x for x in scan.get('ranking') or []};pred=[]
 for z in cur:
  s=str(z['symbol']).upper();r=rr.get(s);c0=f((r or {}).get('close'))
  if not r or r.get('exchange')!='HOSE' or r.get('stale') or c0 is None:continue
  hz={}
  for h in H:
   c=model['horizons'][str(h)];a=dot(c['alphaModel'],vec(model['featureNames'],z,c));p=sig(dot(c['stockDirectionModel'],vec(model['featureNames'],z,c)));mp=sig(dot(c['marketDirectionModel'],vec(model['marketFeatureNames'],z,c,True)));b=bucket(c.get('calibrationBuckets'),a)
   hz[str(h)]={'alpha':a,'pUp':p,'marketPUp':mp,'bucket':None if not b else {k:b.get(k) for k in ('n','meanReturn','positiveRate','q20','q80')}}
  ss=(sent.get('symbols') or {}).get(s) or {};pred.append({'symbol':s,'close':c0,'risk':{'status':r.get('status'),'score':f(r.get('score'))},'sentiment':{'state':ss.get('state'),'signed':f(ss.get('signed')),'n':int(ss.get('n') or 0)},'forecast':hz})
 require_cross_sectional_coverage(len(pred))
 coverage='FULL' if len(pred)>=30 else 'LIMITED_CURRENT_EOD_CACHE'
 core={'version':VER,'asOf':d,'modelVersion':model['version'],'marketScanVersion':scan.get('version'),'sentimentVersion':sent.get('version'),'symbols':len(pred),'coverageState':coverage,'predictions':pred,'governance':{'futureLabelsPresent':False,'exactPriceTarget':False,'automaticPromotion':False,'sentimentNumericalFeature':False,'foreignFlowNumericalFeature':False,'limitedCoverageDoesNotPromoteEvidence':True}}
 core['snapshotHash']=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest();return {'createdAt':datetime.now(timezone.utc).isoformat(),**core}

def archive(z):
 SNAPS.mkdir(parents=True,exist_ok=True);p=SNAPS/f"{z['asOf']}.json"
 if not p.exists():dump(p,z);return 'CREATED'
 old=load(p);return 'EXISTING_IDENTICAL' if old.get('snapshotHash')==z['snapshotHash'] else 'REVISION_DETECTED_PRESERVED_FIRST_ARCHIVE'
def ranks(a):
 o=sorted(range(len(a)),key=lambda i:a[i]);r=[0]*len(a)
 for j,i in enumerate(o):r[i]=j
 return r
def rho(a,b):
 if len(a)<8:return None
 x,y=ranks(a),ranks(b);mx,my=avg(x),avg(y);sx=math.sqrt(sum((v-mx)**2 for v in x));sy=math.sqrt(sum((v-my)**2 for v in y))
 return None if not sx or not sy else sum((u-mx)*(v-my) for u,v in zip(x,y))/(sx*sy)
def evaluate():
 tape=[]
 for p in sorted(TAPES.glob('????-??-??.json')):
  z=load(p)
  if z.get('modelDate') and z.get('snapshotHash'):z['_c']={str(x.get('symbol') or '').upper():f(x.get('close')) for x in z.get('closeTape') or []};tape.append(z)
 dates=[x['modelDate'] for x in tape];out=[];g={str(h):[] for h in H}
 for p in sorted(SNAPS.glob('????-??-??.json')):
  s=load(p)
  if s.get('asOf') not in dates:continue
  i=dates.index(s['asOf'])
  for h in H:
   if i+h>=len(tape):continue
   t=tape[i+h];rows=[]
   for x in s.get('predictions') or []:
    c0=f(x.get('close'));c1=t['_c'].get(x['symbol']);q=(x.get('forecast') or {}).get(str(h)) or {}
    if None not in (c0,c1,f(q.get('alpha')),f(q.get('pUp'))) and c0>0 and c1>0:rows.append((math.log(c1/c0),q))
   if len(rows)<8:continue
   mr=med([r for r,_ in rows]);ic=rho([float(q['alpha']) for _,q in rows],[r-mr for r,_ in rows]);m={'originDate':s['asOf'],'matureDate':t['modelDate'],'horizonSessions':h,'n':len(rows),'directionHitRate':avg([(float(q['pUp'])>=.5)==(r>0) for r,q in rows]),'brier':avg([(float(q['pUp'])-(1 if r>0 else 0))**2 for r,q in rows]),'alphaIC':ic};out.append(m);g[str(h)].append(m)
 summary={}
 for h in H:
  z=g[str(h)];summary[str(h)]={'matureOrigins':len(z),'nPredictions':sum(x['n'] for x in z),'directionHitRate':avg([x['directionHitRate'] for x in z]),'brier':avg([x['brier'] for x in z]),'alphaIC':avg([x['alphaIC'] for x in z]),'evidenceState':'MATURE' if len(z)>=20 else ('EARLY' if len(z)>=5 else 'IMMATURE')}
 return {'version':VER,'generatedAt':datetime.now(timezone.utc).isoformat(),'method':'Prequential test-then-score against immutable completed-EOD close tapes.','summary':summary,'origins':out,'governance':{'automaticPromotion':False,'minimumMatureOrigins':20}}

def manifest():
 a=[]
 for p in sorted(SNAPS.glob('????-??-??.json')):
  z=load(p);a.append({'date':z.get('asOf'),'file':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'snapshotHash':z.get('snapshotHash'),'modelVersion':z.get('modelVersion'),'symbols':z.get('symbols'),'coverageState':z.get('coverageState')})
 return {'version':VER,'generatedAt':datetime.now(timezone.utc).isoformat(),'count':len(a),'snapshots':a,'rule':'Append-only date-keyed forecast snapshots; first archive is preserved.'}
def verify():
 m=load(LIVE/'manifest.json')
 for x in m.get('snapshots') or []:
  p=ROOT/x['file'];z=load(p)
  if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=x['sha256'] or z.get('snapshotHash')!=x.get('snapshotHash') or z.get('governance',{}).get('futureLabelsPresent') is not False:raise RuntimeError(f'Forecast-live integrity failure {p}')
 return {'ok':True,'snapshots':len(m.get('snapshots') or [])}
def live():
 try:z=snapshot()
 except CoverageAbstention as error:
  attempt={'version':VER,'generatedAt':datetime.now(timezone.utc).isoformat(),'status':'WAITING_OR_REVIEW','reason':str(error),'timeBasis':'COMPLETED_EOD_ONLY','preservesLastValidatedSnapshot':True,'automaticPromotion':False}
  dump(LIVE/'last-attempt.json',attempt);print(json.dumps({'legacyV9Attempt':attempt},ensure_ascii=False,indent=2));return
 st=archive(z);ev=evaluate();dump(LIVE/'evaluation.json',ev);dump(LIVE/'manifest.json',manifest());q={'version':VER,'generatedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS','asOf':z['asOf'],'archiveStatus':st,'coverageState':z.get('coverageState'),'symbols':z.get('symbols'),'integrity':verify(),'modelVersion':z['modelVersion'],'sentimentVersion':z.get('sentimentVersion'),'timeBasis':'COMPLETED_EOD_ONLY'};dump(LIVE/'integrity.json',q);dump(LIVE/'last-attempt.json',{'version':VER,'generatedAt':q['generatedAt'],'status':'PASS','asOf':z['asOf'],'symbols':z.get('symbols'),'preservesLastValidatedSnapshot':True});print(json.dumps({'integrity':q,'evaluation':ev['summary']},ensure_ascii=False,indent=2))

def train():
 p=Path(__file__).with_name('train_forecast_v9.py');s=p.read_text(encoding='utf-8');s=s.replace("an=A[0]['name'];dn=C[0]['name'];mn=MC[0]['name'];","an='ridge';dn='logit';mn='logit';");s=re.sub(r"\nif __name__=='__main__':train\(os\.environ\.get\('GITHUB_WORKSPACE','\.'\)\)\s*$",'',s);ns={'__name__':'v9_deployable','__file__':str(p)};exec(compile(s,str(p),'exec'),ns);ns['train'](str(ROOT))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--live',action='store_true');ap.add_argument('--verify-live',action='store_true');a=ap.parse_args()
 if a.verify_live:print(json.dumps(verify()))
 elif a.live:live()
 else:train()
