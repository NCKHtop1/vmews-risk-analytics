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
EVENTS={'REGULATORY':['khởi tố','điều tra','xử phạt','vi phạm','thanh tra'],'EARNINGS':['lợi nhuận','doanh thu','kết quả kinh doanh','báo lỗ','lỗ ròng'],'OWNERSHIP':['cổ đông lớn','thoái vốn','mua vào','bán ra','chủ tịch'],'CORPORATE_ACTION':['cổ tức','phát hành','quyền mua','chia tách','esop'],'FINANCING':['trái phiếu','nợ vay','đáo hạn','tín dụng'],'OPERATIONS_MA':['hợp đồng','trúng thầu','dự án','m&a','sáp nhập','mua lại'],'ANALYST':['khuyến nghị','giá mục tiêu','nâng khuyến nghị','hạ khuyến nghị']}
RUMOR=['tin đồn','đồn đoán','rộ tin','lan truyền','chưa xác nhận','chưa kiểm chứng'];CLARIFY=['bác bỏ','phủ nhận','đính chính','phản hồi tin đồn']
TRUSTED=['cafef','vietstock','vnexpress','vneconomy','tuổi trẻ','tuoi tre','znews','lao động','laodong','người quan sát','nguoi quan sat','baodautu','vietnambiz','dân trí','dan tri'];OFFICIAL=['hsx','hose','hnx','ssc','ủy ban chứng khoán','uy ban chung khoan']
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
 if any(k in x for k in OFFICIAL):return 'OFFICIAL'
 if any(k in x for k in CLARIFY):return 'CLARIFICATION'
 if any(k in x for k in RUMOR):return 'RUMOR_UNVERIFIED'
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
 toks=[q for q in norm(name).split() if len(q)>2 and q not in {'corp','group','bank'}]
 if not toks:return .3
 o=sum(q in x.split() for q in toks)/len(toks);return .9 if o>=.65 else .7 if o>=.45 else .3
def fetch(sym,name,rumor=False):
 extra=' "tin đồn"' if rumor else '';q=f'"{sym}" cổ phiếu{extra}';u='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=vi&gl=VN&ceid=VN:vi'
 for attempt in range(2):
  try:
   if attempt:time.sleep(1)
   with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS-News/10'}),timeout=9) as r:root=ET.fromstring(r.read())
   out=[]
   for it in root.findall('.//item')[:18]:
    t=clean(it.findtext('title'));d=parsed(clean(it.findtext('pubDate')));p=pub(t);sc=source_class(t,p);ev,mat=event(t);quality=1. if sc=='OFFICIAL' else (.9 if any(k in p.lower() for k in TRUSTED) else .45 if sc=='RUMOR_UNVERIFIED' else .65)
    out.append({'symbol':sym,'title':t,'link':clean(it.findtext('link')),'published':clean(it.findtext('pubDate')),'ts':d.timestamp() if d else 0,'publisher':p,'sourceClass':sc,'sourceQuality':quality,'event':ev,'materiality':mat,'relevance':rel(sym,name,t)})
   return out
  except:pass
 return []
def dup(k,seen):
 a=set(k.split())
 for old in seen[-60:]:
  b=set(old.split())
  if len(a&b)/max(1,len(a|b))>=.82 or SequenceMatcher(None,k,old).ratio()>=.9:return True
 return False
def main():
 U=universe();now=datetime.now(timezone.utc);cut=(now-timedelta(days=540)).timestamp();c90=(now-timedelta(days=90)).timestamp();raw={s:[] for s in U};jobs=[]
 with ThreadPoolExecutor(max_workers=10) as ex:
  for s,n in U.items():jobs.extend([ex.submit(fetch,s,n,False),ex.submit(fetch,s,n,True)])
  for f in as_completed(jobs):
   for x in f.result():raw[x['symbol']].append(x)
 out={'version':'VMEWS-NEWS-10.0.0','generatedAt':now.isoformat(),'windowDays':540,'universe':len(U),'symbols':{},'coverage':{}}
 for s,rows in raw.items():
  rows=[x for x in rows if x['ts']>=cut and x['relevance']>=.70];rows.sort(key=lambda x:x['ts'],reverse=True);seen=[];use=[]
  for x in rows:
   k=norm(x['title'])
   if not k or dup(k,seen):continue
   seen.append(k);use.append(x)
   if len(use)>=80:break
  pubs=len(set(x['publisher'] for x in use));recent=sum(x['ts']>=c90 for x in use);classes={k:sum(x['sourceClass']==k for x in use) for k in ['OFFICIAL','MAINSTREAM','RUMOR_UNVERIFIED','CLARIFICATION']};final=[]
  for x in use:y=dict(x);y.pop('symbol');y.pop('ts');final.append(y)
  out['symbols'][s]=final;out['coverage'][s]={'used':len(final),'recent90':recent,'publishers':pubs,'classes':classes,'coverageGrade':'STRONG' if len(final)>=30 and pubs>=6 and recent>=10 else 'MODERATE' if len(final)>=15 and pubs>=4 else 'LIMITED' if len(final)>=5 else 'THIN'}
 (ROOT/'data/research-news-v10.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'version':out['version'],'universe':len(U),'FRT':out['coverage'].get('FRT')},ensure_ascii=False))
if __name__=='__main__':main()
