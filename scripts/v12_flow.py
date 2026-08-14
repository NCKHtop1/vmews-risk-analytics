import bisect
import math
import statistics
FLOW_FEATURES=["foreignNetRatio1","foreignNetRatio5","foreignNetRatio20","foreignZ60","foreignAccel5","foreignAvailable","propNetRatio1","propNetRatio5","propNetRatio20","propZ60","propAccel5","propAvailable"]
def _finite(x,default=0.0):
    try:v=float(x);return v if math.isfinite(v) else default
    except:return default
class FlowTimeline:
    def __init__(self,rows):self.rows=sorted(rows or [],key=lambda x:str(x.get("date") or ""));self.dates=[str(x.get("date") or "")[:10] for x in self.rows]
    def _features_for(self,typ,date):
        i=bisect.bisect_right(self.dates,date)-1
        keys=lambda:{f"{typ}NetRatio1":0.0,f"{typ}NetRatio5":0.0,f"{typ}NetRatio20":0.0,f"{typ}Z60":0.0,f"{typ}Accel5":0.0,f"{typ}Available":0.0}
        if i<0:return keys()
        key=typ+"NetValue";buy=typ+"BuyValue";sell=typ+"SellValue";hist=[];gross=[]
        for r in self.rows[max(0,i-119):i+1]:hist.append(_finite(r.get(key),0));gross.append(abs(_finite(r.get(buy),0))+abs(_finite(r.get(sell),0)))
        active=[j for j,g in enumerate(gross) if g>1e-12];min_obs=40 if typ=="foreign" else 20
        if len(active)<min_obs:return keys()
        n1=hist[-1];n5=sum(hist[-5:]);n20=sum(hist[-20:]);g1=gross[-1];g5=sum(gross[-5:]);g20=sum(gross[-20:]);av=[hist[j] for j in active[-60:]];mu=statistics.mean(av) if av else 0;sd=statistics.stdev(av) if len(av)>2 else 0;prev5=sum(hist[-10:-5]) if len(hist)>=10 else 0;scale=g20/max(1,min(20,len(gross))) if g20>0 else 1
        return {f"{typ}NetRatio1":n1/g1 if g1 else 0,f"{typ}NetRatio5":n5/g5 if g5 else 0,f"{typ}NetRatio20":n20/g20 if g20 else 0,f"{typ}Z60":max(-8,min(8,(n1-mu)/(sd or 1))),f"{typ}Accel5":max(-5,min(5,(n5-prev5)/(5*scale if scale else 1))),f"{typ}Available":1.0}
    def features(self,date):
        out={};out.update(self._features_for("foreign",date));out.update(self._features_for("prop",date));return out
class FlowFeatureStore:
    def __init__(self,flow_json):self.source=str((flow_json or {}).get("source") or "unknown");self.timelines={s:FlowTimeline(rows) for s,rows in (flow_json or {}).get("symbols",{}).items()}
    def features(self,symbol,date):
        tl=self.timelines.get(symbol);return tl.features(date) if tl else {k:0.0 for k in FLOW_FEATURES}
    def coverage_summary(self,symbols,date):
        f=p=0
        for s in symbols:
            z=self.features(s,date);f+=z["foreignAvailable"]>0;p+=z["propAvailable"]>0
        n=max(1,len(symbols));return {"source":self.source,"symbols":len(symbols),"foreignAvailable":int(f),"foreignCoverage":f/n,"propAvailable":int(p),"propCoverage":p/n}
