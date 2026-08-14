import json,re,math,time,os,io
from pathlib import Path
from datetime import datetime,timezone,date
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from openpyxl import load_workbook

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));MANIFEST=ROOT/'data/hose-fallbacks/manifest.json';VERSION='VMEWS-FLOW-11.1.0';BASE='https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/'
HEAD={'User-Agent':'Mozilla/5.0 VMEWS-Flow/11','Referer':'https://cafef.vn/du-lieu/lich-su-giao-dich-fpt-3.chn'}
def syms():
 m=json.loads(MANIFEST.read_text(encoding='utf-8'));return sorted(s for s,r in (m.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520)
def nkey(k):
 s=str(k or '').lower();tr=str.maketrans('àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ','aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd');return re.sub(r'[^a-z0-9]','',s.translate(tr))
def longest_list(x):
 best=[]
 if isinstance(x,list) and (not x or isinstance(x[0],dict)):best=x
 if isinstance(x,dict):
  for v in x.values():
   z=longest_list(v)
   if len(z)>len(best):best=z
 return best
def get_json(url,timeout=25):
 with urlopen(Request(url,headers=HEAD),timeout=timeout) as r:return json.loads(r.read().decode('utf-8','ignore'))
def get_bytes(url,timeout=40):
 with urlopen(Request(url,headers=HEAD),timeout=timeout) as r:return r.read(),str(r.headers.get('content-type') or '')
def endpoint(kind):return 'GDKhoiNgoai.ashx' if kind=='foreign' else 'GDTuDoanh.ashx'
def export_rows(sym,kind):
 q=urlencode({'Type':'EXPORT','Symbol':sym,'Exchange':'HOSE','StartDate':'01/01/2018','EndDate':'31/12/2026','PageIndex':1,'PageSize':20});raw,ct=get_bytes(BASE+endpoint(kind)+'?'+q)
 if not raw.startswith(b'PK'):return []
 wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True);best=[]
 for ws in wb.worksheets:
  vals=list(ws.iter_rows(values_only=True))
  for hi in range(min(20,len(vals))):
   hdr=[str(x or '').strip() for x in vals[hi]];joined=' '.join(nkey(x) for x in hdr)
   if ('ngay' in joined or 'date' in joined) and any(x in joined for x in ['mua','buy','ban','sell','rong','net']):
    rows=[]
    for rr in vals[hi+1:]:
     if not any(x is not None and str(x).strip() for x in rr):continue
     rows.append({hdr[j] if j<len(hdr) and hdr[j] else f'c{j}':rr[j] for j in range(len(rr))})
    if len(rows)>len(best):best=rows
 return best
def page(sym,kind,p,size=2000):
 q=urlencode({'Symbol':sym,'Exchange':'HOSE','StartDate':'01/01/2018','EndDate':'31/12/2026','PageIndex':p,'PageSize':size});return longest_list(get_json(BASE+endpoint(kind)+'?'+q))
def asnum(v):
 if v is None:return None
 if isinstance(v,(int,float)):
  try:return float(v) if math.isfinite(float(v)) else None
  except:return None
 s=str(v).strip().replace('\xa0','').replace(' ','')
 if not s:return None
 # Excel export is normally numeric; this handles formatted strings conservatively.
 if ',' in s and '.' in s:s=s.replace(',','')
 elif s.count(',')==1 and len(s.rsplit(',',1)[-1])<=2:s=s.replace(',','.')
 else:s=s.replace(',','')
 s=s.replace('%','')
 try:return float(s)
 except:return None
def val(row,include,exclude=()):
 for k,v in row.items():
  nk=nkey(k)
  if all(x in nk for x in include) and not any(x in nk for x in exclude):
   z=asnum(v)
   if z is not None:return z
 return None
def datev(row):
 for k,v in row.items():
  if 'date' in nkey(k) or 'ngay' in nkey(k):
   if isinstance(v,(datetime,date)):return v.date().isoformat() if isinstance(v,datetime) else v.isoformat()
   s=str(v).split('T')[0].strip()
   for f in ('%d/%m/%Y','%Y-%m-%d','%m/%d/%Y','%d-%m-%Y'):
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
  room=val(row,('room',),('total',));own=val(row,('sohuu',)) or val(row,('ownership',))
  if room is not None:z['foreignRoom']=room
  if own is not None:z['foreignOwnership']=own
 return z
def fetch_kind(sym,kind):
 # Export is the only reliable way to avoid the foreign endpoint's fixed 20-row JSON cap.
 try:raw=export_rows(sym,kind)
 except Exception:raw=[]
 out=[];seen=set()
 for x in raw:
  z=parse(x,kind)
  if z and z['date'] not in seen:seen.add(z['date']);out.append(z)
 if len(out)>=100:return sorted(out,key=lambda x:x['date']), 'EXPORT_XLSX'
 # Fallback JSON. Proprietary endpoint honors large PageSize; foreign does not, so paginate deeply when needed.
 maxp=140 if kind=='foreign' else 20
 for p in range(1,maxp+1):
  try:r=page(sym,kind,p,2000)
  except Exception:
   time.sleep(.25);continue
  if not r:break
  fresh=0
  for x in r:
   z=parse(x,kind)
   if z and z['date'] not in seen:seen.add(z['date']);out.append(z);fresh+=1
  if fresh==0 or (kind!='foreign' and len(r)<2000):break
 return sorted(out,key=lambda x:x['date']), 'JSON_FALLBACK'
def one(sym):
 f,fs=fetch_kind(sym,'foreign');p,ps=fetch_kind(sym,'prop');d={}
 for x in f+p:d.setdefault(x['date'],{'date':x['date']}).update(x)
 rows=[d[k] for k in sorted(d)];return sym,rows,{'foreign':fs,'prop':ps,'foreignRows':len(f),'propRows':len(p)}
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
 symbols=syms();data={};cur={};sources={}
 with ThreadPoolExecutor(max_workers=14) as ex:
  fs={ex.submit(one,s):s for s in symbols}
  for i,f in enumerate(as_completed(fs),1):
   s,r,src=f.result();data[s]=r;sources[s]=src;c=current(r)
   if c:cur[s]=c
   if i%50==0:print(json.dumps({'flowSymbolsDone':i,'total':len(symbols)}))
 counts=sorted(len(x) for x in data.values());foreignCounts=sorted(x['foreignRows'] for x in sources.values());propCounts=sorted(x['propRows'] for x in sources.values());out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'source':'CafeF public historical export/JSON endpoints','start':'2018-01-01','symbols':data,'current':cur,'sourceAudit':sources,'summary':{'symbols':len(symbols),'symbolsWithFlow':sum(x>0 for x in counts),'symbols100plus':sum(x>=100 for x in counts),'symbols500plus':sum(x>=500 for x in counts),'medianRows':counts[len(counts)//2] if counts else 0,'p10Rows':counts[int(.1*(len(counts)-1))] if counts else 0,'foreignMedianRows':foreignCounts[len(foreignCounts)//2] if foreignCounts else 0,'propMedianRows':propCounts[len(propCounts)//2] if propCounts else 0,'foreignExportSymbols':sum(x['foreign']=='EXPORT_XLSX' for x in sources.values()),'propExportSymbols':sum(x['prop']=='EXPORT_XLSX' for x in sources.values())}}
 (ROOT/'data/flow-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps(out['summary'],ensure_ascii=False))
if __name__=='__main__':main()