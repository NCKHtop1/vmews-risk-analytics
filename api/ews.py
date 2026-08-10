from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import date, timedelta, datetime, timezone
import json, math, statistics

try:
    from vnstock.ui import Market
except Exception:
    from vnstock import Market

VERSION = "EWS-2.0.0"


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs):
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def percentile(xs, p):
    vals = sorted(float(x) for x in xs if isinstance(x, (int, float)) and math.isfinite(float(x)))
    if not vals:
        return 0.0
    if len(vals) == 1:
        return vals[0]
    pos = clamp(p, 0, 1) * (len(vals) - 1)
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    w = pos - lo
    return vals[lo] * (1 - w) + vals[hi] * w


def pct_rank(value, history):
    vals = [x for x in history if isinstance(x, (int, float)) and math.isfinite(x)]
    if not vals:
        return 0.5
    return sum(1 for x in vals if x <= value) / len(vals)


def flatten_df(df):
    if df is None or getattr(df, "empty", True):
        return None
    frame = df.copy()
    try:
        frame = frame.reset_index()
    except Exception:
        pass
    cols = []
    for c in frame.columns:
        if isinstance(c, tuple):
            c = "_".join(str(x) for x in c if str(x))
        cols.append(str(c).strip().lower().replace(" ", "_"))
    frame.columns = cols
    return frame


def pick_col(frame, names):
    for n in names:
        if n in frame.columns:
            return n
    for c in frame.columns:
        for n in names:
            if c.endswith("_" + n):
                return c
    return None


def normalize_history(df):
    frame = flatten_df(df)
    if frame is None:
        return [], {"inputRows": 0, "duplicatesRemoved": 0, "invalidRemoved": 0}
    time_col = pick_col(frame, ["time", "date", "datetime", "trading_date", "index"])
    close_col = pick_col(frame, ["close", "price", "index_value"])
    open_col = pick_col(frame, ["open"]); high_col = pick_col(frame, ["high"]); low_col = pick_col(frame, ["low"])
    volume_col = pick_col(frame, ["volume", "match_volume", "total_volume"])
    if close_col is None or time_col is None:
        raise ValueError(f"Unexpected Vnstock OHLCV schema: {list(frame.columns)}")
    raw_count = len(frame); invalid = 0; out = []
    for _, r in frame.iterrows():
        try:
            close = float(r.get(close_col))
            if not math.isfinite(close) or close <= 0:
                invalid += 1; continue
            raw_time = r.get(time_col)
            d = raw_time.isoformat()[:10] if hasattr(raw_time, "isoformat") else str(raw_time)[:10]
            if len(d) != 10:
                invalid += 1; continue
            def num(col, default):
                if not col: return default
                try:
                    v = float(r.get(col)); return v if math.isfinite(v) else default
                except Exception: return default
            out.append({"date": d, "open": num(open_col, close), "high": num(high_col, close), "low": num(low_col, close), "close": close, "volume": num(volume_col, 0)})
        except Exception:
            invalid += 1
    by_date = {r["date"]: r for r in out}
    rows = [by_date[k] for k in sorted(by_date)]
    return rows, {"inputRows": raw_count, "duplicatesRemoved": max(0, len(out)-len(rows)), "invalidRemoved": invalid}


def normalize_quote(df):
    frame = flatten_df(df)
    if frame is None or len(frame) == 0:
        return None
    r = frame.iloc[-1]
    last_col = pick_col(frame, ["price", "match_price", "close", "index_value", "last", "value"])
    change_col = pick_col(frame, ["change", "price_change"])
    pct_col = pick_col(frame, ["percent_change", "change_percent", "change_pct", "pct_change"])
    time_col = pick_col(frame, ["time", "datetime", "date", "trading_date"])
    def n(col):
        if not col: return None
        try:
            v=float(r.get(col)); return v if math.isfinite(v) else None
        except Exception:return None
    q={"last":n(last_col),"change":n(change_col),"percentChange":n(pct_col)}
    if time_col:
        raw=r.get(time_col); q["time"]=raw.isoformat() if hasattr(raw,"isoformat") else str(raw)
    return q if q["last"] is not None else None


def returns(rows):
    out=[0.0]*len(rows)
    for i in range(1,len(rows)):
        a=rows[i-1]["close"]; b=rows[i]["close"]
        out[i]=math.log(b/a) if a>0 and b>0 else 0.0
    return out


def rolling_mean(values, end, window):
    a=values[max(0,end-window+1):end+1]
    return mean(a)


def rolling_sd(values, end, window):
    a=values[max(0,end-window+1):end+1]
    return stdev(a)


def build_features(rows):
    n=len(rows); rets=returns(rows); closes=[r["close"] for r in rows]; vols=[r.get("volume",0) for r in rows]
    vol20=[0.0]*n
    for i in range(n):
        vol20[i]=rolling_sd(rets,i,20)*math.sqrt(252)
    feats=[]
    for i in range(60,n):
        c=closes[i]
        ret1=rets[i]
        ret5=c/closes[i-5]-1 if closes[i-5]>0 else 0
        mom20=c/closes[i-20]-1 if closes[i-20]>0 else 0
        peak=max(closes[i-59:i+1]); dd60=c/peak-1 if peak>0 else 0
        ma50=mean(closes[i-49:i+1]); trend=c/ma50-1 if ma50>0 else 0
        hist_ret=rets[max(1,i-20):i]; rs=stdev(hist_ret); shock_z=(ret1-mean(hist_ret))/rs if rs>1e-12 else 0
        hist_vol=vol20[max(60,i-252):i+1]; vol_pct=pct_rank(vol20[i],hist_vol)
        vhist=[x for x in vols[max(1,i-20):i] if x>0]; vs=stdev(vhist); vz=(vols[i]-mean(vhist))/vs if vs>1e-12 and vols[i]>0 else 0
        vol_p=clamp((vol_pct-.45)/.55)
        dd_p=clamp(abs(min(dd60,0))/.18)
        mom_p=clamp(abs(min(mom20,0))/.12)
        trend_p=clamp(abs(min(trend,0))/.10)
        shock_p=clamp(max(0,-shock_z)/3.09)
        volume_p=clamp(max(0,vz)/3.0) * clamp(max(0,-ret1)/.04)
        contributions={"volatility":25*vol_p,"drawdown":20*dd_p,"momentum":15*mom_p,"trend":15*trend_p,"shock":15*shock_p,"volume":10*volume_p}
        score=sum(contributions.values())
        feats.append({"i":i,"date":rows[i]["date"],"close":c,"ret1":ret1,"ret5":ret5,"mom20":mom20,"vol20":vol20[i],"volPercentile":vol_pct,"dd60":dd60,"trendGap":trend,"shockZ":shock_z,"volumeZ":vz,"pressures":{"volatility":vol_p,"drawdown":dd_p,"momentum":mom_p,"trend":trend_p,"shock":shock_p,"volume":volume_p},"contributions":contributions,"score":score})
    return feats


def forward_drawdown(rows, i, horizon):
    if i>=len(rows)-1:return None
    end=min(len(rows)-1,i+horizon)
    future=[rows[j]["close"] for j in range(i+1,end+1)]
    if not future:return None
    base=rows[i]["close"]
    return min(x/base-1 for x in future)


def forward_return(rows,i,horizon):
    j=min(len(rows)-1,i+horizon)
    if j<=i:return None
    return rows[j]["close"]/rows[i]["close"]-1


def state(score):
    if score>=75:return "CRITICAL"
    if score>=55:return "HIGH"
    if score>=32:return "WATCH"
    return "LOW"


def auc_score(y,s):
    pairs=[(float(sc),int(yy)) for yy,sc in zip(y,s)]
    pos=sum(yy for _,yy in pairs); neg=len(pairs)-pos
    if pos==0 or neg==0:return None
    pairs.sort(key=lambda x:x[0])
    rank_sum=0.0; i=0; rank=1
    while i<len(pairs):
        j=i+1
        while j<len(pairs) and pairs[j][0]==pairs[i][0]:j+=1
        avg=(rank+(rank+(j-i)-1))/2
        rank_sum += avg*sum(pairs[k][1] for k in range(i,j))
        rank += j-i; i=j
    return (rank_sum-pos*(pos+1)/2)/(pos*neg)


def backtest(rows, feats):
    eligible=[f for f in feats if f["i"]+20 < len(rows)]
    if len(eligible)<200:return {}
    split=int(len(eligible)*.70)
    train=eligible[:split]; test=eligible[split:]
    train_dd=[forward_drawdown(rows,f["i"],20) for f in train]
    stress_threshold=percentile([x for x in train_dd if x is not None],.05)
    alert_threshold=percentile([f["score"] for f in train],.80)
    y=[]; pred=[]; scores=[]
    for f in test:
        dd=forward_drawdown(rows,f["i"],20)
        if dd is None:continue
        actual=1 if dd<=stress_threshold else 0
        y.append(actual); pred.append(1 if f["score"]>=alert_threshold else 0); scores.append(f["score"])
    tp=sum(1 for a,p in zip(y,pred) if a==1 and p==1); fp=sum(1 for a,p in zip(y,pred) if a==0 and p==1); fn=sum(1 for a,p in zip(y,pred) if a==1 and p==0); tn=sum(1 for a,p in zip(y,pred) if a==0 and p==0)
    precision=tp/(tp+fp) if tp+fp else 0; recall=tp/(tp+fn) if tp+fn else 0; f1=2*precision*recall/(precision+recall) if precision+recall else 0; acc=(tp+tn)/len(y) if y else 0
    base=sum(y)/len(y) if y else 0; high_actual=[a for a,p in zip(y,pred) if p==1]; high_rate=sum(high_actual)/len(high_actual) if high_actual else 0
    buckets=[]
    for lo,hi,label in [(0,20,"Q1"),(20,40,"Q2"),(40,60,"Q3"),(60,80,"Q4"),(80,101,"Q5")]:
        vals=[]
        for f in test:
            rank=pct_rank(f["score"],[x["score"] for x in train])*100
            dd=forward_drawdown(rows,f["i"],20)
            if dd is not None and lo<=rank<hi: vals.append(1 if dd<=stress_threshold else 0)
        buckets.append({"bucket":label,"eventRate":mean(vals) if vals else 0,"n":len(vals)})
    return {"trainN":len(train),"testN":len(y),"splitDate":test[0]["date"] if test else None,"stressThreshold20":stress_threshold,"alertThreshold":alert_threshold,"precision":precision,"recall":recall,"f1":f1,"accuracy":acc,"auc":auc_score(y,scores),"baseRate":base,"alertEventRate":high_rate,"lift":high_rate/base if base>0 else None,"confusion":{"tp":tp,"fp":fp,"fn":fn,"tn":tn},"calibration":buckets}


def analogs(rows, feats, current):
    candidates=[f for f in feats[:-60] if f["i"]+60<len(rows)]
    keys=["vol20","dd60","mom20","trendGap","shockZ","volumeZ"]
    stats={k:(mean([f[k] for f in candidates]),stdev([f[k] for f in candidates]) or 1.0) for k in keys}
    ranked=[]
    for f in candidates:
        dist=0.0
        for k in keys:
            m,s=stats[k]; dist+=((f[k]-current[k])/s)**2
        dist=math.sqrt(dist/len(keys)); ranked.append((dist,f))
    ranked.sort(key=lambda x:x[0]); nearest=ranked[:40]
    thresholds={}
    for h in (5,20,60):
        hist=[forward_drawdown(rows,f["i"],h) for f in candidates]
        thresholds[h]=percentile([x for x in hist if x is not None],.05)
    horizons=[]
    for h in (5,20,60):
        outcomes=[]
        for _,f in nearest:
            dd=forward_drawdown(rows,f["i"],h)
            if dd is not None:outcomes.append(1 if dd<=thresholds[h] else 0)
        rate=mean(outcomes) if outcomes else 0
        hscore=clamp(.72*(current["score"]/100)+.28*clamp(rate/.25))*100
        horizons.append({"days":h,"score":hscore,"state":state(hscore),"analogStressRate":rate,"tailThreshold":thresholds[h],"analogs":len(outcomes)})
    top=[]
    for dist,f in nearest[:6]:
        r20=forward_return(rows,f["i"],20); dd20=forward_drawdown(rows,f["i"],20)
        top.append({"date":f["date"],"similarity":1/(1+dist),"forwardReturn20":r20,"maxDrawdown20":dd20,"stress":dd20 is not None and dd20<=thresholds[20]})
    return horizons,top


def crash_diagnostic(rows):
    if len(rows)<260:return {}
    rets=returns(rows)
    weekly=[]
    for i in range(5,len(rows),5):
        weekly.append(math.log(rows[i]["close"]/rows[i-5]["close"]))
    if len(weekly)<30:return {}
    hist=weekly[:-1] if len(weekly)>1 else weekly
    mu=mean(hist); sd=stdev(hist); current=math.log(rows[-1]["close"]/rows[-6]["close"])
    threshold=mu-3.09*sd; sigma=(current-mu)/sd if sd>1e-12 else 0
    return {"currentReturn":current,"mean":mu,"sigma":sd,"threshold":threshold,"sigmaDistance":sigma,"triggered":current<=threshold}


def build_alerts(current, crash):
    items=[]
    p=current["pressures"]
    specs=[("volatility","Volatility regime","20-day realized volatility is unusually high relative to the recent historical window."),("drawdown","Drawdown pressure","The index is materially below its recent 60-day peak."),("momentum","Negative momentum","20-session momentum is negative enough to raise downside pressure."),("trend","Trend break","The index is below its 50-session moving average by a material amount."),("shock","Negative return shock","The latest return is an unusually negative statistical shock."),("volume","Volume-confirmed stress","Negative price action is accompanied by unusually high trading volume.")]
    for key,title,desc in specs:
        if p.get(key,0)>=.45:
            items.append({"severity":"HIGH" if p[key]>=.75 else "WATCH","key":key,"title":title,"description":desc,"pressure":p[key],"contribution":current["contributions"][key]})
    if crash.get("triggered"):
        items.insert(0,{"severity":"HIGH","key":"crash","title":"3.09σ crash trigger breached","description":"The current 5-session log return is below the thesis-aligned 3.09 standard-deviation threshold.","pressure":1.0,"contribution":0})
    if not items:items=[{"severity":"LOW","key":"normal","title":"No material warning threshold breached","description":"Current monitored drivers remain below operational alert thresholds.","pressure":0,"contribution":0}]
    return items


def narrative(current, horizons):
    drivers=sorted(current["contributions"].items(),key=lambda x:x[1],reverse=True)[:2]
    names={"volatility":"volatility","drawdown":"drawdown","momentum":"negative momentum","trend":"trend weakness","shock":"negative return shock","volume":"volume-confirmed stress"}
    hz=max(horizons,key=lambda x:x["score"]) if horizons else None
    txt=f"Risk is {state(current['score']).lower()} at {current['score']:.0f}/100. The largest contributors are {names[drivers[0][0]]} and {names[drivers[1][0]]}."
    if hz:txt+=f" The highest forward warning horizon is {hz['days']} trading days, where {hz['analogStressRate']*100:.1f}% of the closest historical states were followed by a tail drawdown."
    return txt


def playbook_for(st):
    if st=="LOW":return ["Maintain normal monitoring cadence.","Keep current exposure and liquidity checks within standard limits.","Refresh the model after the next completed session or material market move."]
    if st=="WATCH":return ["Review portfolio concentration, leverage and stop-loss usage.","Run downside stress scenarios before adding risk.","Increase monitoring frequency for volatility and trend-break alerts."]
    if st=="HIGH":return ["Escalate the warning to the relevant risk owner.","Run portfolio-specific drawdown and liquidity stress tests.","Review risk limits, hedges and concentrated exposures before discretionary risk increases."]
    return ["Treat as a severe market-risk condition and escalate promptly.","Run severe-but-plausible stress scenarios and validate data freshness first.","Review risk reduction, liquidity buffers and exception governance under the applicable mandate."]


def data_quality(rows, meta):
    last=datetime.fromisoformat(rows[-1]["date"]).date(); stale=(date.today()-last).days
    large_gaps=0
    for a,b in zip(rows,rows[1:]):
        try:
            if (datetime.fromisoformat(b["date"]).date()-datetime.fromisoformat(a["date"]).date()).days>12:large_gaps+=1
        except Exception:pass
    return {"rows":len(rows),"start":rows[0]["date"],"end":rows[-1]["date"],"staleCalendarDays":stale,"duplicatesRemoved":meta.get("duplicatesRemoved",0),"invalidRemoved":meta.get("invalidRemoved",0),"largeGaps":large_gaps,"status":"PASS" if stale<=4 and len(rows)>=1000 and large_gaps<=1 else "REVIEW"}


def load_market():
    today=date.today(); start=today-timedelta(days=8*366+45); end=today+timedelta(days=1)
    market=Market(); idx=market.index("VNINDEX")
    hist=idx.ohlcv(start=start.isoformat(),end=end.isoformat(),interval="1D")
    rows,meta=normalize_history(hist)
    if len(rows)<300:raise ValueError(f"Vnstock returned only {len(rows)} valid daily rows")
    quote=None
    try:quote=normalize_quote(idx.quote())
    except Exception:quote=None
    feats=build_features(rows); current=feats[-1]
    horizons,near=analogs(rows,feats,current); bt=backtest(rows,feats); crash=crash_diagnostic(rows); dq=data_quality(rows,meta)
    return {"version":VERSION,"symbol":"VNINDEX","source":"Vnstock v4 Community","provider":"KBS via Vnstock Unified UI","fetchedAt":datetime.now(timezone.utc).isoformat(),"quote":quote,"dataQuality":dq,"current":current,"risk":{"score":current["score"],"state":state(current["score"]),"narrative":narrative(current,horizons),"horizons":horizons,"alerts":build_alerts(current,crash),"playbook":playbook_for(state(current["score"]))},"crashDiagnostic":crash,"backtest":bt,"analogs":near,"rows":rows,"scoreHistory":[{"date":f["date"],"score":round(f["score"],3)} for f in feats],"research":{"anfisAuc":.970,"crashSignals":81,"crashWeeks":31,"stress20Accuracy":.95,"sampleStocks":251,"sectors":10,"researchWindow":"2007–2023"}}


def load_quote():
    market=Market(); idx=market.index("VNINDEX")
    q=normalize_quote(idx.quote())
    if not q:raise ValueError("Vnstock quote returned no usable index price")
    return {"symbol":"VNINDEX","source":"Vnstock v4 Community","provider":"KBS","fetchedAt":datetime.now(timezone.utc).isoformat(),"quote":q}


class handler(BaseHTTPRequestHandler):
    def send_json(self,code,payload,cache):
        raw=json.dumps(payload,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Cache-Control",cache); self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query); mode=q.get("mode",["full"])[0]
        try:
            if mode=="quote":self.send_json(200,load_quote(),"s-maxage=20, stale-while-revalidate=40")
            else:self.send_json(200,load_market(),"s-maxage=300, stale-while-revalidate=900")
        except Exception as exc:
            self.send_json(502,{"error":"VMEWS_DATA_PIPELINE_FAILED","message":str(exc),"version":VERSION,"source":"Vnstock v4 Community"},"no-store")
