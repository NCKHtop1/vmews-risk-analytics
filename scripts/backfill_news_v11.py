import json,re,html,hashlib,time,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,date,timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));MANIFEST=ROOT/'data/hose-fallbacks/manifest.json';VERSION='VMEWS-NEWS-HISTORY-11.3.0'
WINDOWS=[('2018-01-01','2020-01-01'),('2020-01-01','2022-01-01'),('2022-01-01','2024-01-01'),('2024-01-01','2027-01-01')]
SEARCHES=[('MAIN','cổ phiếu'),('MAIN','chứng khoán'),('MAIN','lợi nhuận doanh thu'),('MAIN','cổ tức phát hành dự án'),('OFFICIAL','công bố thông tin'),('RUMOR','tin đồn')]
RUMOR=['tin đồn','đồn đoán','rộ tin','lan truyền','chưa xác nhận','chưa kiểm chứng','rumor'];CLAR=['bác bỏ','phủ nhận','đính chính','làm rõ','phản hồi tin đồn']
OFFICIAL_PUB=['sở giao dịch chứng khoán','ho chi minh stock exchange','hose','hsx.vn','ủy ban chứng khoán','state securities commission','ubck','ssc.gov.vn'];TRUST=['cafef','vietstock','vnexpress','vneconomy','vietnambiz','baodautu','znews','dantri','dân trí','tuổi trẻ','tuoitre','laodong','lao động','bnews','ndh','nguoiquansat','người quan sát','nhip song kinh doanh','markettimes']
EVENTS={'EARNINGS':['lợi nhuận','doanh thu','kết quả kinh doanh','báo lỗ','lỗ ròng','biên lợi nhuận'],'REGULATORY':['khởi tố','điều tra','xử phạt','vi phạm','thanh tra','cảnh báo'],'CORPORATE_ACTION':['cổ tức','phát hành','quyền mua','chia tách','esop','cổ phiếu thưởng'],'OWNERSHIP':['cổ đông lớn','thoái vốn','đăng ký mua','đăng ký bán','chủ tịch','người nội bộ'],'FINANCING':['trái phiếu','nợ vay','đáo hạn','tín dụng','phát hành riêng lẻ'],'OPERATIONS_MA':['hợp đồng','trúng thầu','dự án','m&a','sáp nhập','mua lại','thoái vốn'],'ANALYST':['khuyến nghị','giá mục tiêu','nâng khuyến nghị','hạ khuyến nghị'],'MARKET_FLOW':['mua ròng','bán ròng','khối ngoại','tự doanh','room ngoại']}
STOP={'cong','ty','co','phan','tap','doan','thuong','mai','dich','vu','joint','stock','company','corporation','corp','group','holdings','holding','vietnam','viet','nam','ngan','hang','bank','investment','development'}
def clean(s):return re.sub(r'\s+',' ',html.unescape(str(s or ''))).strip()
def norm(s):return re.sub(r'[^a-z0-9à-ỹ]+',' ',clean(s).lower()).strip()
def pdate(s):
    try:return parsedate_to_datetime(s).astimezone(timezone.utc)
    except:return None
def publisher(t):
    p=clean(t).rsplit(' - ',1);return p[-1].strip() if len(p)>1 else 'Unknown'
def event(title):
    x=title.lower();best='GENERAL';score=0
    for k,terms in EVENTS.items():
        n=sum(t in x for t in terms)
        if n>score:best,score=k,n
    return best,min(1.,.35+.18*min(3,score))
def source_class(title,pub,stream):
    x=title.lower();p=pub.lower()
    if any(k in x for k in CLAR):return 'CLARIFICATION'
    if stream=='RUMOR' and any(k in x for k in RUMOR):return 'RUMOR_UNVERIFIED'
    if any(k in p for k in OFFICIAL_PUB):return 'OFFICIAL'
    return 'MAINSTREAM'
def quality(sc,pub):
    p=pub.lower()
    if sc=='OFFICIAL':return 1.
    if sc=='CLARIFICATION':return .95
    if sc=='RUMOR_UNVERIFIED':return .35
    return .9 if any(x in p for x in TRUST) else .62
def universe():
    m=json.loads(MANIFEST.read_text(encoding='utf-8'));syms=sorted(s for s,r in (m.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520);names={s:s for s in syms}
    try:
        from vnstock import Listing
        df=Listing(source='VCI').symbols_by_exchange(show_log=False);cols={str(c).lower():c for c in df.columns};sc=cols.get('symbol');nc=cols.get('organ_name') or cols.get('organ_short_name')
        if sc is not None and nc is not None:
            for _,r in df.iterrows():
                s=str(r.get(sc) or '').upper().strip()
                if s in names and str(r.get(nc) or '').strip():names[s]=str(r.get(nc)).strip()
    except Exception:pass
    return syms,names
def name_tokens(name):
    x=norm(name);t=[q for q in x.split() if len(q)>=4 and q not in STOP and not q.isdigit()]
    return t[:8]
def entity_match(sym,name,title):
    low=norm(title);tok=set(low.split());s=sym.lower()
    if s in tok:return True
    nt=name_tokens(name)
    if not nt:return False
    hits=sum(q in tok or q in low for q in nt)
    if len(nt)==1:return len(nt[0])>=6 and hits==1
    return hits>=min(2,len(nt))
def query_for(sym,name,mode):
    nt=name_tokens(name);alias=' '.join(nt[:4])
    entity=f'"{sym}"'
    if alias and alias!=sym.lower():entity=f'("{sym}" OR "{alias}")'
    if mode=='lợi nhuận doanh thu':ctx='("lợi nhuận" OR "doanh thu" OR "kết quả kinh doanh")'
    elif mode=='cổ tức phát hành dự án':ctx='("cổ tức" OR "phát hành" OR "dự án" OR "trúng thầu")'
    else:ctx=f'"{mode}"'
    return f'{entity} {ctx}'
def fetch_once(sym,name,start,end,stream,mode):
    query=f'{query_for(sym,name,mode)} after:{start} before:{end}';u='https://news.google.com/rss/search?q='+quote_plus(query)+'&hl=vi&gl=VN&ceid=VN:vi'
    for attempt in range(3):
        try:
            if attempt:time.sleep(.35*(attempt+1))
            with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS-News-History/11.3'}),timeout=12) as r:root=ET.fromstring(r.read())
            items=root.findall('.//item')[:100];out=[]
            for it in items:
                title=clean(it.findtext('title'));d=pdate(clean(it.findtext('pubDate')));pub=publisher(title)
                if not title or not d or not entity_match(sym,name,title):continue
                sc=source_class(title,pub,stream);ev,mat=event(title);link=clean(it.findtext('link'));low=norm(title);aid=hashlib.sha1((sym+'|'+d.isoformat()+'|'+low).encode()).hexdigest();out.append({'id':aid,'symbol':sym,'title':title,'link':link,'publishedAt':d.isoformat(),'publisher':pub,'stream':stream,'searchMode':mode,'sourceClass':sc,'sourceQuality':quality(sc,pub),'event':ev,'materiality':mat})
            return len(items),out
        except:pass
    return 0,[]
def fetch(sym,name,start,end,stream,mode,depth=0):
    n,out=fetch_once(sym,name,start,end,stream,mode);a=date.fromisoformat(start);b=date.fromisoformat(end)
    if n>=95 and depth<6 and (b-a).days>45:
        mid=a+timedelta(days=(b-a).days//2);m=mid.isoformat();return fetch(sym,name,start,m,stream,mode,depth+1)+fetch(sym,name,m,end,stream,mode,depth+1)
    return out
def duplicate(x,chosen):
    a=norm(x['title']);sa=set(a.split())
    for y in chosen[-220:]:
        b=norm(y['title']);sb=set(b.split());j=len(sa&sb)/max(1,len(sa|sb))
        if j>=.82 or SequenceMatcher(None,a,b).ratio()>=.91:return True
    return False
def main():
    syms,names=universe();jobs=[];raw={s:[] for s in syms}
    with ThreadPoolExecutor(max_workers=28) as ex:
        for s in syms:
            for a,b in WINDOWS:
                for stream,mode in SEARCHES:jobs.append(ex.submit(fetch,s,names.get(s,s),a,b,stream,mode))
        for i,f in enumerate(as_completed(jobs),1):
            try:rows=f.result()
            except Exception:rows=[]
            for x in rows:raw[x['symbol']].append(x)
            if i%750==0:print(json.dumps({'baseQueriesDone':i,'baseQueries':len(jobs)}))
    out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'start':'2018-01-01','end':'2027-01-01','queryWindows':WINDOWS,'searchModes':SEARCHES,'adaptiveSplitOnSaturation':True,'entityResolution':'ticker token OR distinctive VCI company-name tokens; duplicates removed before event study','classificationNote':'OFFICIAL is assigned from publisher identity; disclosure-search articles from mainstream publishers remain MAINSTREAM.','universe':len(syms),'symbols':{},'coverage':{}};total=0
    for s,a in raw.items():
        a.sort(key=lambda x:x['publishedAt']);chosen=[];seen=set()
        for x in a:
            if x['id'] in seen or duplicate(x,chosen):continue
            seen.add(x['id']);chosen.append(x)
        if len(chosen)>320:
            special=[x for x in chosen if x['sourceClass']!='MAINSTREAM' or x['event']!='GENERAL'];general=[x for x in chosen if x not in special];slots=max(1,320-len(special));step=max(1,len(general)//slots);chosen=(special+general[::step])[:360];chosen.sort(key=lambda x:x['publishedAt'])
        total+=len(chosen);pubs=len(set(x['publisher'] for x in chosen));rum=sum(x['sourceClass']=='RUMOR_UNVERIFIED' for x in chosen);off=sum(x['sourceClass']=='OFFICIAL' for x in chosen);clar=sum(x['sourceClass']=='CLARIFICATION' for x in chosen);yrs=len(set(x['publishedAt'][:4] for x in chosen));out['symbols'][s]=chosen;out['coverage'][s]={'n':len(chosen),'publishers':pubs,'years':yrs,'official':off,'clarification':clar,'rumor':rum}
    counts=sorted(z['n'] for z in out['coverage'].values());out['summary']={'articles':total,'symbolsWithNews':sum(x>0 for x in counts),'symbols10plus':sum(x>=10 for x in counts),'symbols20plus':sum(x>=20 for x in counts),'medianPerSymbol':counts[len(counts)//2] if counts else 0,'p10PerSymbol':counts[int(.1*(len(counts)-1))] if counts else 0,'official':sum(z['official'] for z in out['coverage'].values()),'clarifications':sum(z['clarification'] for z in out['coverage'].values()),'rumors':sum(z['rumor'] for z in out['coverage'].values())}
    (ROOT/'data/news-history-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps(out['summary'],ensure_ascii=False))
if __name__=='__main__':main()
