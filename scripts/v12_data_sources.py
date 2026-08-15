import bisect
import json
import math
import os
import pathlib
import statistics
import time
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
VN_TZ = timezone(timedelta(hours=7))
MIN_ROWS = int(os.environ.get("V12_MIN_ROWS", "520"))
VNSTOCK_INTERVAL = float(os.environ.get("V12_VNSTOCK_INTERVAL", "3.15"))
MAX_RAW_RETURN_GUARD = float(os.environ.get("V12_MAX_RAW_RETURN_GUARD", "0.24"))
CROSS_SOURCE_MAD_LIMIT = float(os.environ.get("V12_CROSS_SOURCE_MAD_LIMIT", "0.025"))
VNSTOCK_PROVIDER_ORDER = ("VCI", "KBS")
_last_vnstock_call = [0.0]

def _finite(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None

def _date_text(v):
    if v is None:return ""
    try:
        if hasattr(v,"date"):return v.date().isoformat()
    except Exception:pass
    s=str(v).strip(); return s[:10] if len(s)>=10 else s

def _normalize_df(df,symbol,provider):
    if df is None or len(df)==0:raise RuntimeError(f"{symbol}: {provider} returned no OHLCV rows")
    cols={str(c).strip().lower():c for c in df.columns}; time_col=cols.get("time") or cols.get("date") or cols.get("trading_date"); close_col=cols.get("close")
    if time_col is None or close_col is None:raise RuntimeError(f"{symbol}: unexpected {provider} columns {list(df.columns)}")
    raw=[]
    for _,row in df.iterrows():
        d=_date_text(row.get(time_col)); c=_finite(row.get(close_col))
        if not d or c is None or c<=0:continue
        o=_finite(row.get(cols.get("open"))) if cols.get("open") is not None else None; h=_finite(row.get(cols.get("high"))) if cols.get("high") is not None else None; l=_finite(row.get(cols.get("low"))) if cols.get("low") is not None else None; v=_finite(row.get(cols.get("volume"))) if cols.get("volume") is not None else 0.0
        raw.append({"date":d,"open":o or c,"high":h or c,"low":l or c,"close":c,"volume":max(0.0,v or 0.0)})
    if not raw:raise RuntimeError(f"{symbol}: {provider} returned no usable rows")
    sample=[x["close"] for x in raw[-120:] if x["close"]>0]; med=statistics.median(sample) if sample else raw[-1]["close"]; scale=1000.0 if med<1000.0 else 1.0
    if scale!=1.0:
        for r in raw:
            for k in ("open","high","low","close"):r[k]*=scale
    ded={x["date"]:x for x in raw}; return [ded[k] for k in sorted(ded)],scale

def _throttle_vnstock():
    wait=max(0.0,VNSTOCK_INTERVAL-(time.monotonic()-_last_vnstock_call[0]))
    if wait:time.sleep(wait)
    _last_vnstock_call[0]=time.monotonic()

def _history_window(years=8):
    today=datetime.now(VN_TZ).date()
    return (today-timedelta(days=366*years+30)).isoformat(),(today+timedelta(days=1)).isoformat()

def _provider_history(symbol,source,start,end):
    _throttle_vnstock()
    from vnstock import Vnstock
    stock=Vnstock().stock(symbol=symbol,source=source)
    df=stock.quote.history(start=start,end=end,interval="1D")
    rows,scale=_normalize_df(df,symbol,f"Vnstock {source}")
    return rows,{"source":"VNSTOCK","provider":f"{source} Quote.history","rows":len(rows),"unitNormalization":"x1000_to_VND" if scale==1000.0 else "VND","providerCode":source}

def vnstock_history(symbol,years=8):
    start,end=_history_window(years); errors=[]
    _throttle_vnstock()
    try:
        from vnstock.ui import Market
        df=Market().equity(symbol).ohlcv(start=start,end=end,interval="1D",count=3200); rows,scale=_normalize_df(df,symbol,"Vnstock Unified Market")
        if len(rows)>=MIN_ROWS:return rows,{"source":"VNSTOCK","provider":"Unified Market equity OHLCV","rows":len(rows),"unitNormalization":"x1000_to_VND" if scale==1000.0 else "VND","providerCode":"UNIFIED"}
        errors.append(f"Unified only {len(rows)} rows")
    except BaseException as exc:errors.append(f"Unified: {type(exc).__name__}: {exc}")
    for source in VNSTOCK_PROVIDER_ORDER:
        try:
            rows,audit=_provider_history(symbol,source,start,end)
            if len(rows)>=MIN_ROWS:return rows,audit
            errors.append(f"{source} only {len(rows)} rows")
        except BaseException as exc:errors.append(f"{source}: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"{symbol}: VNStock routes failed: {' | '.join(errors)}")

def yahoo_history(symbol):
    from forecast_v11_features import yahoo_adjusted
    rows,audit=yahoo_adjusted(symbol,"10y",18); return rows,{"source":"YAHOO","provider":audit.get("provider"),"rows":len(rows),"adjusted":bool(audit.get("adjusted"))}

def cached_history(symbol):
    p=ROOT/"data"/"hose-fallbacks"/f"{symbol}.json"
    if not p.exists():return [],{"source":"CACHE","provider":"none","rows":0}
    try:
        z=json.loads(p.read_text(encoding="utf-8")); rows=z.get("history") or []; out=[]
        for r in rows:
            c=_finite(r.get("close"))
            if c is None or c<=0:continue
            out.append({"date":str(r.get("date"))[:10],"open":float(r.get("open",c) or c),"high":float(r.get("high",c) or c),"low":float(r.get("low",c) or c),"close":c,"modelClose":float(r.get("modelClose",c) or c),"volume":max(0.0,float(r.get("volume",0) or 0))})
        return out,{"source":"CACHE","provider":"data/hose-fallbacks","rows":len(out)}
    except Exception as exc:return [],{"source":"CACHE","provider":"data/hose-fallbacks","rows":0,"error":str(exc)}

def _raw_log_returns(rows):
    out={}; prev=None
    for r in rows:
        c=_finite(r.get("close"))
        if c is None or c<=0:continue
        if prev and prev[1]>0:out[r["date"]]=math.log(c/prev[1])
        prev=(r["date"],c)
    return out

def _cross_source_mad(primary,secondary):
    a=_raw_log_returns(primary); b=_raw_log_returns(secondary); common=sorted(set(a)&set(b))[-300:]
    if len(common)<60:return None,len(common)
    diffs=[abs(a[d]-b[d]) for d in common if math.isfinite(a[d]) and math.isfinite(b[d])]; return (float(statistics.median(diffs)) if diffs else None),len(diffs)

def _largest_raw_jump(rows):
    rr=_raw_log_returns(rows)
    if not rr:return 0.0,None
    d,v=max(rr.items(),key=lambda kv:abs(kv[1])); return abs(float(v)),d

def reconcile_vnstock_with_yahoo(vn_rows,yahoo_rows):
    if not yahoo_rows:
        out=[{**r,"modelClose":r["close"],"adjustmentFactor":1.0} for r in vn_rows]; jump,jump_date=_largest_raw_jump(out)
        return out,{"method":"VNSTOCK_RAW_NO_ADJUSTMENT_REFERENCE","verified":jump<=MAX_RAW_RETURN_GUARD,"largestRawLogJump":jump,"largestRawJumpDate":jump_date,"factorDates":0}
    factors={}
    for y in yahoo_rows:
        raw=_finite(y.get("close")); mc=_finite(y.get("modelClose",y.get("adjClose")))
        if raw and raw>0 and mc and mc>0:factors[str(y["date"])[:10]]=mc/raw
    if not factors:return reconcile_vnstock_with_yahoo(vn_rows,[])
    fdates=sorted(factors); out=[]
    for r in vn_rows:
        d=r["date"]
        if d in factors:fac=factors[d]
        else:
            i=bisect.bisect_right(fdates,d)-1; fac=factors[fdates[0]] if i<0 else factors[fdates[i]]
        fac=fac if math.isfinite(fac) and fac>0 else 1.0; out.append({**r,"modelClose":r["close"]*fac,"adjustmentFactor":fac})
    jump,jump_date=_largest_raw_jump(vn_rows); model_jump,model_jump_date=_largest_raw_jump([{**r,"close":r["modelClose"]} for r in out])
    return out,{"method":"VNSTOCK_RAW_YAHOO_CORPORATE_ACTION_FACTOR","verified":model_jump<=MAX_RAW_RETURN_GUARD,"largestRawLogJump":jump,"largestRawJumpDate":jump_date,"largestModelLogJump":model_jump,"largestModelJumpDate":model_jump_date,"factorDates":len(factors)}

def _provider_recovery(symbol,yahoo_rows,attempts,years=8):
    """Re-check explicit VNStock providers only after the normal Unified route fails a quality gate.

    This is a data-quality recovery path, not an alpha feature: it never averages prices across
    vendors and it never uses future information. A provider is admitted only when the same
    corporate-action and cross-source return gates used by the primary route pass.
    """
    start,end=_history_window(years); candidates=[]
    for source in VNSTOCK_PROVIDER_ORDER:
        try:
            rows,audit=_provider_history(symbol,source,start,end)
            if len(rows)<MIN_ROWS:
                attempts.append({"stage":f"VNSTOCK_{source}_RECOVERY","ok":False,"reason":"insufficient_rows","rows":len(rows)})
                continue
            mad,common=_cross_source_mad(rows,yahoo_rows or []); adjusted,ca=reconcile_vnstock_with_yahoo(rows,yahoo_rows or []); severe=mad is not None and mad>CROSS_SOURCE_MAD_LIMIT
            ok=bool(ca.get("verified")) and not severe
            attempts.append({"stage":f"VNSTOCK_{source}_RECOVERY","ok":ok,**audit,"crossSourceReturnMAD":mad,"crossSourceCommonDates":common,"corporateAction":ca})
            if ok:candidates.append((float(mad) if mad is not None else float("inf"),source,adjusted,audit,mad,common,ca))
        except BaseException as exc:
            attempts.append({"stage":f"VNSTOCK_{source}_RECOVERY","ok":False,"error":f"{type(exc).__name__}: {exc}"[:500]})
    if not candidates:return None
    candidates.sort(key=lambda x:(x[0],VNSTOCK_PROVIDER_ORDER.index(x[1])))
    _,source,rows,audit,mad,common,ca=candidates[0]
    return rows,{"symbol":symbol,"route":"VNSTOCK_PROVIDER_RECOVERY","rawSource":audit,"adjustmentReference":None,"crossSourceReturnMAD":mad,"crossSourceCommonDates":common,"corporateAction":ca,"recoveryProvider":source,"attempts":attempts,"eligible":len(rows)>=MIN_ROWS}

def get_price_history(symbol,yahoo_reference=True):
    attempts=[]; vn_rows=vn_audit=None
    try:vn_rows,vn_audit=vnstock_history(symbol); attempts.append({"stage":"VNSTOCK_PRIMARY","ok":True,**vn_audit})
    except BaseException as exc:attempts.append({"stage":"VNSTOCK_PRIMARY","ok":False,"error":f"{type(exc).__name__}: {exc}"[:500]})
    yh_rows=yh_audit=None
    if yahoo_reference or vn_rows is None:
        try:yh_rows,yh_audit=yahoo_history(symbol); attempts.append({"stage":"YAHOO_REFERENCE_OR_FALLBACK","ok":True,**yh_audit})
        except BaseException as exc:attempts.append({"stage":"YAHOO_REFERENCE_OR_FALLBACK","ok":False,"error":f"{type(exc).__name__}: {exc}"[:500]})
    if vn_rows and len(vn_rows)>=MIN_ROWS:
        mad,common=_cross_source_mad(vn_rows,yh_rows or []); rows,ca=reconcile_vnstock_with_yahoo(vn_rows,yh_rows or []); severe=mad is not None and mad>CROSS_SOURCE_MAD_LIMIT
        if ca.get("verified") and not severe:return rows,{"symbol":symbol,"route":"VNSTOCK_PRIMARY","rawSource":vn_audit,"adjustmentReference":yh_audit,"crossSourceReturnMAD":mad,"crossSourceCommonDates":common,"corporateAction":ca,"attempts":attempts,"eligible":len(rows)>=MIN_ROWS}
        attempts.append({"stage":"VNSTOCK_QUALITY_GATE","ok":False,"reason":"corporate_action_unverified" if not ca.get("verified") else "cross_source_disagreement","crossSourceReturnMAD":mad,"corporateAction":ca})
        recovered=_provider_recovery(symbol,yh_rows or [],attempts)
        if recovered:
            rows,audit=recovered; audit["adjustmentReference"]=yh_audit; return rows,audit
    if yh_rows and len(yh_rows)>=MIN_ROWS:return yh_rows,{"symbol":symbol,"route":"YAHOO_ADJUSTED_FALLBACK","rawSource":yh_audit,"adjustmentReference":yh_audit,"crossSourceReturnMAD":None,"corporateAction":{"method":"YAHOO_ADJUSTED_CLOSE","verified":True},"attempts":attempts,"eligible":True}
    cache_rows,cache_audit=cached_history(symbol)
    if len(cache_rows)>=MIN_ROWS:
        jump,jump_date=_largest_raw_jump([{**r,"close":r.get("modelClose",r.get("close"))} for r in cache_rows])
        if jump<=MAX_RAW_RETURN_GUARD:
            attempts.append({"stage":"LAST_GOOD_CACHE","ok":True,**cache_audit}); return cache_rows,{"symbol":symbol,"route":"LAST_GOOD_CACHE","rawSource":cache_audit,"adjustmentReference":None,"corporateAction":{"method":"PREVIOUS_VALIDATED_SNAPSHOT","verified":True,"largestModelLogJump":jump,"largestModelJumpDate":jump_date},"attempts":attempts,"eligible":True}
    raise RuntimeError(f"{symbol}: no price route passed V12 quality gate")

def get_index_history(symbol="VNINDEX",years=8):
    today=datetime.now(VN_TZ).date(); start=(today-timedelta(days=366*years+30)).isoformat(); end=(today+timedelta(days=1)).isoformat(); errors=[]; _throttle_vnstock()
    try:
        from vnstock.ui import Market
        df=Market().index(symbol).ohlcv(start=start,end=end,interval="1D",count=3200); rows,scale=_normalize_df(df,symbol,"Vnstock Index")
        for r in rows:r["modelClose"]=r["close"]
        if len(rows)>=MIN_ROWS:return rows,{"route":"VNSTOCK_INDEX_PRIMARY","provider":"Vnstock Market.index OHLCV","rows":len(rows),"unitNormalization":"x1000" if scale==1000.0 else "native"}
    except BaseException as exc:errors.append(f"VNStock index: {type(exc).__name__}: {exc}")
    try:
        from forecast_v11_features import yahoo_adjusted
        ys="^VNINDEX" if symbol.upper()=="VNINDEX" else symbol; rows,audit=yahoo_adjusted(ys,"10y",18)
        if len(rows)>=MIN_ROWS:return rows,{"route":"YAHOO_INDEX_FALLBACK","provider":audit.get("provider"),"rows":len(rows)}
    except BaseException as exc:errors.append(f"Yahoo index: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"{symbol}: index history unavailable: {' | '.join(errors)}")

def build_price_store(symbols):
    store={}; audits={}; failures={}
    for i,symbol in enumerate(symbols,1):
        try:rows,audit=get_price_history(symbol); store[symbol]=rows; audits[symbol]=audit
        except BaseException as exc:failures[symbol]=f"{type(exc).__name__}: {exc}"[:700]
        if i%25==0 or i==len(symbols):print(json.dumps({"v12PriceProgress":i,"total":len(symbols),"passed":len(store),"failed":len(failures),"vnstockPrimary":sum(a.get("route")=="VNSTOCK_PRIMARY" for a in audits.values()),"vnstockRecovered":sum(a.get("route")=="VNSTOCK_PROVIDER_RECOVERY" for a in audits.values()),"yahooFallback":sum(a.get("route")=="YAHOO_ADJUSTED_FALLBACK" for a in audits.values())},ensure_ascii=False),flush=True)
    return store,audits,failures

def source_audit_summary(audits,failures):
    routes={}; mad=[]
    for a in audits.values():
        r=a.get("route","UNKNOWN"); routes[r]=routes.get(r,0)+1; x=a.get("crossSourceReturnMAD")
        if isinstance(x,(int,float)) and math.isfinite(x):mad.append(float(x))
    return {"version":"VMEWS-DATA-AUDIT-12.0.1","generatedAt":datetime.now(timezone.utc).isoformat(),"policy":["VNStock 4.0.4 Unified Market is the primary Vietnamese-equity OHLCV route.","If the primary route fails a quality gate, explicit VCI/KBS routes may recover only after the same return and corporate-action checks pass.","Yahoo adjusted data is used as corporate-action reference and fallback.","A previous validated cache is last-resort only.","No synthetic history padding is allowed."],"symbolsPassed":len(audits),"symbolsFailed":len(failures),"routes":routes,"crossSourceMedianReturnMAD":statistics.median(mad) if mad else None,"failures":failures,"symbols":audits}
