import bisect
import collections
import math
import re
from datetime import datetime,timedelta,timezone
VN_TZ=timezone(timedelta(hours=7));HORIZONS=(1,2,3,4,5);EVENT_TYPES=("EARNINGS","REGULATORY","CORPORATE_ACTION","OWNERSHIP","FINANCING","OPERATIONS_MA","ANALYST","MARKET_FLOW","GENERAL");FUNDAMENTAL_EVENTS={"EARNINGS","FINANCING"}
EVENT_FEATURES=["newsN5","newsN20","newsSent20","newsMateriality20","newsQuality20","newsNovelty20","officialShare20","clarificationN20","hierSent20","latestEventAge","eventPriorAR5","eventPriorHit5","eventPriorN5","earningsN20","earningsSent20","fundamentalN20","fundamentalSent20"]
RUMOR_FEATURES=["rumorN5","rumorN20","rumorSources20","rumorSent20","rumorMateriality20","rumorPreMove2","rumorPreMove5","rumorVelocity"];ALL_EVENT_FEATURES=EVENT_FEATURES+RUMOR_FEATURES

def _finite(x,default=0.0):
    try:v=float(x);return v if math.isfinite(v) else default
    except:return default

def _dt(x):
    try:return datetime.fromisoformat(str(x).replace("Z","+00:00")).astimezone(VN_TZ)
    except:return None

def _sent(label):return 1.0 if label=="POS" else -1.0 if label=="NEG" else 0.0

def _tokens(s):
    s=re.sub(r"[^a-z0-9à-ỹ]+"," ",str(s or "").lower());return set(x for x in s.split() if len(x)>=3)
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

def prepare_articles(sentiment,price_store,sector_map,index_rows=None):
    by_symbol={};outcomes=[]
    for symbol,z in (sentiment or {}).get("symbols",{}).items():
        rows=price_store.get(symbol) or []
        if len(rows)<30:continue
        dates=[r["date"] for r in rows];prepared=[];prior_titles=collections.deque()
        for raw in sorted(z.get("items") or [],key=lambda x:str(x.get("publishedAt") or "")):
            avail,i=_align_available_date(raw.get("publishedAt"),dates)
            if i is None:continue
            pub=_dt(raw.get("publishedAt"));
            while prior_titles and (pub-prior_titles[0][0]).days>30:prior_titles.popleft()
            tok=_tokens(raw.get("title"));dup=max((_jaccard(tok,x[1]) for x in prior_titles),default=0.0);nov=max(0.0,min(1.0,1.0-dup));prior_titles.append((pub,tok))
            label=str(raw.get("label") or "NEU").upper();weight=max(.01,_finite(raw.get("sourceQuality"),.5)*_finite(raw.get("materiality"),.5)*max(.2,_finite(raw.get("confidence"),.5)));event=str(raw.get("event") or "GENERAL").upper();event=event if event in EVENT_TYPES else "GENERAL"
            rec={"id":raw.get("id"),"symbol":symbol,"sector":sector_map.get(symbol,"OTHER"),"title":raw.get("title"),"publisher":str(raw.get("publisher") or "Unknown"),"sourceClass":str(raw.get("sourceClass") or "MAINSTREAM"),"event":event,"label":label,"sent":_sent(label),"confidence":_finite(raw.get("confidence"),0),"materiality":_finite(raw.get("materiality"),.35),"quality":_finite(raw.get("sourceQuality"),.5),"weight":weight,"novelty":nov,"publishedAt":raw.get("publishedAt"),"availableDate":avail,"availableIndex":i,"link":raw.get("link")}
            for pre in (2,5):
                if i-pre>=0:
                    a=_finite(rows[i-pre].get("modelClose",rows[i-pre].get("close")),None);b=_finite(rows[i].get("modelClose",rows[i].get("close")),None)
                    if a and b and a>0 and b>0:rec[f"preR{pre}"]=math.log(b/a)
            outcome={"id":rec["id"],"symbol":symbol,"sector":rec["sector"],"event":event,"sourceClass":rec["sourceClass"],"availableDate":avail}
            for h in HORIZONS:
                if i+h<len(rows):
                    a=_finite(rows[i].get("modelClose",rows[i].get("close")),None);b=_finite(rows[i+h].get("modelClose",rows[i+h].get("close")),None)
                    if a and b and a>0 and b>0:
                        rr=math.log(b/a);br=benchmark_return(index_rows,avail,h);has_benchmark=isinstance(br,(int,float)) and math.isfinite(float(br));outcome[f"r{h}"]=rr;outcome[f"benchmarkR{h}"]=float(br) if has_benchmark else None;outcome[f"benchmarkAvailable{h}"]=bool(has_benchmark);outcome[f"ar{h}"]=rr-float(br) if has_benchmark else None;outcome[f"matureDate{h}"]=rows[i+h]["date"]
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

class EvidenceFeatureStore:
    def __init__(self,articles_by_symbol,outcomes,sector_map):
        self.sector_map=sector_map;self.stock={s:Timeline(v) for s,v in articles_by_symbol.items()};sec=collections.defaultdict(list);market=[]
        for rows in articles_by_symbol.values():
            for x in rows:sec[x["sector"]].append(x);market.append(x)
        self.sector={k:Timeline(v) for k,v in sec.items()};self.market=Timeline(market);self.prior=OutcomePrior(outcomes)
    @staticmethod
    def _agg(rows):
        if not rows:return {"n":0,"sent":0,"mat":0,"quality":0,"novelty":0,"official":0,"clar":0,"rumor":0,"rumorSent":0,"rumorMat":0,"rumorSources":0,"fundN":0,"fundSent":0,"earnN":0,"earnSent":0}
        sw=sum(max(.01,x["weight"]) for x in rows)
        def wav(k):return sum(max(.01,x["weight"])*_finite(x.get(k),0) for x in rows)/sw
        rumor=[x for x in rows if x["sourceClass"]=="RUMOR_UNVERIFIED"];fund=[x for x in rows if x["event"] in FUNDAMENTAL_EVENTS];earn=[x for x in rows if x["event"]=="EARNINGS"]
        def ss(a):
            w=sum(max(.01,x["weight"]) for x in a);return sum(max(.01,x["weight"])*x["sent"] for x in a)/w if w else 0
        return {"n":len(rows),"sent":wav("sent"),"mat":wav("materiality"),"quality":wav("quality"),"novelty":wav("novelty"),"official":sum(x["sourceClass"]=="OFFICIAL" for x in rows)/len(rows),"clar":sum(x["sourceClass"]=="CLARIFICATION" for x in rows),"rumor":len(rumor),"rumorSent":ss(rumor),"rumorMat":sum(x["materiality"] for x in rumor)/len(rumor) if rumor else 0,"rumorSources":len(set(x["publisher"] for x in rumor)),"fundN":len(fund),"fundSent":ss(fund),"earnN":len(earn),"earnSent":ss(earn)}
    def features(self,symbol,date):
        sec=self.sector_map.get(symbol,"OTHER");st=self.stock.get(symbol,Timeline([]));s5=self._agg(st.window(date,5));s20rows=st.window(date,20);s20=self._agg(s20rows);sec20=self._agg(self.sector.get(sec,Timeline([])).window(date,20));m20=self._agg(self.market.window(date,20));ws=s20["n"]/(s20["n"]+5);wsec=sec20["n"]/(sec20["n"]+30);hier=ws*s20["sent"]+(1-ws)*(wsec*sec20["sent"]+(1-wsec)*m20["sent"]);latest=st.latest(date)
        if latest:
            age=(datetime.fromisoformat(date).date()-datetime.fromisoformat(latest["availableDate"]).date()).days;pr=self.prior.hierarchical(symbol,sec,latest["event"],date)
        else:age=999;pr={"mean":0,"hit":.5,"n":0}
        rumors=[x for x in s20rows if x["sourceClass"]=="RUMOR_UNVERIFIED"]
        den=sum(x["weight"] for x in rumors);pre2=sum(x.get("preR2",0)*x["weight"] for x in rumors)/den if den else 0;pre5=sum(x.get("preR5",0)*x["weight"] for x in rumors)/den if den else 0;r5=sum(x["sourceClass"]=="RUMOR_UNVERIFIED" for x in st.window(date,5));r20=s20["rumor"]
        return {"newsN5":float(s5["n"]),"newsN20":float(s20["n"]),"newsSent20":s20["sent"],"newsMateriality20":s20["mat"],"newsQuality20":s20["quality"],"newsNovelty20":s20["novelty"],"officialShare20":s20["official"],"clarificationN20":float(s20["clar"]),"hierSent20":hier,"latestEventAge":float(min(180,age))/180,"eventPriorAR5":pr["mean"],"eventPriorHit5":pr["hit"]-.5,"eventPriorN5":math.log1p(pr["n"])/5,"earningsN20":float(s20["earnN"]),"earningsSent20":s20["earnSent"],"fundamentalN20":float(s20["fundN"]),"fundamentalSent20":s20["fundSent"],"rumorN5":float(r5),"rumorN20":float(r20),"rumorSources20":float(s20["rumorSources"]),"rumorSent20":s20["rumorSent"],"rumorMateriality20":s20["rumorMat"],"rumorPreMove2":pre2,"rumorPreMove5":pre5,"rumorVelocity":r5/max(1,r20/4)}
    def current_intelligence(self,symbol,date,limit=10):
        st=self.stock.get(symbol,Timeline([]));recent=list(reversed(st.window(date,30)))[:limit];rumors=[x for x in reversed(st.window(date,60)) if x["sourceClass"]=="RUMOR_UNVERIFIED"][:limit]
        rr=[{k:x.get(k) for k in ("id","title","publisher","sourceClass","event","label","confidence","materiality","quality","novelty","publishedAt","availableDate","link")} for x in recent]
        ru=[{"id":x.get("id"),"title":x.get("title"),"publisher":x.get("publisher"),"publishedAt":x.get("publishedAt"),"availableDate":x.get("availableDate"),"label":x.get("label"),"materiality":x.get("materiality"),"quality":x.get("quality"),"novelty":x.get("novelty"),"preMove2":x.get("preR2"),"preMove5":x.get("preR5"),"state":"UNVERIFIED","link":x.get("link")} for x in rumors]
        return {"recent":rr,"rumors":ru}
