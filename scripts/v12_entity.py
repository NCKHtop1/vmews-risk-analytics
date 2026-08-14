import copy
import re
import unicodedata
from collections import Counter,defaultdict

STOP={
 'cong','ty','co','phan','tap','doan','thuong','mai','dich','vu','joint','stock','company','corporation','corp','group','holdings','holding','vietnam','viet','nam','ngan','hang','bank','investment','development','tmcp','mot','thanh','vien','tong','ctcp','saigon','ha','noi','ho','chi','minh'
}
FINANCE_CTX={
 'co phieu','chung khoan','ma co phieu','hose','hsx','hnx','upcom','niem yet','co dong','loi nhuan','doanh thu','co tuc','phat hanh','trai phieu','mua rong','ban rong','khoi ngoai','tu doanh','ket qua kinh doanh','dai hoi co dong','room ngoai','gia muc tieu','khuyen nghi','esop','m a','sap nhap','thoai von','giao dich'
}
EVENT_CTX={'loi nhuan','doanh thu','co tuc','phat hanh','trung thau','du an','xu phat','dieu tra','khoi to','dang ky mua','dang ky ban','trai phieu','no vay','mua lai','sap nhap','khuyen nghi','gia muc tieu'}
AMBIGUOUS={'HCM','CDC','COM','GTA'}
COLLISIONS={
 'HCM':(r'\btp\s*hcm\b',r'\bthanh\s*pho\s*hcm\b',r'\bhochiminh\s*city\b'),
 'CDC':(r'\bcdc\s+home\b',r'\bcenters?\s+for\s+disease\b',r'\bcenter\s+for\s+disease\b'),
 'GTA':(r'\bgta\s*[456]\b',r'\bgrand\s+theft\s+auto\b'),
 'COM':(r'\.com\b',r'\bdot\s+com\b')
}

def norm(s):
    x=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',x).strip()

def company_name_map(market_scan):
    out={}
    for x in (market_scan or {}).get('ranking',[]):
        s=str(x.get('symbol') or '').upper().strip();name=str(x.get('name') or '').strip()
        if s and name:out[s]=name
    return out

def name_tokens(name):
    toks=[]
    for x in norm(name).split():
        if len(x)>=4 and x not in STOP and not x.isdigit():toks.append(x)
    return list(dict.fromkeys(toks))[:10]

def _explicit_ticker(symbol,text):
    s=re.escape(symbol.lower());patterns=[
        rf'\({s}\)',rf'\[{s}\]',rf'\bma\s+(?:co\s+phieu\s+)?{s}\b',rf'\bco\s+phieu\s+{s}\b',rf'\b(?:hose|hsx|hnx|upcom)\s*[:\-]?\s*{s}\b',rf'^\s*{s}\s*[:\-–—]'
    ]
    return any(re.search(p,text) for p in patterns)

def entity_relevance(symbol,name,title):
    symbol=str(symbol or '').upper().strip();text=norm(title);tok=set(text.split());nt=name_tokens(name);ticker=symbol.lower()
    explicit=_explicit_ticker(symbol,text)
    name_hits=[x for x in nt if x in tok]
    strong_name=(len(name_hits)>=2) or (len(name_hits)>=1 and len(name_hits[0])>=7)
    ctx=any(x in text for x in FINANCE_CTX);event_ctx=any(x in text for x in EVENT_CTX);ticker_token=ticker in tok
    collision=any(re.search(p,text) for p in COLLISIONS.get(symbol,()))
    if explicit:return True,1.0,'EXPLICIT_TICKER'
    if strong_name:return True,min(.98,.72+.08*len(name_hits)),'COMPANY_NAME'
    if symbol=='HCM' and collision:return False,0.0,'AMBIGUOUS_TP_HCM'
    if symbol in {'CDC','GTA','COM'} and collision:return False,0.0,'AMBIGUOUS_COLLISION'
    if ticker_token and ctx and symbol not in AMBIGUOUS:return True,.78,'TICKER_FINANCE_CONTEXT'
    if ticker_token and event_ctx and symbol in AMBIGUOUS:return True,.72,'AMBIGUOUS_TICKER_EVENT_CONTEXT'
    return False,.0,'INSUFFICIENT_ENTITY_EVIDENCE'

def filter_sentiment_entities(sentiment,market_scan,eligible_symbols=None):
    out=copy.deepcopy(sentiment);names=company_name_map(market_scan);allowed=set(eligible_symbols or (out.get('symbols') or {}).keys());accepted=rejected=0;reason=Counter();per_symbol={};examples=defaultdict(list)
    clean_symbols={}
    for symbol,z in (out.get('symbols') or {}).items():
        if symbol not in allowed:continue
        kept=[];rej=0
        for x in z.get('items') or []:
            ok,confidence,method=entity_relevance(symbol,names.get(symbol,''),x.get('title'))
            if ok:
                y=dict(x);y['entityConfidence']=confidence;y['entityMethod']=method;kept.append(y);accepted+=1
            else:
                rejected+=1;rej+=1;reason[method]+=1
                if len(examples[symbol])<4:examples[symbol].append({'title':x.get('title'),'reason':method})
        cnt={'POS':0,'NEU':0,'NEG':0};sw=ss=0.0
        for x in kept:
            lab=str(x.get('label') or 'NEU').upper();cnt[lab]=cnt.get(lab,0)+1;v=1 if lab=='POS' else -1 if lab=='NEG' else 0;w=max(.01,float(x.get('weight') or .01));ss+=w*v;sw+=w
        clean_symbols[symbol]={**z,'n':len(kept),'counts':cnt,'signed':ss/sw if sw else 0.0,'items':kept}
        per_symbol[symbol]={'input':len(z.get('items') or []),'accepted':len(kept),'rejected':rej,'acceptanceRate':len(kept)/max(1,len(z.get('items') or []))}
    out['symbols']=clean_symbols;out['entityFilter']={'version':'VMEWS-ENTITY-GATE-12.0.0','input':accepted+rejected,'accepted':accepted,'rejected':rejected,'acceptanceRate':accepted/max(1,accepted+rejected),'reasons':dict(reason),'perSymbol':per_symbol,'rejectedExamples':dict(examples),'policy':'Ticker token alone is insufficient for ambiguous entities; require explicit market-ticker syntax, distinctive company-name evidence, or event-linked finance context.'}
    out['summary']={**(out.get('summary') or {}),'articlesAfterEntityGate':accepted,'articlesRejectedByEntityGate':rejected}
    return out,out['entityFilter']
