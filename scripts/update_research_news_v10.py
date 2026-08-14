import json,re,html,pathlib,importlib.util,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('core',ROOT/'api/stocks.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
VERSION='VMEWS-NEWS-11.0.0';WINDOW_DAYS=1095;MAX_PER_SYMBOL=180
EVENTS={
 'REGULATORY':['khởi tố','điều tra','xử phạt','vi phạm','thanh tra','cảnh báo','kiểm soát'],
 'EARNINGS':['lợi nhuận','doanh thu','kết quả kinh doanh','báo lỗ','lỗ ròng','biên lợi nhuận','kế hoạch kinh doanh'],
 'OWNERSHIP':['cổ đông lớn','thoái vốn','mua vào','bán ra','chủ tịch','người nội bộ'],
 'CORPORATE_ACTION':['cổ tức','phát hành','quyền mua','chia tách','esop','cổ phiếu thưởng'],
 'FINANCING':['trái phiếu','nợ vay','đáo hạn','tín dụng','tăng vốn'],
 'OPERATIONS_MA':['hợp đồng','trúng thầu','dự án','m&a','sáp nhập','mua lại','đầu tư'],
 'ANALYST':['khuyến nghị','giá mục tiêu','nâng khuyến nghị','hạ khuyến nghị'],
 'MARKET_FLOW':['khối ngoại','mua ròng','bán ròng','tự doanh','thanh khoản']
}
RUMOR=['tin đồn','đồn đoán','rộ tin','lan truyền','chưa xác nhận','chưa kiểm chứng'];CLARIFY=['bác bỏ','phủ nhận','đính chính','phản hồi tin đồn','xác nhận thông tin']
TRUSTED=['cafef','vietstock','vnexpress','vneconomy','tuổi trẻ','tuoi tre','znews','lao động','laodong','người quan sát','nguoi quan sat','baodautu','vietnambiz','dân trí','dan tri','bnews','nhadautu','mekong asean','the investor']
OFFICIAL=['hsx','hose','hnx','ssc','ủy ban chứng khoán','uy ban chung khoan','công bố thông tin','cong bo thong tin']

def clean(s):return re.sub(r'\s+',' ',html.unescape(s or '')).strip()
def norm(s):return re.sub(r'[^a-z0-9à-ỹ]+',' ',clean(s).lower()).strip()
def parsed(s):
 try:
  d=parsedate_to_datetime(s);return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
 except:return None
def pub(t):
 p=clean(t).rsplit(' - ',1);return p[1].strip() if len(p)==2 else 'Unknown'
def source_class(t,p):
 x=(t+' '+p).lower()
 if any(k in x for k in CLARIFY):return 'CLARIFICATION'
 if any(k in x for k in RUMOR):return 'RUMOR_UNVERIFIED'
 if any(k in x for k in OFFICIAL):return 'OFFICIAL'
 return 'MAINSTREAM'
def event(t):
 x=t.lower();best='GENERAL';hits=0
 for k,terms in EVENTS.items():
  n=sum(q in x for q in terms)
  if n>hits:best,hits=k,n
 return best,min(1,.35+.18*min(3,hits))
def universe():
 out=dict(core.NAMES);p=ROOT/'data/hose-fallbacks/manifest.json'
 if p.exists():
  m=json.loads(p.read_text(encoding='utf-8'))
  for s,r in (m.get('routes') or {}).items():
   if int((r or {}).get('rows') or 0)>=520:out.setdefault(s,s)
 return out
def rel(sym,name,title):
 x=norm(title)
 if re.search(rf'(^| ){re.escape(sym.lower())}( |$)',x):return 1.
 toks=[q for q in norm(name).split() if len(q)>2 and q not in {'corp','group','bank','cong','company','joint','stock'}]
 if not toks:return .3
 o=sum(q in x.split() for q in toks)/len(toks);return .95 if o>=.75 else .85 if o>=.55 else .7 if o>=.4 else .3

def query_families(sym,name):
 q=[
  ('ticker',f'"{sym}" cổ phiếu'),
  ('event',f'"{sym}" lợi nhuận OR doanh thu OR cổ tức OR phát hành OR dự án OR trái phiếu OR xử phạt'),
  ('flow',f'"{sym}" khối ngoại OR mua ròng OR bán ròng OR tự doanh'),
  ('rumor',f'"{sym}" tin đồn OR đính chính OR bác bỏ'),
  ('official',f'"{sym}" (site:hsx.vn OR site:hnx.vn OR site:ssc.gov.vn)')
 ]
 nn=clean(name)
 if nn and norm(nn)!=norm(sym):q.append(('company',f'"{nn}" chứng khoán OR cổ phiếu'))
 return q

def fetch_query(sym,name,family,q):
 u='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=vi&gl=VN&ceid=VN:vi'
 for attempt in range(2):
  try:
   if attempt:time.sleep(.7)
   with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS-News/11'}),timeout=10) as r:root=ET.fromstring(r.read())
   out=[]
   for it in root.findall('.//item')[:24]:
    t=clean(it.findtext('title'));d=parsed(clean(it.findtext('pubDate')));p=pub(t);sc=source_class(t,p);ev,mat=event(t)
    quality=1. if sc in {'OFFICIAL','CLARIFICATION'} else (.92 if any(k in p.lower() for k in TRUSTED) else .42 if sc=='RUMOR_UNVERIFIED' else .68)
    out.append({'symbol':sym,'title':t,'link':clean(it.findtext('link')),'published':clean(it.findtext('pubDate')),'ts':d.timestamp() if d else 0,'publisher':p,'sourceClass':sc,'sourceQuality':quality,'event':ev,'materiality':mat,'relevance':rel(sym,name,t),'queryFamily':family})
   return out
  except Exception:pass
 return []

def dup(k,seen):
 a=set(k.split())
 for old in seen[-160:]:
  b=set(old.split());u=len(a|b)
  if (len(a&b)/max(1,u)>=.80) or SequenceMatcher(None,k,old).ratio()>=.89:return True
 return False

def previous():
 p=ROOT/'data/research-news-v10.json'
 try:
  z=json.loads(p.read_text(encoding='utf-8')) if p.exists() and p.stat().st_size>10 else {}
  return z if isinstance(z,dict) else {}
 except:return {}

def main():
 U=universe();now=datetime.now(timezone.utc);cut=(now-timedelta(days=WINDOW_DAYS)).timestamp();c90=(now-timedelta(days=90)).timestamp();raw={s:[] for s in U};old=previous();jobs=[]
 # Accumulate prior immutable discoveries before refreshing. This thickens the corpus without changing original publication times.
 for s,items in (old.get('symbols') or {}).items():
  if s not in raw:continue
  for x in items or []:
   d=parsed(x.get('published',''));y={'symbol':s,**x,'ts':d.timestamp() if d else 0};raw[s].append(y)
 with ThreadPoolExecutor(max_workers=18) as ex:
  for s,n in U.items():
   for fam,q in query_families(s,n):jobs.append(ex.submit(fetch_query,s,n,fam,q))
  for f in as_completed(jobs):
   for x in f.result():raw[x['symbol']].append(x)
 out={'version':VERSION,'generatedAt':now.isoformat(),'windowDays':WINDOW_DAYS,'universe':len(U),'symbols':{},'coverage':{},'method':'Accumulating multi-query Google News index plus official-domain discovery queries; immutable publication time and first-seen time; entity relevance, deduplication, source class and event taxonomy.'}
 old_first={}
 for s,items in (old.get('symbols') or {}).items():
  for x in items or []:
   k=(clean(x.get('link')),norm(x.get('title')));old_first[(s,k)]=x.get('firstSeenAt') or old.get('generatedAt')
 for s,rows in raw.items():
  rows=[x for x in rows if x.get('ts',0)>=cut and float(x.get('relevance') or 0)>=.70];rows.sort(key=lambda x:x.get('ts',0),reverse=True);seen=[];use=[]
  for x in rows:
   k=norm(x.get('title'))
   if not k or dup(k,seen):continue
   seen.append(k);x['firstSeenAt']=old_first.get((s,(clean(x.get('link')),k))) or now.isoformat();use.append(x)
   if len(use)>=MAX_PER_SYMBOL:break
  pubs=len(set(x.get('publisher') for x in use if x.get('publisher')));recent=sum(x.get('ts',0)>=c90 for x in use);classes={k:sum(x.get('sourceClass')==k for x in use) for k in ['OFFICIAL','MAINSTREAM','RUMOR_UNVERIFIED','CLARIFICATION']};events=len(set(x.get('event') for x in use if x.get('event')));families=len(set(x.get('queryFamily') for x in use if x.get('queryFamily')));final=[]
  for x in use:
   y=dict(x);y.pop('symbol',None);y.pop('ts',None);final.append(y)
  grade='STRONG' if len(final)>=40 and pubs>=8 and recent>=10 and events>=4 else 'MODERATE' if len(final)>=20 and pubs>=5 and events>=3 else 'LIMITED' if len(final)>=8 else 'THIN'
  out['symbols'][s]=final;out['coverage'][s]={'used':len(final),'recent90':recent,'publishers':pubs,'eventTypes':events,'queryFamilies':families,'classes':classes,'coverageGrade':grade}
 (ROOT/'data/research-news-v10.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 cov=list(out['coverage'].values());print(json.dumps({'version':VERSION,'universe':len(U),'symbolsWithNews':sum(x['used']>0 for x in cov),'symbolsModeratePlus':sum(x['coverageGrade'] in {'MODERATE','STRONG'} for x in cov),'totalItems':sum(x['used'] for x in cov),'FRT':out['coverage'].get('FRT')},ensure_ascii=False))
if __name__=='__main__':main()
