import json,re,math,time,os
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));MANIFEST=ROOT/'data/hose-fallbacks/manifest.json';VERSION='VMEWS-FLOW-11.0.0';BASE='https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/'

def syms():
 m=json.loads(MANIFEST.read_text(encoding='utf-8'));return sorted(s for s,r in (m.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520)
def nkey(k):return re.sub(r'[^a-z0-9]','',str(k).lower())
def longest_list(x):
 best=[]
 if isinstance(x,list) and (not x or isinstance(x[0],dict)):best=x
 if isinstance(x,dict):
  for v in x.values():
   z=longest_list(v)
   if len(z)>len(best):best=z
 return best
def get(url,timeout=20):
 with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 VMEWS-Flow/11','Referer':'https://cafef.vn/du-lieu/lich-su-giao-dich-fpt-3.chn'}),timeout=timeout) as r:return json.loads(r.read().decode('utf-8','ignore'))
def page(sym,kind,p,size=500):
 ep='GDKhoiNgoai.ashx' if kind=='foreign' else 'GDTuDoanh.ashx';q=urlencode({'Symbol':sym,'Exchange':'HOSE','StartDate':'01/01/2018','EndDate':'31/12/2026','PageIndex':p,'PageSize':size});return longest_list(get(BASE+ep+'?'+q))
def val(row,include,exclude=()):
 for k,v in row.items():
  nk=nkey(k)
  if all(x in nk for x in include) and not any(x in nk for x in exclude):
   try:return float(str(v).replace(',',''))
   except:pass
 return None
def datev(row):
 for k,v in row.items():
  if 'date' in nkey(k) or 'ngay' in nkey(k):
   s=str(v).split('T')[0].strip()
   for f in ('%d/%m/%Y','%Y-%m-%d','%m/%d/%Y'):
    try:return datetime.strptime(s,f).date().isoformat()
    except:pass
 return None
def parse(row,kind):
 d=datev(row)
 if not d:return None
 buyV=val(row,('mua','gt')) or val(row,('buy','value')) or 0.;sellV=val(row,('ban','gt')) or val(row,('sell','value')) or 0.;buyQ=val(row,('mua','kl')) or val(row,('buy','volume')) or 0.;sellQ=val(row,('ban','kl')) or val(row,('sell','volume')) or 0.
 netV=val(row,('rong','gt')) or val(row,('net','value'));netQ=val(row,('rong','kl')) or val(row,('net','volume'));netV=(buyV-sellV) if netV is None else netV;netQ=(buyQ-sellQ) if netQ is None else netQ
 z={'date':d,kind+'BuyValue':buyV,kind+'SellValue':sellV,kind+'NetValue':netV,kind+'BuyVolume':buyQ,kind+'SellVolume':sellQ,kind+'NetVolume':netQ}
 if kind=='foreign':
  room=val(row,('room',),('total',));own=val(row,('sohuu',)) or val(row,('ownership',));
  if room is not None:z['foreignRoom']=room
  if own is not None:z['foreignOwnership']=own
 return z
def fetch_kind(sym,kind):
 all=[];seen=set()
 for p in range(1,40):
  try:r=page(sym,kind,p,500)
  except Exception:
   time.sleep(.4);continue
  if not r:break
  fresh=0
  for x in r:
   z=parse(x,kind)
   if z and z['date'] not in seen:seen.add(z['date']);all.append(z);fresh+=1
  if fresh==0 or len(r)<500:break
 return all
def one(sym):
 f=fetch_kind(sym,'foreign');p=fetch_kind(sym,'prop');d={}
 for x in f+p:d.setdefault(x['date'],{'date':x['date']}).update(x)
 rows=[d[k] for k in sorted(d)];return sym,rows
def roll(rows,k,field):return float(sum(float(x.get(field,0) or 0) for x in rows[-k:])) if rows else 0.
def current(rows):
 if not rows:return None
 z={'date':rows[-1]['date']}
 for typ in ('foreign','prop'):
  fld=typ+'NetValue';gross=typ+'BuyValue';gross2=typ+'SellValue'
  for k in (1,5,20):z[typ+'Net'+str(k)]=roll(rows,k,fld)
  vals=np.asarray([float(x.get(fld,0) or 0) for x in rows[-60:]],float);z[typ+'Z60']=float((vals[-1]-vals.mean())/(vals.std(ddof=1) or 1)) if len(vals)>2 else 0.;g=sum(float(x.get(gross,0) or 0)+float(x.get(gross2,0) or 0) for x in rows[-20:]);z[typ+'NetRatio20']=z[typ+'Net20']/g if g else 0.
 if 'foreignRoom' in rows[-1]:z['foreignRoom']=rows[-1]['foreignRoom']
 return z
def main():
 symbols=syms();data={};cur={}
 with ThreadPoolExecutor(max_workers=18) as ex:
  fs={ex.submit(one,s):s for s in symbols}
  for i,f in enumerate(as_completed(fs),1):
   s,r=f.result();data[s]=r;c=current(r)
   if c:cur[s]=c
   if i%50==0:print(json.dumps({'flowSymbolsDone':i,'total':len(symbols)}))
 counts=sorted(len(x) for x in data.values());out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'source':'CafeF public historical foreign/proprietary endpoints','start':'2018-01-01','symbols':data,'current':cur,'summary':{'symbols':len(symbols),'symbolsWithFlow':sum(x>0 for x in counts),'symbols100plus':sum(x>=100 for x in counts),'symbols500plus':sum(x>=500 for x in counts),'medianRows':counts[len(counts)//2] if counts else 0,'p10Rows':counts[int(.1*(len(counts)-1))] if counts else 0}}
 (ROOT/'data/flow-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps(out['summary'],ensure_ascii=False))
if __name__=='__main__':main()
