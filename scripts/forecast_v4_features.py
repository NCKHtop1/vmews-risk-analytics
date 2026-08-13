import json, math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote
import numpy as np

MIN_ROWS=520
CORP_GUARD=.22
MACRO_SPECS={"vix":"^VIX","usdVnd":"USDVND=X","dxy":"DX-Y.NYB","us10y":"^TNX","brent":"BZ=F"}
FEATURE_NAMES=["ret1","ret2","ret3","ret5","ret10","ret20","dd20","dd60","trend5","trend10","trend20","trend50","trend200","vol5","vol20","volPct","rsi14","macdNorm","volumeZ","range1","range5","technical","technicalDelta5","marketTechnical","vixLevel","vixRet20","usdVndRet20","dxyRet20","us10yRet20","brentRet20"]

def ema(a,n):
    out=[];e=None;k=2/(n+1)
    for v in a:e=float(v) if e is None else k*float(v)+(1-k)*e;out.append(e)
    return np.asarray(out,float)

def rsi(c,i):
    if i<14:return 50.
    d=np.diff(c[i-14:i+1]);g=np.maximum(d,0).mean();l=np.maximum(-d,0).mean()
    return 100. if l<1e-12 else 100-100/(1+g/l)

def rank(v,h):return float(np.mean(np.asarray(h,float)<=v)) if h else .5

def sanitize(rows):
    out=[]
    for r in rows or []:
        try:
            c=float(r["close"])
            if math.isfinite(c) and c>0:out.append({"date":str(r["date"])[:10],"open":float(r.get("open") or c),"high":float(r.get("high") or c),"low":float(r.get("low") or c),"close":c,"volume":max(0.,float(r.get("volume") or 0))})
        except:pass
    d={r["date"]:r for r in out};rows=[d[k] for k in sorted(d)]
    if not rows:return []
    m=[rows[0]["close"]]
    for i in range(1,len(rows)):
        z=math.log(rows[i]["close"]/rows[i-1]["close"]);m.append(m[-1]*math.exp(0 if abs(z)>.22 else z))
    for r,x in zip(rows,m):r["modelClose"]=x
    return rows

def stock_features(raw):
    rows=sanitize(raw)
    if len(rows)<520:return rows,[]
    c=np.array([r["modelClose"] for r in rows]);h=np.array([r["high"] for r in rows]);l=np.array([r["low"] for r in rows]);v=np.array([r["volume"] for r in rows]);lr=np.zeros(len(c));lr[1:]=np.log(c[1:]/c[:-1]);e12=ema(c,12);e26=ema(c,26);mac=e12-e26;sig=ema(mac,9);vol20=np.zeros(len(c))
    for i in range(1,len(c)):
        x=lr[max(1,i-19):i+1];vol20[i]=(np.std(x,ddof=1) if len(x)>1 else 0)*math.sqrt(252)
    fs=[]
    for i in range(200,len(rows)):
        ret=lambda k:math.log(c[i]/c[i-k]);sma=lambda k:float(np.mean(c[i-k+1:i+1]));dd20=c[i]/np.max(c[i-19:i+1])-1;dd60=c[i]/np.max(c[i-59:i+1])-1;tr={k:c[i]/sma(k)-1 for k in (5,10,20,50,200)};vp=rank(vol20[i],vol20[max(200,i-252):i].tolist());rv=v[max(1,i-20):i];rv=rv[rv>0];vz=(v[i]-rv.mean())/(rv.std(ddof=1) if len(rv)>1 else 1) if v[i]>0 and len(rv) else 0;rs=rsi(c,i);mn=(mac[i]-sig[i])/c[i] if c[i] else 0;mom=c[i]/c[i-20]-1
        p=[min(1,max(0,-dd60/.22)),min(1,max(0,-mom/.14)),min(1,max(0,-tr[50]/.12)),min(1,max(0,-tr[200]/.18)),min(1,max(0,(vp-.45)/.55)),min(1,max(0,(45-rs)/20)),min(1,max(0,-mn/.025)),min(1,max(0,vz/3))*min(1,max(0,-lr[i]/.05))];tech=100*(.18*p[0]+.16*p[1]+.14*p[2]+.10*p[3]+.16*p[4]+.10*p[5]+.08*p[6]+.08*p[7]);ranges=[(h[j]-l[j])/c[j] if c[j] else 0 for j in range(i-4,i+1)]
        fs.append({"i":i,"date":rows[i]["date"],"ret1":lr[i],"ret2":ret(2),"ret3":ret(3),"ret5":ret(5),"ret10":ret(10),"ret20":ret(20),"dd20":dd20,"dd60":dd60,"trend5":tr[5],"trend10":tr[10],"trend20":tr[20],"trend50":tr[50],"trend200":tr[200],"vol5":np.std(lr[i-4:i+1],ddof=1)*math.sqrt(252),"vol20":vol20[i],"volPct":vp,"rsi14":rs/100,"macdNorm":mn,"volumeZ":vz,"range1":(h[i]-l[i])/c[i] if c[i] else 0,"range5":float(np.mean(ranges)),"technical":tech})
    by={f["date"]:f["technical"] for f in fs}
    for f in fs:f["technicalDelta5"]=(f["technical"]-by.get(rows[max(0,f["i"]-5)]["date"],f["technical"]))/100
    return rows,fs

def yahoo(symbol,range_value="10y"):
    err=None;ys=quote(symbol,safe="")
    for host in ("query1.finance.yahoo.com","query2.finance.yahoo.com"):
        try:
            u=f"https://{host}/v8/finance/chart/{ys}?range={range_value}&interval=1d&includePrePost=false&events=div%2Csplits";req=Request(u,headers={"User-Agent":"Mozilla/5.0 VMEWS-Forecast/4.0","Accept":"application/json"})
            with urlopen(req,timeout=18) as r:p=json.loads(r.read().decode())
            z=(p.get("chart",{}).get("result") or [None])[0]
            if not z:raise RuntimeError(str(p.get("chart",{}).get("error")))
            ts=z.get("timestamp") or [];q=((z.get("indicators") or {}).get("quote") or [{}])[0];rows=[]
            for i,t in enumerate(ts):
                try:
                    c=float((q.get("close") or [])[i])
                    if math.isfinite(c) and c>0:rows.append({"date":datetime.fromtimestamp(int(t),timezone.utc).date().isoformat(),"close":c})
                except:pass
            d={r["date"]:r for r in rows};rows=[d[k] for k in sorted(d)]
            if len(rows)<250:raise RuntimeError("short history")
            return rows
        except Exception as e:err=e
    raise RuntimeError(f"{symbol}: {err}")

def external():
    ext={}
    try:mr=yahoo("0P0000HY8X.VN")
    except:
        try:mr=yahoo("^VNINDEX.VN")
        except:mr=[]
    if mr:
        rr=[{"date":r["date"],"open":r["close"],"high":r["close"],"low":r["close"],"close":r["close"],"volume":0} for r in mr];_,fs=stock_features(rr);ext["marketTechnical"]={f["date"]:f["technical"] for f in fs}
    for k,s in MACRO_SPECS.items():
        try:r=yahoo(s);c=[x["close"] for x in r]
        except:r=[];c=[]
        ext[k+"Level"]={x["date"]:x["close"] for x in r};ext[k+"Ret20"]={r[i]["date"]:c[i]/c[i-20]-1 for i in range(20,len(r))}
    return {k:(sorted(v),[v[d] for d in sorted(v)]) for k,v in ext.items()}

def aligned(series,d,default=np.nan):
    keys,vals=series if series else ([],[])
    if not keys:return default
    import bisect;i=bisect.bisect_right(keys,d)-1
    return vals[i] if i>=0 else default
