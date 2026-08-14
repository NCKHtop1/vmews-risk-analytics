import bisect
import collections
import math
import re
import statistics
from datetime import datetime,timedelta,timezone
VN_TZ=timezone(timedelta(hours=7));HORIZONS=(1,2,3,4,5);EVENT_TYPES=("EARNINGS","REGULATORY","CORPORATE_ACTION","OWNERSHIP","FINANCING","OPERATIONS_MA","ANALYST","MARKET_FLOW","GENERAL");FUNDAMENTAL_EVENTS={"EARNINGS","FINANCING"}
EVENT_FEATURES=["newsN5","newsN20","newsSent20","newsMateriality20","newsQuality20","newsNovelty20","officialShare20","clarificationN20","hierSent20","latestEventAge","eventPriorAR5","eventPriorHit5","eventPriorN5","earningsN20","earningsSent20","fundamentalN20","fundamentalSent20"]
RUMOR_FEATURES=["rumorN5","rumorN20","rumorSources20","rumorSent20","rumorMateriality20","rumorQuality20","rumorDuplication20","rumorPreMove2","rumorPreMove5","rumorPreVolumeZ2","rumorPreVolumeZ5","rumorPriceLeadShare","rumorVolumeLeadShare","rumorVelocity"];ALL_EVENT_FEATURES=EVENT_FEATURES+RUMOR_FEATURES
DENIAL_TERMS=("phu nhan","bac bo","khong co chuyen","khong chinh xac","sai su that","tin gia","deny","denies","false rumor")

def _finite(x,default=0.0):
    try:v=float(x);return v if math.isfinite(v) else default
    except:return default

def _dt(x):
    try:return datetime.fromisoformat(str(x).replace("Z","+00:00")).astimezone(VN_TZ)
    except:return None

def _sent(label):return 1.0 if label=="POS" else -1.0 if label=="NEG" else 0.0

def _normalize_text(s):
    s=str(s or "").lower().replace("đ","d")
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9à-ỹ]+"," ",s)).strip()
def _tokens(s):return set(x for x in _normalize_text(s).split() if len(x)>=3)
def _jaccard(a,b):return len(a&b)/max(1,len(a|b)) if a and b else 0.0

def build_sector_map(market_scan):
    out={}
    for x in (market_scan or {}).get("ranking",[]):
        s=str(x.get("symbol") or "").upper().strip();sec=str(x.get("sector") or "").strip()
        if s and sec:out[s]=sec
    return out

def _align_available_date(published_at,trading_dates):
    d=_dt(published_at)
    if not d or not trading_dates:return None,None
    target=d.date().isoformat()
    if d.hour>=15:target=(d.date()+timedelta(days=1)).isoformat()
    i=bisect.bisect_left(trading_dates,target)
    return (None,None) if i>=len(trading_dates) else (trading_dates[i],i)

def benchmark_return(index_rows,origin_date,h):
    if not index_rows:return None
    dates=[r["date"] for r in index_rows];i=bisect.bisect_left(dates,origin_date)
    if i>=len(dates) or dates[i]!=origin_date or i+h>=len(index_rows):return None
    a=_finite(index_rows[i].get("modelClose",index_rows[i].get("close")),None);b=_finite(index_rows[i+h].get("modelClose",index_rows[i+h].get("close")),None)
    return math.log(b/a) if a and b and a>0 and b>0 else None

def _pre_volume_z(rows,i,window):
    if i<=1:return 0.0
    base=[_finite(rows[j].get("volume"),0) for j in range(max(0,i-60),i)];base=[x for x in base if x>0]
    sample=[_finite(rows[j].get("volume"),0) for j in range(max(0,i-window),i)];sample=[x for x in sample if x>0]
    if len(base)<15 or not sample:return 0.0
    mu=statistics.mean(base);sd=statistics.stdev(base) if len(base)>2 else 0.0
    return max(-8.0,min(8.0,(statistics.mean(sample)-mu)/(sd or 1.0)))

def prepare_articles(sentiment,price_store,sector_map,index_rows=None):
    by_symbol={};outcomes=[]
    for symbol,z in (sentiment or {}).get("symbols",{}).items():
        rows=price_store.get(symbol) or []
        if len(rows)<30:continue
        dates=[r["date"] for r in rows];prepared=[];prior_titles=collections.deque()
        for raw in sorted(z.get("items") or [],key=lambda x:str(x.get("publishedAt") or "")):
            avail,i=_align_available_date(raw.get("publishedAt"),dates)
            if i is None:continue
            pub=_dt(raw.get("publishedAt"))
            if pub is None:continue
            while prior_titles and (pub-prior_titles[0][0]).days>30:prior_titles.popleft()
            tok=_tokens(raw.get("title"));dup=max((_jaccard(tok,x[1]) for x in prior_titles),default=0.0);nov=max(0.0,min(1.0,1.0-dup));prior_titles.append((pub,tok))
            label=str(raw.get("label") or "NEU").upper();weight=max(.01,_finite(raw.get("sourceQuality"),.5)*_finite(raw.get("materiality"),.5)*max(.2,_finite(raw.get("confidence"),.5)));event=str(raw.get("event") or "GENERAL").upper();event=event if event in EVENT_TYPES else "GENERAL"
            rec={"id":raw.get("id"),"symbol":symbol,"sector":sector_map.get(symbol,"OTHER"),"title":raw.get("title"),"titleTokens":sorted(tok),"publisher":str(raw.get("publisher") or "Unknown"),"sourceClass":str(raw.get("sourceClass") or "MAINSTREAM"),"event":event,"label":label,"sent":_sent(label),"confidence":_finite(raw.get("confidence"),0),"materiality":_finite(raw.get("materiality"),.35),"quality":_finite(raw.get("sourceQuality"),.5),"weight":weight,"novelty":nov,"duplication":dup,"publishedAt":raw.get("publishedAt"),"availableDate":avail,"availableIndex":i,"link":raw.get("link")}
            for pre in (2,5):
                if i-pre>=0:
                    a=_finite(rows[i-pre].get("modelClose",rows[i-pre].get("close")),None);b=_finite(rows[i].get("modelClose",rows[i].get("close")),None)
                    if a and b and a>0 and b>0:rec[f"preR{pre}"]=math.log(b/a)
                    rec[f"preVolumeZ{pre}"]=_pre_volume_z(rows,i,pre)
            outcome={"id":rec["id"],"symbol":symbol,"sector":rec["sector"],"event":event,"sourceClass":rec["sourceClass"],"availableDate":avail,"preR2":rec.get("preR2"),"preR5":rec.get("preR5"),"preVolumeZ2":rec.get("preVolumeZ2"),"preVolumeZ5":rec.get("preVolumeZ5")}
            for h in HORIZONS:
                if i+h<len(rows):
                    a=_finite(rows[i].get("modelClose",rows[i].get("close")),None);b=_finite(rows[i+h].get("modelClose",rows[i+h].get("close")),None)
                    if a and b and a>0 and b>0:
                        rr=math.log(b/a);br=benchmark_return(index_rows,avail,h);outcome[f"r{h}"]=rr;outcome[f"ar{h}"]=rr-br if isinstance(br,(int,float)) else rr;outcome[f"matureDate{h}"]=rows[i+h]["date"]
            prepared.append(rec);outcomes.append(outcome)
        by_symbol[symbol]=prepared
    return by_symbol,outcomes

class Timeline:
    def __init__(self,rows):self.rows=sorted(rows,key=lambda x:x["availableDate"]);self.dates=[x["availableDate"] for x in self.rows]
    def window(self,date,days):
        if not self.rows:return []
        end=bisect.bisect_right(self.dates,date);start_date=(datetime.fromisoformat(date).date()-timedelta(days=days)).isoformat();start=bisect.bisect_left(self.dates,start_date);return self.rows[start:end]
    def latest(self,date):
        i=bisect.bisect_right(self.dates,date)-1;return self.rows[i] if i>=0 else None

class OutcomePrior:
    def __init__(self,outcomes):
        groups=collections.defaultdict(list)
        for x in outcomes:
            ar=x.get("ar5");mature=x.get("matureDate5")
            if not isinstance(ar,(int,float)) or not math.isfinite(ar) or not mature:continue
            for k in [("MARKET",x["event"]),("SECTOR",x["sector"],x["event"]),("STOCK",x["symbol"],x["event"])]:groups[k].append((mature,float(ar)))
        self.groups={}
        for k,vals in groups.items():
            vals.sort();dates=[];sums=[0.0];pos=[0]
            for d,v in vals:dates.append(d);sums.append(sums[-1]+v);pos.append(pos[-1]+(1 if v>0 else 0))
            self.groups[k]=(dates,sums,pos)
    def _query(self,key,date):
        z=self.groups.get(key)
        if not z:return None
        dates,sums,pos=z;n=bisect.bisect_right(dates,date)
        return None if n<=0 else {"n":n,"mean":sums[n]/n,"hit":pos[n]/n}
    def hierarchical(self,symbol,sector,event,date):
        stock=self._query(("STOCK",symbol,event),date);sec=self._query(("SECTOR",sector,event),date);market=self._query(("MARKET",event),date);mn=market or {"n":0,"mean":0.0,"hit":.5};sn=sec or mn;st=stock or sn
        wm=min(1,mn["n"]/60);mm=wm*mn["mean"];mh=wm*mn["hit"]+(1-wm)*.5;ws=min(1,sn["n"]/30);sm=ws*sn["mean"]+(1-ws)*mm;sh=ws*sn["hit"]+(1-ws)*mh;wt=min(1,st["n"]/8);mean=wt*st["mean"]+(1-wt)*sm;hit=wt*st["hit"]+(1-wt)*sh
        return {"mean":mean,"hit":hit,"n":st["n"] if stock else sn["n"] if sec else mn["n"],"level":"STOCK" if stock and stock["n"]>=8 else "SECTOR" if sec and sec["n"]>=20 else "MARKET"}

def _is_denial(title):
    t=_normalize_text(title);return any(x in t for x in DENIAL_TERMS)
def resolve_rumor_state(rumor,all_rows,as_of):
    rtok=set(rumor.get("titleTokens") or _tokens(rumor.get("title")));rdate=rumor.get("availableDate") or "";independent=set();official=[];clarifications=[]
    for x in all_rows:
        d=x.get("availableDate") or ""
        if not d or d<rdate or d>as_of or x.get("id")==rumor.get("id"):continue
        xtok=set(x.get("titleTokens") or _tokens(x.get("title")));sim=_jaccard(rtok,xtok);same_event=x.get("event")==rumor.get("event")
        if sim>=.20 or (same_event and sim>=.12):
            if x.get("publisher")!=rumor.get("publisher"):independent.add(x.get("publisher"))
            if x.get("sourceClass")=="CLARIFICATION":clarifications.append(x)
            if x.get("sourceClass")=="OFFICIAL":official.append(x)
    denial=next((x for x in clarifications+official if _is_denial(x.get("title"))),None)
    if denial:return {"state":"DENIED","confirmationId":denial.get("id"),"independentSources":len(independent),"truthConfidence":None,"truthMethod":"STATE_FROM_PUBLISHED_CLARIFICATION_NOT_PROBABILITY_MODEL"}
    if official:
        x=official[0];return {"state":"CONFIRMED","confirmationId":x.get("id"),"independentSources":len(independent),"truthConfidence":None,"truthMethod":"STATE_FROM_PUBLISHED_OFFICIAL_SOURCE_NOT_PROBABILITY_MODEL"}
    if clarifications:
        x=clarifications[0];return {"state":"CLARIFIED","confirmationId":x.get("id"),"independentSources":len(independent),"truthConfidence":None,"truthMethod":"STATE_FROM_PUBLISHED_CLARIFICATION_NOT_PROBABILITY_MODEL"}
    if len(independent)>=2:return {"state":"CORROBORATED","confirmationId":None,"independentSources":len(independent),"truthConfidence":None,"truthMethod":"NO_GOLD_TRUTH_LABEL"}
    age=(datetime.fromisoformat(as_of).date()-datetime.fromisoformat(rdate).date()).days if rdate else 999
    return {"state":"STALE" if age>30 else "UNVERIFIED","confirmationId":None,"independentSources":len(independent),"truthConfidence":None,"truthMethod":"NO_GOLD_TRUTH_LABEL"}

class EvidenceFeatureStore:
    def __init__(self,articles_by_symbol,outcomes,sector_map):
        self.sector_map=sector_map;self.stock={s:Timeline(v) for s,v in articles_by_symbol.items()};sec=collections.defaultdict(list);market=[]
        for rows in articles_by_symbol.values():
            for x in rows:sec[x["sector"]].append(x);market.append(x)
        self.sector={k:Timeline(v) for k,v in sec.items()};self.market=Timeline(market);self.prior=OutcomePrior(outcomes)
    @staticmethod
    def _agg(rows):
        if not rows:return {"n":0,"sent":0,"mat":0,"quality":0,"novelty":0,"official":0,"clar":0,"rumor":0,"rumorSent":0,"rumorMat":0,"rumorQuality":0,"rumorDup":0,"rumorSources":0,"fundN":0,"fundSent":0,"earnN":0,"earnSent":0}
        sw=sum(max(.01,x["weight"]) for x in rows)
        def wav(k):return sum(max(.01,x["weight"])*_finite(x.get(k),0) for x in rows)/sw
        rumor=[x for x in rows if x["sourceClass"]=="RUMOR_UNVERIFIED"];fund=[x for x in rows if x["event"] in FUNDAMENTAL_EVENTS];earn=[x for x in rows if x["event"]=="EARNINGS"]
        def ss(a):
            w=sum(max(.01,x["weight"]) for x in a);return sum(max(.01,x["weight"])*x["sent"] for x in a)/w if w else 0
        def rw(k):
            w=sum(max(.01,x["weight"]) for x in rumor);return sum(max(.01,x["weight"])*_finite(x.get(k),0) for x in rumor)/w if w else 0
        return {"n":len(rows),"sent":wav("sent"),"mat":wav("materiality"),"quality":wav("quality"),"novelty":wav("novelty"),"official":sum(x["sourceClass"]=="OFFICIAL" for x in rows)/len(rows),"clar":sum(x["sourceClass"]=="CLARIFICATION" for x in rows),"rumor":len(rumor),"rumorSent":ss(rumor),"rumorMat":rw("materiality"),"rumorQuality":rw("quality"),"rumorDup":rw("duplication"),"rumorSources":len(set(x["publisher"] for x in rumor)),"fundN":len(fund),"fundSent":ss(fund),"earnN":len(earn),"earnSent":ss(earn)}
    def features(self,symbol,date):
        sec=self.sector_map.get(symbol,"OTHER");st=self.stock.get(symbol,Timeline([]));s5=self._agg(st.window(date,5));s20rows=st.window(date,20);s20=self._agg(s20rows);sec20=self._agg(self.sector.get(sec,Timeline([])).window(date,20));m20=self._agg(self.market.window(date,20));ws=s20["n"]/(s20["n"]+5);wsec=sec20["n"]/(sec20["n"]+30);hier=ws*s20["sent"]+(1-ws)*(wsec*sec20["sent"]+(1-wsec)*m20["sent"]);latest=st.latest(date)
        if latest:
            age=(datetime.fromisoformat(date).date()-datetime.fromisoformat(latest["availableDate"]).date()).days;pr=self.prior.hierarchical(symbol,sec,latest["event"],date)
        else:age=999;pr={"mean":0,"hit":.5,"n":0}
        rumors=[x for x in s20rows if x["sourceClass"]=="RUMOR_UNVERIFIED"];den=sum(x["weight"] for x in rumors)
        def wr(k):return sum(_finite(x.get(k),0)*x["weight"] for x in rumors)/den if den else 0
        pre2=wr("preR2");pre5=wr("preR5");pv2=wr("preVolumeZ2");pv5=wr("preVolumeZ5");price_lead=sum(abs(_finite(x.get("preR2"),0))>=.03 for x in rumors)/len(rumors) if rumors else 0;volume_lead=sum(_finite(x.get("preVolumeZ2"),0)>=1.0 for x in rumors)/len(rumors) if rumors else 0;r5=sum(x["sourceClass"]=="RUMOR_UNVERIFIED" for x in st.window(date,5));r20=s20["rumor"]
        return {"newsN5":float(s5["n"]),"newsN20":float(s20["n"]),"newsSent20":s20["sent"],"newsMateriality20":s20["mat"],"newsQuality20":s20["quality"],"newsNovelty20":s20["novelty"],"officialShare20":s20["official"],"clarificationN20":float(s20["clar"]),"hierSent20":hier,"latestEventAge":float(min(180,age))/180,"eventPriorAR5":pr["mean"],"eventPriorHit5":pr["hit"]-.5,"eventPriorN5":math.log1p(pr["n"])/5,"earningsN20":float(s20["earnN"]),"earningsSent20":s20["earnSent"],"fundamentalN20":float(s20["fundN"]),"fundamentalSent20":s20["fundSent"],"rumorN5":float(r5),"rumorN20":float(r20),"rumorSources20":float(s20["rumorSources"]),"rumorSent20":s20["rumorSent"],"rumorMateriality20":s20["rumorMat"],"rumorQuality20":s20["rumorQuality"],"rumorDuplication20":s20["rumorDup"],"rumorPreMove2":pre2,"rumorPreMove5":pre5,"rumorPreVolumeZ2":pv2,"rumorPreVolumeZ5":pv5,"rumorPriceLeadShare":price_lead,"rumorVolumeLeadShare":volume_lead,"rumorVelocity":r5/max(1,r20/4)}
    def current_intelligence(self,symbol,date,limit=10):
        st=self.stock.get(symbol,Timeline([]));all_rows=st.window(date,120);recent=list(reversed(st.window(date,30)))[:limit];rumors=[x for x in reversed(st.window(date,60)) if x["sourceClass"]=="RUMOR_UNVERIFIED"][:limit]
        rr=[{k:x.get(k) for k in ("id","title","publisher","sourceClass","event","label","confidence","materiality","quality","novelty","publishedAt","availableDate","link")} for x in recent]
        ru=[]
        for x in rumors:
            state=resolve_rumor_state(x,all_rows,date);ru.append({"id":x.get("id"),"title":x.get("title"),"publisher":x.get("publisher"),"publishedAt":x.get("publishedAt"),"availableDate":x.get("availableDate"),"label":x.get("label"),"materiality":x.get("materiality"),"quality":x.get("quality"),"novelty":x.get("novelty"),"duplicationRatio":x.get("duplication"),"preMove2":x.get("preR2"),"preMove5":x.get("preR5"),"preVolumeZ2":x.get("preVolumeZ2"),"preVolumeZ5":x.get("preVolumeZ5"),"priceLeadsRumor":abs(_finite(x.get("preR2"),0))>=.03,"volumeLeadsRumor":_finite(x.get("preVolumeZ2"),0)>=1.0,"state":state["state"],"confirmationId":state["confirmationId"],"independentSources":state["independentSources"],"truthConfidence":state["truthConfidence"],"truthMethod":state["truthMethod"],"anonymousSourceAvailable":False,"socialSignalAvailable":False,"link":x.get("link")})
        return {"recent":rr,"rumors":ru,"rumorMethod":{"truthProbability":"NOT_RENDERED_WITHOUT_GOLD_TRUTH_LABELS","confirmationState":"Uses only already-published official/clarification/corroborating articles available by as-of date.","prePrice":"Adjusted return before first rumor observation.","preVolume":"Volume z-score before first rumor observation.","missingSocialAnonymous":"Explicitly unavailable rather than imputed neutral."}}
