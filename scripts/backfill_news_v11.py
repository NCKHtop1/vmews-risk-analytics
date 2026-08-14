import json,re,html,hashlib,time,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,date,timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));MANIFEST=ROOT/'data/hose-fallbacks/manifest.json';VERSION='VMEWS-NEWS-HISTORY-11.1.0'
WINDOWS=[('2018-01-01','2020-01-01'),('2020-01-01','2022-01-01'),('2022-01-01','2024-01-01'),('2024-01-01','2027-01-01')]
RUMOR=['tin đồn','đồn đoán','rộ tin','lan truyền','chưa xác nhận','chưa kiểm chứng','rumor'];CLAR=['bác bỏ','phủ nhận','đính chính','làm rõ','phản hồi tin đồn']
OFFICIAL=['hsx','hose','hnx','ssc','ủy ban chứng khoán','ubck','công bố thông tin'];TRUST=['cafef','vietstock','vnexpress','vneconomy','vietnambiz','baodautu','znews','dantri','dân trí','tuổi trẻ','tuoitre','laodong','lao động','bnews','ndh','nguoiquansat','người quan sát']
EVENTS={'EARNINGS':['lợi nhuận','doanh thu','kết quả kinh doanh','báo lỗ','lỗ ròng','biên lợi nhuận'],'REGULATORY':['khởi tố','điều tra','xử phạt','vi phạm','thanh tra','cảnh báo'],'CORPORATE_ACTION':['cổ tức','phát hành','quyền mua','chia tách','esop','cổ phiếu thưởng'],'OWNERSHIP':['cổ đông lớn','thoái vốn','đăng ký mua','đăng ký bán','chủ tịch','người nội bộ'],'FINANCING':['trái phiếu','nợ vay','đáo hạn','tín dụng','phát hành riêng lẻ'],'OPERATIONS_MA':['hợp đồng','trúng thầu','dự án','m&a','sáp nhập','mua lại','thoái vốn'],'ANALYST':['khuyến nghị','giá mục tiêu','nâng khuyến nghị','hạ khuyến nghị'],'MARKET_FLOW':['mua ròng','bán ròng','khối ngoại','tự doanh','room ngoại']}
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
    x=(title+' '+pub).lower()
    if any(k in x for k in CLAR):return 'CLARIFICATION'
    if stream=='RUMOR' and any(k in x for k in RUMOR):return 'RUMOR_UNVERIFIED'
    if any(k in x for k in OFFICIAL) or stream=='OFFICIAL' and any(k in pub.lower() for k in ['hsx','hose','ssc','ubck']):return 'OFFICIAL'
    return 'MAINSTREAM'
def quality(sc,pub):
    p=pub.lower()
    if sc=='OFFICIAL':return 1.
    if sc=='CLARIFICATION':return .95
    if sc=='RUMOR_UNVERIFIED':return .35
    return .9 if any(x in p for x in TRUST) else .62
def symbols():
    m=json.loads(MANIFEST.read_text(encoding='utf-8'));return sorted(s for s,r in (m.get('routes') or {}).items() if int((r or {}).get('rows') or 0)>=520)
def query_stream(stream):return ' "tin đồn"' if stream=='RUMOR' else ' "công bố thông tin"' if stream=='OFFICIAL' else ''
def fetch_once(sym,start,end,stream):
    query=f'"{sym}" "cổ phiếu"{query_stream(stream)} after:{start} before:{end}';u='https://news.google.com/rss/search?q='+quote_plus(query)+'&hl=vi&gl=VN&ceid=VN:vi'
    for attempt in range(3):
        try:
            if attempt:time.sleep(.4*(attempt+1))
            with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS-News-History/11'}),timeout=12) as r:root=ET.fromstring(r.read())
            items=root.findall('.//item')[:100];out=[]
            for it in items:
                title=clean(it.findtext('title'));d=pdate(clean(it.findtext('pubDate')));pub=publisher(title);low=norm(title)
                if not title or not d or not re.search(rf'(^| ){re.escape(sym.lower())}( |$)',low):continue
                sc=source_class(title,pub,stream);ev,mat=event(title);link=clean(it.findtext('link'));aid=hashlib.sha1((sym+'|'+d.isoformat()+'|'+low).encode()).hexdigest();out.append({'id':aid,'symbol':sym,'title':title,'link':link,'publishedAt':d.isoformat(),'publisher':pub,'stream':stream,'sourceClass':sc,'sourceQuality':quality(sc,pub),'event':ev,'materiality':mat})
            return len(items),out
        except:pass
    return 0,[]
def fetch(sym,start,end,stream,depth=0):
    n,out=fetch_once(sym,start,end,stream);a=date.fromisoformat(start);b=date.fromisoformat(end)
    # Google News RSS commonly caps a query near 100 results; split saturated windows recursively.
    if n>=95 and depth<6 and (b-a).days>45:
        mid=a+timedelta(days=(b-a).days//2);m=mid.isoformat();return fetch(sym,start,m,stream,depth+1)+fetch(sym,m,end,stream,depth+1)
    return out
def duplicate(x,chosen):
    a=norm(x['title']);sa=set(a.split())
    for y in chosen[-180:]:
        b=norm(y['title']);sb=set(b.split());j=len(sa&sb)/max(1,len(sa|sb))
        if j>=.82 or SequenceMatcher(None,a,b).ratio()>=.91:return True
    return False
def main():
    syms=symbols();jobs=[];raw={s:[] for s in syms}
    with ThreadPoolExecutor(max_workers=24) as ex:
        for s in syms:
            for a,b in WINDOWS:
                for stream in ('MAIN','OFFICIAL','RUMOR'):jobs.append(ex.submit(fetch,s,a,b,stream))
        for i,f in enumerate(as_completed(jobs),1):
            for x in f.result():raw[x['symbol']].append(x)
            if i%500==0:print(json.dumps({'baseQueriesDone':i,'baseQueries':len(jobs)}))
    out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'start':'2018-01-01','end':'2027-01-01','queryWindows':WINDOWS,'adaptiveSplitOnSaturation':True,'universe':len(syms),'symbols':{},'coverage':{}};total=0
    for s,a in raw.items():
        a.sort(key=lambda x:x['publishedAt']);chosen=[];seen=set()
        for x in a:
            if x['id'] in seen or duplicate(x,chosen):continue
            seen.add(x['id']);chosen.append(x)
        # Enough history for event inference without letting a few mega-caps dominate storage.
        if len(chosen)>240:
            special=[x for x in chosen if x['sourceClass']!='MAINSTREAM' or x['event']!='GENERAL'];general=[x for x in chosen if x not in special];slots=max(1,240-len(special));step=max(1,len(general)//slots);chosen=(special+general[::step])[:280];chosen.sort(key=lambda x:x['publishedAt'])
        total+=len(chosen);pubs=len(set(x['publisher'] for x in chosen));rum=sum(x['sourceClass']=='RUMOR_UNVERIFIED' for x in chosen);off=sum(x['sourceClass'] in {'OFFICIAL','CLARIFICATION'} for x in chosen);yrs=len(set(x['publishedAt'][:4] for x in chosen));out['symbols'][s]=chosen;out['coverage'][s]={'n':len(chosen),'publishers':pubs,'years':yrs,'officialOrClarification':off,'rumor':rum}
    counts=sorted(z['n'] for z in out['coverage'].values());out['summary']={'articles':total,'symbolsWithNews':sum(x>0 for x in counts),'symbols10plus':sum(x>=10 for x in counts),'symbols20plus':sum(x>=20 for x in counts),'medianPerSymbol':counts[len(counts)//2] if counts else 0,'p10PerSymbol':counts[int(.1*(len(counts)-1))] if counts else 0,'officialOrClarification':sum(z['officialOrClarification'] for z in out['coverage'].values()),'rumors':sum(z['rumor'] for z in out['coverage'].values())}
    (ROOT/'data/news-history-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps(out['summary'],ensure_ascii=False))
if __name__=='__main__':main()
