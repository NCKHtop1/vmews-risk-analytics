import json,math,os
from pathlib import Path
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import MiniBatchKMeans
from forecast_v11_features import yahoo_adjusted
ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));H=(1,2,3,4,5);PRE=(1,2,5);VERSION='VMEWS-NEWS-EVENT-11.2.0'
def dt(x):
    try:return datetime.fromisoformat(str(x).replace('Z','+00:00')).astimezone(timezone(timedelta(hours=7)))
    except:
        try:return parsedate_to_datetime(str(x)).astimezone(timezone(timedelta(hours=7)))
        except:return None
def price(sym):
    try:r,_=yahoo_adjusted(sym,'10y',15);return sym,r
    except:return sym,[]
def effective(rows,d):
    target=d.date().isoformat();after=d.hour>=15
    for i,x in enumerate(rows):
        if x['date']>target or (x['date']==target and not after):return i
    return None
def stats(v):
    a=np.asarray([x for x in v if isinstance(x,(int,float)) and math.isfinite(x)],float);n=len(a)
    if not n:return None
    se=float(np.std(a,ddof=1)/math.sqrt(n)) if n>1 else None;mu=float(np.mean(a));return {'n':n,'meanAR':mu,'medianAR':float(np.median(a)),'positiveRate':float(np.mean(a>0)),'q20':float(np.quantile(a,.2)),'q80':float(np.quantile(a,.8)),'se':se,'tStat':float(mu/se) if se and se>0 else None}
def aggregate(items):
    out={'n':len(items),'horizons':{},'preEvent':{}}
    for h in H:
        s=stats([x.get('ar'+str(h)) for x in items]);
        if s:out['horizons'][str(h)]=s
    for h in PRE:
        s=stats([x.get('preAR'+str(h)) for x in items]);
        if s:out['preEvent'][str(h)]=s
    c=[x.get('confirmT2') for x in items if x.get('confirmT2') in {'POS','NEG','NEU'}];out['confirmT2']={k:sum(x==k for x in c)/len(c) for k in ('POS','NEG','NEU')} if c else None;pre=[x.get('preAR2') for x in items if isinstance(x.get('preAR2'),(int,float))];out['preMoveShare2']=float(np.mean(np.abs(pre)>.01)) if pre else None;return out
def sector_map():
    out={}
    try:
        scan=json.loads((ROOT/'data/market-scan.json').read_text(encoding='utf-8'))
        for x in scan.get('ranking',[]):
            if x.get('exchange')=='HOSE' and x.get('symbol') and str(x.get('sector') or '').strip():out[str(x['symbol']).upper()]=str(x['sector']).strip()
    except:pass
    try:
        from tradingview_screener import stocks
        _,df=stocks('vietnam').select('name','exchange','sector').limit(3000).get_scanner_data()
        if df is not None:
            for _,r in df.iterrows():
                s=str(r.get('name') or '').upper().split(':')[-1].strip();sec=str(r.get('sector') or '').strip();ex=str(r.get('exchange') or '').upper()
                if s and sec and ex in {'HOSE','HSX','HOCHIMINH'}:out.setdefault(s,sec)
    except:pass
    return out
def main():
    sent=json.loads((ROOT/'data/sentiment-v11.json').read_text(encoding='utf-8'));sectorBy=sector_map();items=[]
    for s,z in sent['symbols'].items():
        for x in z['items']:items.append({'symbol':s,'sector':sectorBy.get(s,'OTHER'),**x})
    texts=[x['title'] for x in items]
    if len(texts)<100:raise RuntimeError('event-study news history too small')
    vec=TfidfVectorizer(max_features=5000,ngram_range=(1,2),min_df=3,max_df=.93);X=vec.fit_transform(texts);k=max(18,min(56,int(math.sqrt(len(texts)/18))));km=MiniBatchKMeans(n_clusters=k,random_state=43,n_init=10,batch_size=1024).fit(X);terms=np.asarray(vec.get_feature_names_out());clusters={str(j):{'n':int(np.sum(km.labels_==j)),'terms':[str(x) for x in terms[np.argsort(km.cluster_centers_[j])[-7:][::-1]]]} for j in range(k)}
    for x,c in zip(items,km.labels_):x['cluster']=int(c)
    syms=sorted(sent['symbols']);prices={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs={ex.submit(price,s):s for s in syms}
        for f in as_completed(fs):s,r=f.result();prices[s]=r
    raw=[]
    for x in items:
        d=dt(x.get('publishedAt'));r=prices.get(x['symbol']) or []
        if not d or not r:continue
        i=effective(r,d)
        if i is None:continue
        z={'id':x['id'],'symbol':x['symbol'],'sector':x['sector'],'title':x['title'],'publishedAt':x['publishedAt'],'effectiveDate':r[i]['date'],'event':x['event'],'label':x['label'],'stream':x['stream'],'sourceClass':x['sourceClass'],'publisher':x['publisher'],'cluster':x['cluster']}
        for h in H:
            if i+h<len(r):z['r'+str(h)]=float(math.log(r[i+h]['modelClose']/r[i]['modelClose']))
        for h in PRE:
            if i-h>=0:z['preR'+str(h)]=float(math.log(r[i]['modelClose']/r[i-h]['modelClose']))
        raw.append(z)
    bench={}
    for x in raw:
        for h in H:
            if 'r'+str(h) in x:bench.setdefault((x['effectiveDate'],'r'+str(h)),[]).append(x['r'+str(h)])
        for h in PRE:
            if 'preR'+str(h) in x:bench.setdefault((x['effectiveDate'],'preR'+str(h)),[]).append(x['preR'+str(h)])
    med={k:float(np.median(v)) for k,v in bench.items() if len(v)>=8};mature=[]
    for x in raw:
        z=dict(x)
        for h in H:
            k=(x['effectiveDate'],'r'+str(h));
            if 'r'+str(h) in x and k in med:z['ar'+str(h)]=x['r'+str(h)]-med[k]
        for h in PRE:
            k=(x['effectiveDate'],'preR'+str(h));
            if 'preR'+str(h) in x and k in med:z['preAR'+str(h)]=x['preR'+str(h)]-med[k]
        a=z.get('ar2');z['confirmT2']='POS' if isinstance(a,(int,float)) and a>.01 else 'NEG' if isinstance(a,(int,float)) and a<-.01 else 'NEU' if isinstance(a,(int,float)) else None;p=z.get('preAR2');post=z.get('ar2');z['newsFollowsPrice']=bool(isinstance(p,(int,float)) and abs(p)>.01 and (not isinstance(post,(int,float)) or (p>0)==(post>0)));mature.append(z)
    def group(key):
        g={}
        for x in mature:g.setdefault(str(key(x)),[]).append(x)
        return {k:aggregate(v) for k,v in g.items()}
    groups={'event':group(lambda x:x['event']),'eventLabel':group(lambda x:x['event']+'|'+x['label']),'sectorEvent':group(lambda x:x['sector']+'|'+x['event']),'sectorEventLabel':group(lambda x:x['sector']+'|'+x['event']+'|'+x['label']),'cluster':group(lambda x:x['cluster']),'sourceClass':group(lambda x:x['sourceClass']),'stream':group(lambda x:x['stream'])};tickerEvent={}
    for x in mature:tickerEvent.setdefault((x['symbol'],x['event'],x['label']),[]).append(x)
    idCluster={x['id']:x['cluster'] for x in items};now=max([dt(x['publishedAt']) for x in items if dt(x['publishedAt'])] or [datetime.now(timezone.utc)]);bys={}
    for s,z in sent['symbols'].items():
        cur=sorted(z['items'],key=lambda x:x['publishedAt'],reverse=True);latest=cur[0] if cur else None;rows=[x for x in mature if x['symbol']==s];pooled=None;sector=sectorBy.get(s,'OTHER')
        if latest:
            direct=tickerEvent.get((s,latest['event'],latest['label']),[]);cand=[('TICKER_EVENT',aggregate(direct)),('SECTOR_EVENT_LABEL',groups['sectorEventLabel'].get(sector+'|'+latest['event']+'|'+latest['label'])),('EVENT_LABEL',groups['eventLabel'].get(latest['event']+'|'+latest['label'])),('SECTOR_EVENT',groups['sectorEvent'].get(sector+'|'+latest['event'])),('EVENT',groups['event'].get(latest['event'])),('CLUSTER',groups['cluster'].get(str(idCluster.get(latest['id'],-1))))];pooled=next(({'level':n,**a} for n,a in cand if a and a.get('n',0)>=20),None) or next(({'level':n,**a} for n,a in cand if a and a.get('n',0)>=8),None)
        d7=sum((now-dt(x['publishedAt'])).days<=7 for x in cur if dt(x['publishedAt']));d30=sum((now-dt(x['publishedAt'])).days<=30 for x in cur if dt(x['publishedAt']));velocity=d7/max(1,d30/4.3);recent=[{k:x.get(k) for k in ('id','title','link','publishedAt','publisher','stream','sourceClass','event','label','confidence')} for x in cur[:20]];latestM=next((x for x in mature if latest and x['id']==latest['id']),None);bys[s]={'sector':sector,'newsCount':len(cur),'publishers':len(set(x['publisher'] for x in cur)),'years':len(set(x['publishedAt'][:4] for x in cur)),'newsVelocity7v30':velocity,'sentiment':z['signed'],'counts':z['counts'],'recent':recent,'tickerStudy':aggregate(rows),'pooledLatest':pooled,'latestOutcomeStudy':latestM}
    rumor=[x for x in mature if x['sourceClass']=='RUMOR_UNVERIFIED'];clar=[x for x in mature if x['sourceClass']=='CLARIFICATION'];out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'pointInTime':'publishedAt is the availability timestamp; T+2 confirmation and T+1..T+5 outcomes are labels only, never forecast features','events':len(mature),'symbols':bys,'groups':groups,'clusters':clusters,'sectorCoverage':sum(z['sector']!='OTHER' for z in bys.values()),'sectorFallbackCount':sum(z['sector']=='OTHER' for z in bys.values()),'rumorStudy':{**aggregate(rumor),'events':len(rumor),'share':len(rumor)/max(1,len(mature)),'symbols':len(set(x['symbol'] for x in rumor))},'clarificationStudy':{**aggregate(clar),'events':len(clar),'share':len(clar)/max(1,len(mature))}}
    (ROOT/'data/news-event-study-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps({'events':out['events'],'symbols':len(bys),'sectorCoverage':out['sectorCoverage'],'rumors':len(rumor),'medianNews':int(np.median([z['newsCount'] for z in bys.values()])),'FPT':bys.get('FPT',{}).get('newsCount')},ensure_ascii=False))
if __name__=='__main__':main()
