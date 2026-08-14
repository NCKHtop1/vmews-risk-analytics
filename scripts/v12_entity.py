import copy
import re
import unicodedata
from collections import Counter,defaultdict

STOP={
 'cong','company','corporation','corp','ctcp','ty','phan','tap','doan','tong','joint','stock','group','holdings','holding','vietnam','viet','nam','ngan','hang','bank','investment','development','tmcp','mot','thanh','vien','thuong','mai','dich','vu','saigon','noi','minh','phat','trien','xay','dung','dau','kinh','doanh','van','tai'
}
FINANCE_CTX={
 'co phieu','chung khoan','ma co phieu','hose','hsx','hnx','upcom','niem yet','co dong','loi nhuan','doanh thu','co tuc','phat hanh','trai phieu','mua rong','ban rong','khoi ngoai','tu doanh','ket qua kinh doanh','dai hoi co dong','room ngoai','gia muc tieu','khuyen nghi','esop','m a','sap nhap','thoai von','giao dich','von hoa','thi gia','bctc','bao cao tai chinh'
}
EVENT_CTX={'loi nhuan','doanh thu','co tuc','phat hanh','trung thau','du an','xu phat','dieu tra','khoi to','dang ky mua','dang ky ban','trai phieu','no vay','mua lai','sap nhap','khuyen nghi','gia muc tieu','ke hoach','hop dong','tai co cau','chuyen nhuong','dau tu','tang truong'}
AMBIGUOUS={'HCM','CDC','COM','GTA','THG','VIP','FIT','NHA'}
COLLISIONS={
 'HCM':(r'\btp\s*hcm\b',r'\bthanh\s*pho\s*hcm\b',r'\bho\s*chi\s*minh\s*city\b'),
 'CDC':(r'\bcdc\s+home\b',r'\bcenters?\s+for\s+disease\b',r'\bcenter\s+for\s+disease\b',r'\bcdc\s+(ha\s+giang|quang\s+ninh|khanh\s+hoa|binh\s+thuan|lam\s+dong|my)\b'),
 'GTA':(r'\bgta\s*[456]\b',r'\bgrand\s+theft\s+auto\b'),
 'COM':(r'\.com\b',r'\bdot\s+com\b'),
 'THG':(r'\bthg\s+\d{1,2}\b',),
 'VIP':(r'\broom\s+vip\b',r'\bnhom\s+vip\b',r'\bkhach\s+vip\b',r'\bve\s+vip\b',r'\bgoi\s+vip\b'),
 'FIT':(r'\bgia\s+fit\b',r'\bfeed\s+in\s+tariff\b',r'\bcong\s+cu\s+khuyen\s+nghi\s+fit\b'),
 'NHA':(r'\bnha\s+trang\b',r'\bnha\s+dau\s+tu\b',r'\bnha\s+may\b',r'\bnha\s+o\b')
}
SPECIAL_OTHER_ENTITY={'FPT':(r'\bfpt\s+retail\b',)}

def ascii_text(s):
    x=str(s or '').replace('đ','d').replace('Đ','D')
    return unicodedata.normalize('NFKD',x).encode('ascii','ignore').decode().lower()

def norm(s):
    return re.sub(r'[^a-z0-9]+',' ',ascii_text(s)).strip()

def company_name_map(market_scan):
    out={}
    for x in (market_scan or {}).get('ranking',[]):
        s=str(x.get('symbol') or '').upper().strip();name=str(x.get('name') or '').strip()
        if s and name:out[s]=name
    return out

def name_tokens(name):
    toks=[]
    for x in norm(name).split():
        if len(x)>=5 and x not in STOP and not x.isdigit():toks.append(x)
    return list(dict.fromkeys(toks))[:10]

def _explicit_ticker(symbol,raw_text):
    s=re.escape(symbol.lower());patterns=[
        rf'\(\s*{s}\s*\)',rf'\[\s*{s}\s*\]',rf'\bma\s+(?:co\s+phieu\s+)?{s}\b',rf'\bco\s+phieu\s+{s}\b',rf'\b(?:hose|hsx|hnx|upcom)\s*[:\-]?\s*{s}\b',rf'^\s*{s}\s*[:\-–—]'
    ]
    return any(re.search(p,raw_text) for p in patterns)

def _brand_phrase(symbol,text):
    s=re.escape(symbol.lower())
    if re.search(rf'\b{s}\s+(?:holdings?|group|corp|corporation|bank|securities|retail|land|logistics|shipping)\b',text):return True
    if symbol=='GAS' and re.search(r'\bpv\s+gas\b',text):return True
    if symbol=='FIT' and re.search(r'\bf\s*i\s*t\b|\bfit\s+group\b',text):return True
    return False

def entity_relevance(symbol,name,title):
    symbol=str(symbol or '').upper().strip();raw=ascii_text(title);text=norm(title);tok=set(text.split());nt=name_tokens(name);ticker=symbol.lower()
    explicit=_explicit_ticker(symbol,raw);collision=any(re.search(p,text) for p in COLLISIONS.get(symbol,()));other_entity=any(re.search(p,text) for p in SPECIAL_OTHER_ENTITY.get(symbol,()))
    name_hits=[x for x in nt if x in tok]
    strong_name=(len(name_hits)>=2 and all(len(x)>=5 for x in name_hits[:2])) or (len(name_hits)>=1 and len(name_hits[0])>=8)
    brand=_brand_phrase(symbol,text);ctx=any(x in text for x in FINANCE_CTX);event_ctx=any(x in text for x in EVENT_CTX);ticker_token=ticker in tok
    if other_entity and not explicit:return False,0.0,'OTHER_LISTED_ENTITY_COLLISION'
    if collision:return False,0.0,'AMBIGUOUS_COLLISION'
    if explicit:return True,1.0,'EXPLICIT_TICKER'
    if strong_name:return True,min(.98,.76+.07*len(name_hits)),'COMPANY_NAME'
    if brand:return True,.90,'COMPANY_BRAND'
    if symbol in AMBIGUOUS:return False,0.0,'AMBIGUOUS_REQUIRES_EXPLICIT_ENTITY'
    if ticker_token and (ctx or event_ctx):return True,.80,'TICKER_FINANCE_EVENT_CONTEXT'
    if ticker_token and re.search(rf'^\s*{re.escape(ticker)}\b',text):return True,.72,'TICKER_TITLE_LEAD'
    return False,.0,'INSUFFICIENT_ENTITY_EVIDENCE'

def filter_sentiment_entities(sentiment,market_scan,eligible_symbols=None):
    out=copy.deepcopy(sentiment);names=company_name_map(market_scan);allowed=set(eligible_symbols or (out.get('symbols') or {}).keys());accepted=rejected=0;reason=Counter();per_symbol={};examples=defaultdict(list);methods=Counter();clean_symbols={}
    for symbol,z in (out.get('symbols') or {}).items():
        if symbol not in allowed:continue
        kept=[];rej=0
        for x in z.get('items') or []:
            ok,confidence,method=entity_relevance(symbol,names.get(symbol,''),x.get('title'))
            if ok:
                y=dict(x);y['entityConfidence']=confidence;y['entityMethod']=method;kept.append(y);accepted+=1;methods[method]+=1
            else:
                rejected+=1;rej+=1;reason[method]+=1
                if len(examples[symbol])<4:examples[symbol].append({'title':x.get('title'),'reason':method})
        cnt={'POS':0,'NEU':0,'NEG':0};sw=ss=0.0
        for x in kept:
            lab=str(x.get('label') or 'NEU').upper();cnt[lab]=cnt.get(lab,0)+1;v=1 if lab=='POS' else -1 if lab=='NEG' else 0;w=max(.01,float(x.get('weight') or .01));ss+=w*v;sw+=w
        clean_symbols[symbol]={**z,'n':len(kept),'counts':cnt,'signed':ss/sw if sw else 0.0,'items':kept}
        per_symbol[symbol]={'input':len(z.get('items') or []),'accepted':len(kept),'rejected':rej,'acceptanceRate':len(kept)/max(1,len(z.get('items') or []))}
    out['symbols']=clean_symbols;out['entityFilter']={'version':'VMEWS-ENTITY-GATE-12.1.0','input':accepted+rejected,'accepted':accepted,'rejected':rejected,'acceptanceRate':accepted/max(1,accepted+rejected),'acceptedMethods':dict(methods),'reasons':dict(reason),'perSymbol':per_symbol,'rejectedExamples':dict(examples),'ambiguousSymbols':sorted(AMBIGUOUS),'policy':'Ambiguous language tickers require explicit market-ticker syntax, distinctive company-name evidence, or a known company brand. Raw ticker-token coincidence is never sufficient for ambiguous entities.'}
    out['summary']={**(out.get('summary') or {}),'articlesAfterEntityGate':accepted,'articlesRejectedByEntityGate':rejected}
    return out,out['entityFilter']
