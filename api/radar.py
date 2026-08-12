import pathlib, importlib.util, json, re
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parents[1]
core_path = pathlib.Path(__file__).with_name('stocks.py')
spec = importlib.util.spec_from_file_location('vmews_core_final', core_path)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

price_path = pathlib.Path(__file__).with_name('price_history.py')
pspec = importlib.util.spec_from_file_location('vmews_price_history', price_path)
price_history = importlib.util.module_from_spec(pspec)
pspec.loader.exec_module(price_history)

try:
    POLICY = json.loads((ROOT / 'data' / 'alert-policy.json').read_text(encoding='utf-8'))
except Exception:
    POLICY = {'version':'VMEWS-ALERT-POLICY-FALLBACK','riskIndexBands':{'red':78,'yellow':65,'watch':50},'eligibility':{'minCompletedSessionsForStructuralDetail':240}}

VERSION = 'STOCK-EWS-5.2.0-PRODUCTION'
VN_TZ = timezone(timedelta(hours=7))
DEFAULT_SCAN = ['FPT','PNJ','VCB','HPG','MWG','VHM','SSI','DGC']
SCAN_MAX = 8
BANDS = POLICY.get('riskIndexBands', {})
RED = float(BANDS.get('red', 78))
YELLOW = float(BANDS.get('yellow', 65))
WATCH = float(BANDS.get('watch', 50))
MIN_DETAIL_ROWS = int(POLICY.get('eligibility', {}).get('minCompletedSessionsForStructuralDetail', 240))

def clean_symbol(s):
    return re.sub('[^A-Z0-9]','',str(s or '').upper())[:8]

def pct_quality(rows,audit=None):
    return {'status':'PASS' if len(rows)>=MIN_DETAIL_ROWS else 'REVIEW','rows':len(rows),'start':rows[0]['date'] if rows else None,'end':rows[-1]['date'] if rows else None,'coverageRatio':1.0 if len(rows)>=MIN_DETAIL_ROWS else max(0,len(rows)/MIN_DETAIL_ROWS),'largeGaps':0,'intradayBarExcluded':False,'requestAudit':[audit] if audit else []}

def static_market_snapshot():
    try:
        p=json.loads((ROOT/'data'/'market-context.json').read_text(encoding='utf-8'))
        m=p.get('market') or {}
        if m.get('available') and isinstance(m.get('score'),(int,float)) and m.get('date'):
            return {**m,'snapshotGeneratedAt':p.get('generatedAt'),'snapshotFallback':True}
    except Exception:
        pass
    return None

def safe_market(asof=None):
    # Current EOD research prefers the independently refreshed snapshot. This avoids
    # turning a transient Yahoo index-symbol failure into a false NORMAL market state.
    if not asof:
        snap=static_market_snapshot()
        if snap:
            return snap
    last=None
    for ticker in ['^VNINDEX.VN','0P0000HY8X.VN','VNINDEX.VN']:
        try:
            rows,_,host=core.yahoo_chart(ticker,'10y',9)
            if asof: rows=[r for r in rows if r['date']<=asof]
            if len(rows)<MIN_DETAIL_ROWS:
                raise RuntimeError(f'{ticker}: only {len(rows)} rows')
            cur,hz,_=core.technical_state(rows,asof)
            a=hz['20']; score=.65*cur['technical']+.35*(a['score'] if a.get('available') else 50)
            return {'score':score,'available':True,'technical':cur['technical'],'analog20':a,'date':cur['date'],'ticker':ticker,'rows':len(rows),'source':'Yahoo Finance','audit':[{'source':'Yahoo Finance','provider':host,'symbol':'VNINDEX','ticker':ticker,'rows':len(rows),'ok':True}]}
        except Exception as e: last=e
    return {'score':50,'available':False,'technical':None,'analog20':{'score':50,'rate':None,'matches':0,'available':False},'date':None,'reason':str(last or 'VNINDEX context unavailable')[:240],'audit':[]}

def safe_macro():
    try:return core.macro_module()
    except Exception as e:return {'score':50,'available':False,'factors':{},'reason':str(e)[:200]}

def aggregate(mods):
    weights={'technical':.30,'analog':.25,'market':.15,'macro':.10,'sentiment':.10,'fundamental':.10}; total=used=0.0
    for k,w in weights.items():
        m=mods.get(k) or {}
        if m.get('available',True) and isinstance(m.get('score'),(int,float)): total+=w*m['score']; used+=w
    return (total/used if used else 50),used

def classify(score,cur,conf):
    dd=cur.get('dd60',0); weak=cur.get('mom20',0)<0 or cur.get('trend50',0)<0
    if score>=RED and weak and conf>=.70:return 'PRE_CRASH_RED','RED','HIGH'
    if score>=YELLOW and weak and conf>=.55:return 'PRE_CRASH_YELLOW','YELLOW','ELEVATED'
    if score>=WATCH and weak:return 'WATCH','YELLOW','WATCH'
    if dd<=-.15:return 'ACTIVE_DRAWDOWN','GRAY','DRAWDOWN'
    return 'NORMAL','GREEN','CLEAR'

def reasons(mods):
    labels={'technical':'Technical','analog':'Historical analog','market':'VNINDEX regime','macro':'Macro/cross-asset','sentiment':'News sentiment','fundamental':'Fundamentals'}; xs=[]
    for k,m in mods.items():
        if m.get('available',True) and isinstance(m.get('score'),(int,float)):xs.append((m['score'],labels[k]))
    xs.sort(reverse=True); return [f'{name} {score:.0f}/100' for score,name in xs[:4]]

def load_rows(symbol,asof=None,min_rows=None):
    min_rows=int(min_rows or MIN_DETAIL_ROWS); errors=[]
    try:
        rows,_,host=core.yahoo_chart(symbol,'10y',10)
        if asof: rows=[r for r in rows if r['date']<=asof]
        if len(rows)>=min_rows:
            return rows,{'source':'Yahoo Finance','provider':host,'type':'price-history','symbol':symbol,'rows':len(rows),'ok':True}
        errors.append(f'Yahoo only {len(rows)} rows')
    except Exception as e:
        errors.append(f'Yahoo: {e}')
    try:
        rows,audit=price_history.vnstock_equity_history(symbol,11)
        if asof: rows=[r for r in rows if r['date']<=asof]
        audit={**audit,'type':'price-history','rows':len(rows)}
        if len(rows)>=min_rows:
            return rows,audit
        errors.append(f'Vnstock only {len(rows)} rows')
    except BaseException as e:
        errors.append(f'Vnstock: {e}')
    raise RuntimeError(f'{symbol}: no price-history source with >= {min_rows} completed sessions; ' + ' | '.join(errors))

def scan_one(symbol,market,macro):
    rows,audit=load_rows(symbol); cur,hz,_=core.technical_state(rows)
    mods={'technical':{'score':cur['technical'],'available':True,'drivers':cur.get('technicalDrivers',{})},'analog':hz['20'],'market':market,'macro':macro,'sentiment':{'score':50,'available':False,'note':'Deferred in watchlist scan'},'fundamental':{'score':50,'available':False,'note':'Deferred in watchlist scan'}}
    score,conf=aggregate(mods); phase,color,state=classify(score,cur,conf)
    return {'symbol':symbol,'name':core.NAMES.get(symbol,symbol),'date':cur['date'],'close':cur['close'],'ret5':cur['ret5'],'score':score,'confidence':conf,'phase':phase,'color':color,'state':state,'effectiveScore':score,'modules':mods,'current':cur,'quote':None,'liveOverlay':{'available':False,'score':score},'reasons':reasons(mods),'dataQuality':pct_quality(rows,audit),'audit':[audit],'policyVersion':POLICY.get('version')}

def scan(q):
    raw=q.get('symbols',[''])[0]; symbols=[clean_symbol(x) for x in raw.split(',') if clean_symbol(x)] if raw else DEFAULT_SCAN[:]; symbols=list(dict.fromkeys(symbols))[:SCAN_MAX]
    market=safe_market(); macro=safe_macro(); items=[]; errors=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut={ex.submit(scan_one,s,market,macro):s for s in symbols}
        for f in as_completed(fut):
            try:items.append(f.result())
            except Exception as e:errors.append({'symbol':fut[f],'error':str(e)[:400]})
    items.sort(key=lambda x:x['effectiveScore'],reverse=True)
    return {'version':VERSION,'policyVersion':POLICY.get('version'),'mode':'scan','asOf':datetime.now(VN_TZ).isoformat(),'universeSize':len(core.UNIVERSE),'requestedSymbols':symbols,'scanned':len(items),'redList':[x for x in items if x['color']=='RED'],'yellowList':[x for x in items if x['phase']=='PRE_CRASH_YELLOW'],'watchList':[x for x in items if x['phase']=='WATCH'],'greenList':[x for x in items if x['color']=='GREEN'],'activeDrawdown':[x for x in items if x['phase']=='ACTIVE_DRAWDOWN'],'ranking':items,'market':market,'macro':macro,'errors':errors,'scanPolicy':{'maxSymbolsPerRequest':SCAN_MAX,'priceSource':'Yahoo Finance with Vnstock Unified Market fallback','fundamentals':'Vnstock optional in detail','riskBands':{'watch':WATCH,'yellow':YELLOW,'red':RED}}}

def safe_sentiment(symbol,asof=None,days=45):
    try:return core.sentiment_module(symbol,asof,days,20)
    except Exception as e:return {'score':50,'available':False,'headlines':[],'error':str(e)[:200]}

def safe_fundamental(symbol,historical=False):
    if historical:return {'score':50,'available':False,'metrics':{},'note':'Historical fundamentals excluded to prevent look-ahead bias.'}
    try:return core.fundamental_module(symbol)
    except Exception as e:return {'score':50,'available':False,'metrics':{},'error':str(e)[:200]}

def replay(rows,fs,cutoff_i):
    out=[]; last=-999; eligible=[f for f in fs if f['i']<=cutoff_i]
    for f in eligible:
        i=f['i']
        if i+20>cutoff_i or i-last<30:continue
        d=core.future_dd(rows,i,20)
        if d is None or d>-.12:continue
        pre=[]
        for lead in (20,10,5,0):
            target=max(0,i-lead); cand=[x for x in eligible if x['i']<=target]
            if cand:
                x=cand[-1]; pre.append({'lead':lead,'date':x['date'],'technical':x['technical'],'close':x['close'],'drivers':x.get('technicalDrivers',{})})
        out.append({'signalDate':f['date'],'startClose':f['close'],'forwardDrawdown20':d,'preSignals':pre}); last=i
    out.sort(key=lambda x:x['forwardDrawdown20']); return out[:8]

def detail(symbol,q):
    symbol=clean_symbol(symbol)
    if not symbol:raise ValueError('Invalid symbol')
    asof=q.get('asof',[None])[0] or None; start=q.get('from',[None])[0] or None; end=q.get('to',[None])[0] or None
    rows,audit=load_rows(symbol)
    if end:rows=[r for r in rows if r['date']<=end]
    if len(rows)<MIN_DETAIL_ROWS:raise RuntimeError(f'{symbol}: only {len(rows)} completed sessions before selected TO date')
    cur,hz,fs=core.technical_state(rows,asof); market=safe_market(asof); macro=safe_macro(); sent=safe_sentiment(symbol,asof,45); fund=safe_fundamental(symbol,historical=bool(asof))
    mods={'technical':{'score':cur['technical'],'available':True,'drivers':cur.get('technicalDrivers',{})},'analog':hz['20'],'market':market,'macro':macro,'sentiment':sent,'fundamental':fund}
    score,conf=aggregate(mods); phase,color,state=classify(score,cur,conf); view=[r for r in rows if not start or r['date']>=start]; cutoff_i=cur['i']
    price_label=f"{audit.get('source')} · {audit.get('provider')}"
    hist=[]
    for f in fs:
        if f['i']>cutoff_i or (start and f['date']<start):continue
        hist.append({'date':f['date'],'technical':f['technical'],'close':f.get('close'),'mom20':f.get('mom20'),'dd60':f.get('dd60'),'trend50':f.get('trend50'),'trend200':f.get('trend200'),'rsi14':f.get('rsi14'),'volPct':f.get('volPct'),'macdNorm':f.get('macdNorm'),'volumeZ':f.get('volumeZ'),'drivers':f.get('technicalDrivers',{})})
    return {'version':VERSION,'policyVersion':POLICY.get('version'),'mode':'detail','symbol':symbol,'name':core.NAMES.get(symbol,symbol),'request':{'from':start,'to':end,'asOf':asof},'fetchedAt':datetime.now(timezone.utc).isoformat(),'modelAsOf':cur['date'],'quote':None,'score':score,'confidence':conf,'phase':phase,'color':color,'state':state,'effectiveScore':score,'liveOverlay':{'available':False,'score':score,'intradayReturn':None},'reasons':reasons(mods),'current':cur,'horizons':hz,'modules':mods,'news':sent.get('headlines',[]),'fundamentals':fund.get('metrics',{}),'history':view[-1800:],'scoreHistory':hist,'crashReplay':replay(rows,fs,cutoff_i),'dataQuality':pct_quality(rows,audit),'warnings':[],'audit':[audit],'source':{'price':price_label,'quote':'Not used in final EOD risk model','market':'Independent VMEWS VNINDEX EOD snapshot; point-in-time Yahoo fallback for historical as-of requests','fundamental':'Vnstock Fundamental current snapshot when available','sentiment':'Google News RSS headline sentiment','macro':'Yahoo cross-asset proxies'}}

class handler(BaseHTTPRequestHandler):
    def sendj(self,code,payload):
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query); mode=q.get('mode',['scan'])[0]
        try:
            if mode=='detail':out=detail(q.get('symbol',['FPT'])[0],q)
            elif mode=='health':out={'ok':True,'version':VERSION,'policyVersion':POLICY.get('version'),'time':datetime.now(VN_TZ).isoformat(),'priceSource':'Yahoo Finance with Vnstock Unified Market fallback','marketContext':'Independent VMEWS market-context snapshot','vnstockRole':'price fallback + optional fundamentals'}
            else:out=scan(q)
            self.sendj(200,out)
        except Exception as e:self.sendj(503,{'error':'VMEWS_FINAL_REQUEST_FAILED','message':str(e),'type':type(e).__name__,'version':VERSION,'retryable':True})
