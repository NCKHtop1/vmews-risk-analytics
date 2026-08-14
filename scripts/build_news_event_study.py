import json,math,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import MiniBatchKMeans
from forecast_v4_features import yahoo,sanitize
ROOT=Path(__file__).resolve().parents[1];H=(1,2,3,4,5);PRE=(1,2,5)
def pubdt(x):
 try:return parsedate_to_datetime(str(x)).astimezone(timezone(timedelta(hours=7)))
 except:return None
def load_price(sym):
 try:
  r=yahoo(sym+'.VN');rows=sanitize([{'date':x['date'],'close':x['close'],'open':x['close'],'high':x['close'],'low':x['close'],'volume':0} for x in r]);return sym,rows
 except:return sym,[]
def effective(rows,d,after_close):
 ds=[x['date'] for x in rows];target=d.date().isoformat()
 for i,x in enumerate(ds):
  if (x>target) or (x==target and not after_close):return i
 return None
def retmap(rows):
 out={};c=np.asarray([x['modelClose'] for x in rows],float)
 for i,r in enumerate(rows):
  z={}
  for h in H:
   if i+h<len(rows):z['f'+str(h)]=float(math.log(c[i+h]/c[i]))
  for h in PRE:
   if i-h>=0:z['p'+str(h)]=float(math.log(c[i]/c[i-h]))
  out[r['date']]=z
 return out
def stats(vals):
 a=np.asarray(vals,float);n=len(a)
 if not n:return None
 se=float(np.std(a,ddof=1)/math.sqrt(n)) if n>1 else None;mu=float(np.mean(a));t=mu/se if se and se>0 else None
 return {'n':n,'meanAR':mu,'medianAR':float(np.median(a)),'positiveRate':float(np.mean(a>0)),'q20':float(np.quantile(a,.2)),'q80':float(np.quantile(a,.8)),'se':se,'tStat':float(t) if t is not None else None}
def agg(items):
 if not items:return {'n':0,'evidence':'THIN'}
 out={'n':len(items),'evidence':'MATURE' if len(items)>=50 else 'MODERATE' if len(items)>=20 else 'LIMITED' if len(items)>=8 else 'THIN','horizons':{},'preEvent':{}}
 for h in H:
  vals=[x.get('ar'+str(h)) for x in items if isinstance(x.get('ar'+str(h)),(int,float))];s=stats(vals)
  if s:out['horizons'][str(h)]=s
 for h in PRE:
  vals=[x.get('preAR'+str(h)) for x in items if isinstance(x.get('preAR'+str(h)),(int,float))];s=stats(vals)
  if s:out['preEvent'][str(h)]=s
 c=[x.get('confirmT2') for x in items if x.get('confirmT2') in {'POS','NEG','NEU'}];out['confirmT2']={k:sum(v==k for v in c)/len(c) for k in ('POS','NEG','NEU')} if c else None
 pre2=[x.get('preAR2') for x in items if isinstance(x.get('preAR2'),(int,float))];out['preMoveShare2']=float(np.mean(np.abs(pre2)>.01)) if pre2 else None
 return out
def main(root='.'):
 root=Path(root);sent=json.loads((root/'data/sentiment-v10.json').read_text(encoding='utf-8'));allitems=[]
 for sym,z in sent.get('symbols',{}).items():
  for x in z.get('items',[]):allitems.append({'symbol':sym,**x})
 texts=[str(x.get('title') or '') for x in allitems];clusters=[];clusterInfo={}
 if len(texts)>=60:
  vec=TfidfVectorizer(max_features=1200,ngram_range=(1,2),min_df=2,max_df=.92);X=vec.fit_transform(texts);k=max(6,min(14,int(math.sqrt(len(texts)/2))));km=MiniBatchKMeans(n_clusters=k,random_state=27,n_init=10,batch_size=256).fit(X);clusters=[int(x) for x in km.labels_];terms=np.asarray(vec.get_feature_names_out())
  for j in range(k):clusterInfo[str(j)]={'n':int(np.sum(km.labels_==j)),'topTerms':[str(x) for x in terms[np.argsort(km.cluster_centers_[j])[-6:][::-1]]]}
 else:clusters=[-1]*len(allitems)
 for x,c in zip(allitems,clusters):x['cluster']=c
 syms=sorted(set(x['symbol'] for x in allitems));prices={}
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs={ex.submit(load_price,s):s for s in syms}
  for f in as_completed(fs):s,r=f.result();prices[s]=r
 rmap={s:retmap(r) for s,r in prices.items() if r};cross={}
 for m in rmap.values():
  for d,z in m.items():
   for k,v in z.items():cross.setdefault((d,k),[]).append(v)
 med={k:float(np.median(v)) for k,v in cross.items() if len(v)>=8};mature=[]
 for x in allitems:
  d=pubdt(x.get('published'));rows=prices.get(x['symbol']) or []
  if not d or not rows:continue
  i=effective(rows,d,d.hour>=15)
  if i is None:continue
  origin=rows[i]['date'];z={'symbol':x['symbol'],'title':x.get('title'),'published':x.get('published'),'effectiveDate':origin,'event':x.get('event'),'sourceClass':x.get('sourceClass'),'label':x.get('label'),'cluster':x.get('cluster')}
  for h in H:
   if i+h<len(rows):
    r=float(math.log(rows[i+h]['modelClose']/rows[i]['modelClose']));z['r'+str(h)]=r
    if (origin,'f'+str(h)) in med:z['ar'+str(h)]=r-med[(origin,'f'+str(h))]
  for h in PRE:
   if i-h>=0:
    r=float(math.log(rows[i]['modelClose']/rows[i-h]['modelClose']));z['preR'+str(h)]=r
    if (origin,'p'+str(h)) in med:z['preAR'+str(h)]=r-med[(origin,'p'+str(h))]
  a2=z.get('ar2');z['confirmT2']='POS' if isinstance(a2,(int,float)) and a2>.01 else 'NEG' if isinstance(a2,(int,float)) and a2<-.01 else 'NEU' if isinstance(a2,(int,float)) else None;mature.append(z)
 groups={'event':{},'label':{},'sourceClass':{},'cluster':{}}
 for field in groups:
  vals=sorted(set(str(x.get(field)) for x in mature if x.get(field) is not None))
  for v in vals:groups[field][v]=agg([x for x in mature if str(x.get(field))==v])
 bysym={}
 for s in sorted(sent.get('symbols',{})):
  rows=[x for x in mature if x['symbol']==s];cur=sent['symbols'][s];latest=(cur.get('items') or [None])[0];matched=None
  if latest:matched=groups['event'].get(str(latest.get('event')))
  bysym[s]={'newsCount':cur.get('n',0),'coverageGrade':cur.get('coverageGrade','THIN'),'sentiment':cur.get('state'),'counts':cur.get('counts'),'eventStudy':agg(rows),'latestEvent':{'title':latest.get('title'),'event':latest.get('event'),'sourceClass':latest.get('sourceClass'),'label':latest.get('label'),'historicalSameEvent':matched} if latest else None}
 rumor=[x for x in mature if x.get('sourceClass')=='RUMOR_UNVERIFIED'];clar=[x for x in mature if x.get('sourceClass')=='CLARIFICATION'];rs=agg(rumor);rs['shareOfAllEvents']=len(rumor)/len(mature) if mature else 0;rs['uniqueSymbols']=len(set(x['symbol'] for x in rumor));cs=agg(clar);cs['shareOfAllEvents']=len(clar)/len(mature) if mature else 0;cs['uniqueSymbols']=len(set(x['symbol'] for x in clar))
 out={'version':'VMEWS-NEWS-EVENT-STUDY-1.1.0','generatedAt':datetime.now(timezone.utc).isoformat(),'method':'Publication-time alignment in Vietnam; corporate-action-guarded closes; cross-sectional median market adjustment; pre-event AR(-5,-2,-1), post-event AR(+1..+5), T+2 confirmation; TF-IDF + MiniBatchKMeans descriptive clusters','pointInTimeEligibleForForecast':False,'warning':'Retrospective news search can have availability/revision bias. Event-study and rumor statistics are descriptive context only and do not enter the numerical forecast.','events':len(mature),'symbolsWithPrice':sum(bool(x) for x in prices.values()),'clusters':clusterInfo,'groups':groups,'rumorStudy':rs,'clarificationStudy':cs,'symbols':bysym}
 (root/'data/news-event-study.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'version':out['version'],'events':len(mature),'symbolsWithPrice':out['symbolsWithPrice'],'rumors':len(rumor),'rumorShare':rs['shareOfAllEvents'],'rumorPreMove2':rs.get('preMoveShare2'),'FRT':bysym.get('FRT')},ensure_ascii=False,default=str))
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else '.')
