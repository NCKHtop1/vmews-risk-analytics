import json, re, html, pathlib, importlib.util
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

ROOT=pathlib.Path(__file__).resolve().parents[1]
core_path=ROOT/'api'/'stocks.py'
spec=importlib.util.spec_from_file_location('vmews_news_core',core_path)
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
SYMBOLS={s:core.NAMES.get(s,s) for s in core.UNIVERSE}
QUERY_GROUPS=['','(site:cafef.vn OR site:vietstock.vn)','(site:vnexpress.net OR site:vneconomy.vn OR site:nguoiquansat.vn)','(site:hsx.vn OR site:hnx.vn OR site:ssc.gov.vn)']
WINDOW_DAYS=540
MAX_PER_QUERY=25
MAX_USED=100
EVENTS={'Regulatory / legal':['khởi tố','điều tra','xử phạt','vi phạm','thanh tra','truy thu','fraud','investigation','penalty'],'Earnings':['lợi nhuận','doanh thu','kết quả kinh doanh','báo lỗ','lỗ ròng','earnings','profit','revenue'],'Ownership / governance':['cổ đông lớn','dragon capital','quỹ','thoái vốn','mua vào','bán ra','chủ tịch','tổng giám đốc','ownership'],'Capital / corporate action':['cổ tức','phát hành','thưởng cổ phiếu','quyền mua','chia tách','esop','dividend','issuance','split'],'Financing / leverage':['trái phiếu','nợ vay','thanh khoản','đáo hạn','tín dụng','bond','debt','liquidity'],'Operations / M&A':['hợp đồng','trúng thầu','dự án','m&a','sáp nhập','mua lại','mở rộng','contract','project','acquisition']}
MATERIAL_TERMS=['khởi tố','điều tra','xử phạt','báo lỗ','lỗ ròng','giảm mạnh','trái phiếu','đáo hạn','cổ đông lớn','thoái vốn','trúng thầu','m&a','phát hành','cổ tức','record profit','fraud','default','downgrade']
TRUSTED=['cafef','vietstock','vnexpress','vneconomy','tuổi trẻ','tuoi tre','znews','lao động','laodong','nguoi quan sat','người quan sát','ndh','baodautu','the investor']
OFFICIAL=['hsx','hose','hnx','ssc','ủy ban chứng khoán','uy ban chung khoan']
def clean(s): return re.sub(r'\s+',' ',html.unescape(s or '')).strip()
def norm(s): return re.sub(r'[^a-z0-9à-ỹ]+',' ',clean(s).lower()).strip()
def parse_date(s):
    try:
        dt=parsedate_to_datetime(s)
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:return None
def publisher(title):
    p=clean(title).rsplit(' - ',1);return p[1].strip() if len(p)==2 else 'Unknown'
def source_quality(pub):
    low=pub.lower()
    if any(x in low for x in OFFICIAL):return 1.0
    if any(x in low for x in TRUSTED):return .9
    return .65
def event_info(title):
    low=title.lower();best='General';hits=0
    for name,terms in EVENTS.items():
        n=sum(t in low for t in terms)
        if n>hits:best,hits=name,n
    return best,min(1.0,.35+.18*min(3,hits)+(.25 if any(t in low for t in MATERIAL_TERMS) else 0))
def relevance(sym,name,title):
    low=norm(title);symhit=re.search(rf'(^| ){re.escape(sym.lower())}( |$)',low) is not None;tokens=low.split();name_tokens=[x for x in norm(name).split() if len(x)>2];overlap=sum(t in tokens for t in name_tokens)/max(1,len(name_tokens))
    return 1.0 if symhit else .9 if overlap>=.65 else .72 if overlap>=.35 else .45
def noisy(title):
    low=title.lower().strip();return not low or low.startswith('untitled') or low.startswith('cw.') or 'chứng quyền' in low or 'covered warrant' in low
def fetch(sym,name,group,limit=MAX_PER_QUERY):
    q=(f'"{sym}" cổ phiếu "{name}" {group}').strip();url='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=vi&gl=VN&ceid=VN:vi';req=Request(url,headers={'User-Agent':'Mozilla/5.0 VMEWS-Research-News/5.0'})
    with urlopen(req,timeout=8) as r:root=ET.fromstring(r.read())
    out=[]
    for it in root.findall('.//item')[:limit]:
        title=clean(it.findtext('title'));published=clean(it.findtext('pubDate'));dt=parse_date(published);pub=publisher(title);evt,mat=event_info(title);out.append({'symbol':sym,'title':title,'link':clean(it.findtext('link')),'published':published,'publishedTs':dt.timestamp() if dt else 0,'publisher':pub,'sourceQuality':source_quality(pub),'event':evt,'materiality':mat,'relevance':relevance(sym,name,title),'query':q})
    return out
def near_dup(key,seen_keys):
    toks=set(key.split())
    for old in seen_keys[-60:]:
        ot=set(old.split());jac=len(toks&ot)/max(1,len(toks|ot))
        if jac>=.82 or SequenceMatcher(None,key,old).ratio()>=.9:return True
    return False
def coverage_grade(used,pubs,r180):
    if used>=35 and pubs>=7 and r180>=12:return 'STRONG'
    if used>=18 and pubs>=5 and r180>=6:return 'MODERATE'
    if used>=6 and pubs>=3:return 'LIMITED'
    return 'THIN'
def main():
    now=datetime.now(timezone.utc);cutoff=(now-timedelta(days=WINDOW_DAYS)).timestamp();c90=(now-timedelta(days=90)).timestamp();c180=(now-timedelta(days=180)).timestamp();payload={'generatedAt':now.isoformat(),'windowDays':WINDOW_DAYS,'method':'full-universe Google News RSS; grouped publisher and official-source queries; recency, relevance, source-quality, event taxonomy and fuzzy deduplication','symbols':{s:[] for s in SYMBOLS},'coverage':{}};raw={s:[] for s in SYMBOLS};jobs=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        for sym,name in SYMBOLS.items():
            for group in QUERY_GROUPS:jobs.append(ex.submit(fetch,sym,name,group))
        for fut in as_completed(jobs):
            try:
                for row in fut.result():raw[row['symbol']].append(row)
            except Exception:pass
    for sym,rows in raw.items():
        collected=len(rows);windowed=[x for x in rows if (not x.get('publishedTs')) or x['publishedTs']>=cutoff];windowed=[x for x in windowed if not noisy(x.get('title',''))];relevant=[x for x in windowed if x.get('relevance',0)>=.70];relevant.sort(key=lambda z:z.get('publishedTs',0),reverse=True);seen=[];uniq=[]
        for x in relevant:
            key=norm(x['title'])
            if not key or near_dup(key,seen):continue
            seen.append(key);uniq.append(x)
        used=uniq[:MAX_USED];material=sum(1 for x in used if x.get('materiality',0)>=.65 or x.get('event')!='General');pubs=len(set(x.get('publisher','Unknown') for x in used));official=sum(1 for x in used if x.get('sourceQuality')==1.0);r90=sum(1 for x in used if x.get('publishedTs',0)>=c90);r180=sum(1 for x in used if x.get('publishedTs',0)>=c180);final=[]
        for x in used:
            y=dict(x);y.pop('symbol',None);y.pop('publishedTs',None);final.append(y)
        payload['symbols'][sym]=final;payload['coverage'][sym]={'collected':collected,'windowed':len(windowed),'relevant':len(relevant),'unique':len(uniq),'used':len(final),'recent90':r90,'recent180':r180,'material':material,'publishers':pubs,'official':official,'coverageGrade':coverage_grade(len(final),pubs,r180)}
    p=ROOT/'data'/'research-news.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
