import os, pathlib, importlib.util, json, math, re
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ['VNSTOCK_DATA_DIR']='/tmp/.vnstock'
os.environ['HOME']='/tmp'
os.environ['USERPROFILE']='/tmp'
os.environ['XDG_CACHE_HOME']='/tmp/.cache'
os.environ['XDG_CONFIG_HOME']='/tmp/.config'
os.environ['XDG_DATA_HOME']='/tmp/.local/share'
for p in ['/tmp/.vnstock','/tmp/.vnstock/id','/tmp/.cache','/tmp/.config','/tmp/.local/share']:
    try: os.makedirs(p,exist_ok=True)
    except Exception: pass
pathlib.Path.home=classmethod(lambda cls: cls('/tmp'))

from vnstock import Market, Fundamental
try:
    key=os.environ.get('VNSTOCK_API_KEY','').strip()
    if key:
        from vnstock import register_user
        register_user(api_key=key)
except Exception: pass

core_path=pathlib.Path(__file__).with_name('stocks.py')
spec=importlib.util.spec_from_file_location('stock_core',core_path)
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)

VERSION='STOCK-EWS-4.0.0'
VN_TZ=ZoneInfo('Asia/Ho_Chi_Minh')
MAX_HISTORY_DAYS=8*366
SCAN_MAX=8
DEFAULT_SCAN=['FPT','PNJ','VCB','HPG','MWG','VHM','SSI','DGC']

def clean_symbol(s): return re.sub('[^A-Z0-9]','',str(s or '').upper())[:8]
def parse_date(x,default=None):
    try:return date.fromisoformat(str(x)[:10]) if x else default
    except Exception:return default

def flat(df):
    if df is None or getattr(df,'empty',True):return None
    fr=df.copy()
    try:fr=fr.reset_index()
    except Exception:pass
    fr.columns=['_'.join(str(y) for y in x if str(y)) if isinstance(x,tuple) else str(x) for x in fr.columns]
    fr.columns=[x.strip().lower().replace(' ','_') for x in fr.columns]
    return fr

def col(fr,names):
    for n in names:
        if n in fr.columns:return n
    for c in fr.columns:
        for n in names:
            if c.endswith('_'+n) or n in c:return c
    return None

def normalize_ohlcv(df):
    fr=flat(df)
    if fr is None:return []
    tc=col(fr,['time','date','datetime','trading_date','index']);cc=col(fr,['close','price','index_value']);oc=col(fr,['open']);hc=col(fr,['high']);lc=col(fr,['low']);vc=col(fr,['volume','match_volume','total_volume'])
    if not tc or not cc:raise ValueError(f'Unexpected Vnstock OHLCV schema: {list(fr.columns)}')
    out=[]
    for _,r in fr.iterrows():
        try:
            close=float(r.get(cc));raw=r.get(tc);d=raw.isoformat()[:10] if hasattr(raw,'isoformat') else str(raw)[:10]
            if not math.isfinite(close) or close<=0 or len(d)!=10:continue
            def n(c,default):
                if not c:return default
                try:
                    v=float(r.get(c));return v if math.isfinite(v) else default
                except:return default
            out.append({'date':d,'open':n(oc,close),'high':n(hc,close),'low':n(lc,close),'close':close,'volume':n(vc,0.0)})
        except Exception:pass
    ded={r['date']:r for r in out};return [ded[k] for k in sorted(ded)]

def normalize_quote(df):
    fr=flat(df)
    if fr is None or len(fr)==0:return None
    r=fr.iloc[-1];pc=col(fr,['price','match_price','last','close','index_value','value']);tc=col(fr,['time','datetime','date','trading_date'])
    try:last=float(r.get(pc))
    except:return None
    if not math.isfinite(last):return None
    q={'last':last}
    if tc:
        raw=r.get(tc);q['time']=raw.isoformat() if hasattr(raw,'isoformat') else str(raw)
    return q

def strip_intraday(rows):
    if not rows:return rows,False
    now=datetime.now(VN_TZ)
    if rows[-1]['date']==now.date().isoformat() and (now.hour<15 or (now.hour==15 and now.minute<20)):return rows[:-1],True
    return rows,False

def business_days(a,b):
    n=0
    while a<=b:
        if a.weekday()<5:n+=1
        a+=timedelta(days=1)
    return n

def quality(rows,start,end,audit,intraday=False):
    if not rows:return {'status':'FAIL','rows':0,'coverageRatio':0,'requestAudit':audit}
    a=max(start,date.fromisoformat(rows[0]['date']));b=min(end,date.fromisoformat(rows[-1]['date']));exp=max(1,business_days(a,b));obs=sum(a<=date.fromisoformat(r['date'])<=b for r in rows);ratio=obs/exp
    gaps=sum((date.fromisoformat(y['date'])-date.fromisoformat(x['date'])).days>14 for x,y in zip(rows,rows[1:]))
    return {'status':'PASS' if ratio>=.72 and len(rows)>=220 and gaps<=3 else 'REVIEW','rows':len(rows),'start':rows[0]['date'],'end':rows[-1]['date'],'coverageRatio':min(1,ratio),'largeGaps':gaps,'intradayBarExcluded':intraday,'requestAudit':audit}

def fetch_history(symbol,start,end,segmented=True,index=False):
    obj=Market().index('VNINDEX') if index else Market().equity(clean_symbol(symbol));audit=[];allrows=[]
    if not segmented or (end-start).days<=430:windows=[(start,end)]
    else:
        windows=[];cur=start
        while cur<=end:
            nxt=min(end,cur+timedelta(days=370));windows.append((cur,nxt));cur=nxt+timedelta(days=1)
    for a,b in windows:
        try:
            rows=normalize_ohlcv(obj.ohlcv(start=a.isoformat(),end=(b+timedelta(days=1)).isoformat(),interval='1D'));allrows+=rows;audit.append({'source':'Vnstock','provider':'KBS','type':'index.ohlcv' if index else 'equity.ohlcv','symbol':'VNINDEX' if index else clean_symbol(symbol),'start':a.isoformat(),'end':b.isoformat(),'rows':len(rows),'ok':True})
        except Exception as e:audit.append({'source':'Vnstock','provider':'KBS','type':'ohlcv','symbol':'VNINDEX' if index else clean_symbol(symbol),'start':a.isoformat(),'end':b.isoformat(),'rows':0,'ok':False,'error':str(e)[:160]})
    ded={r['date']:r for r in allrows};rows=[ded[k] for k in sorted(ded)];rows,intraday=strip_intraday(rows)
    if len(rows)<80:raise RuntimeError(f'Vnstock returned only {len(rows)} usable rows for {"VNINDEX" if index else symbol}')
    return rows,audit,intraday

def quote_now(symbol=None,index=False):
    try:
        obj=Market().index('VNINDEX') if index else Market().equity(clean_symbol(symbol));q=normalize_quote(obj.quote());return q,{'source':'Vnstock','provider':'KBS','type':'index.quote' if index else 'equity.quote','symbol':'VNINDEX' if index else clean_symbol(symbol),'ok':bool(q)}
    except Exception as e:return None,{'source':'Vnstock','provider':'KBS','type':'quote','symbol':'VNINDEX' if index else clean_symbol(symbol),'ok':False,'error':str(e)[:160]}

def analog_pt(rows,fs,current,h):
    cutoff=current['i'];cand=[f for f in fs if f['i']+max(60,h)<=cutoff and f['i']<cutoff-60]
    if len(cand)<80:return {'score':50,'rate':None,'threshold':None,'matches':0,'available':False,'reason':'Insufficient point-in-time analog history'}
    keys=['vol20','dd60','mom20','trend50','trend200','rsi14','macdNorm','volumeZ'];stats={k:(core.mean([f[k] for f in cand]),core.sd([f[k] for f in cand]) or 1) for k in keys};rank=[]
    for f in cand:rank.append((math.sqrt(sum(((f[k]-current[k])/stats[k][1])**2 for k in keys)/len(keys)),f))
    rank.sort(key=lambda x:x[0]);near=rank[:40];dds=[core.future_dd(rows,f['i'],h) for f in cand];dds=[x for x in dds if x is not None];thr=min(-.10,core.pctile(dds,.05));events=[];examples=[]
    for dist,f in near:
        d=core.future_dd(rows,f['i'],h)
        if d is None:continue
        ev=d<=thr;events.append(1 if ev else 0)
        if len(examples)<5:examples.append({'date':f['date'],'similarity':1/(1+dist),'forwardDrawdown':d,'event':ev})
    rate=core.mean(events) if events else 0
    return {'score':100*core.clamp(rate/.30),'rate':rate,'threshold':thr,'matches':len(events),'available':True,'examples':examples}

def state_from_rows(rows,asof=None):
    fs=core.features(rows)
    if not fs:raise ValueError('At least ~200 completed sessions are required')
    eligible=[f for f in fs if not asof or f['date']<=asof]
    if not eligible:raise ValueError(f'No model observation on or before {asof}')
    cur=eligible[-1];hz={str(h):analog_pt(rows,fs,cur,h) for h in (5,20,60)};return cur,hz,fs

def macro_asof(asof=None):
    specs={'VIX':'^VIX','USDVND':'USDVND=X','DXY':'DX-Y.NYB','US10Y':'^TNX','BRENT':'BZ=F'};data={};press=[]
    def one(k,s):
        rows,_,_=core.yahoo_chart(s,'10y' if asof else '1y',7);rows=[r for r in rows if not asof or r['date']<=asof];c=[r['close'] for r in rows]
        if len(c)<21:raise RuntimeError('not enough macro rows')
        return k,{'last':c[-1],'ret20':c[-1]/c[-21]-1,'ret5':c[-1]/c[-6]-1,'date':rows[-1]['date']}
    with ThreadPoolExecutor(max_workers=5) as ex:
        for f in as_completed([ex.submit(one,k,s) for k,s in specs.items()]):
            try:k,v=f.result();data[k]=v
            except Exception:pass
    if 'VIX' in data:press.append(core.clamp((data['VIX']['last']-17)/20))
    if 'USDVND' in data:press.append(core.clamp(max(0,data['USDVND']['ret20'])/.025))
    if 'DXY' in data:press.append(core.clamp(max(0,data['DXY']['ret20'])/.04))
    if 'US10Y' in data:press.append(core.clamp(max(0,data['US10Y']['ret20'])/.08))
    if 'BRENT' in data:press.append(core.clamp(abs(data['BRENT']['ret20'])/.18))
    return {'score':100*core.mean(press) if press else 50,'available':bool(press),'factors':data,'note':'Cross-asset proxies; full macro domain requires Vnstock Data/Sponsor.'}

def fund_quick(symbol):
    try:
        eq=Fundamental().equity(clean_symbol(symbol))
        try:df=eq.ratio(orient='time_series')
        except Exception:df=eq.ratio()
        fr=flat(df)
        if fr is None or len(fr)==0:return {'score':50,'available':False,'metrics':{},'reason':'No Vnstock ratio rows'}
        if 'year' in fr.columns:
            try:
                sortcols=['year']+(['quarter'] if 'quarter' in fr.columns else []);fr=fr.sort_values(sortcols)
            except Exception:pass
        r=fr.iloc[-1]
        def m(names):
            c=col(fr,names)
            if not c:return None
            try:
                v=float(r.get(c));return v if math.isfinite(v) else None
            except:return None
        vals={'pe':m(['pricetoearning','price_to_earning','pe_ratio','pe']),'pb':m(['pricetobook','price_to_book','pb_ratio','pb']),'roe':m(['roe','return_on_equity']),'roa':m(['roa','return_on_assets']),'debtToEquity':m(['debt_to_equity','debttoequity']),'netMargin':m(['profit_margin','net_profit_margin','netmargin'])}
        ps=[]
        if vals['roe'] is not None:
            v=vals['roe']/100 if abs(vals['roe'])>2 else vals['roe'];ps.append(core.clamp((.12-v)/.18))
        if vals['pe'] is not None and vals['pe']>0:ps.append(core.clamp((vals['pe']-18)/30))
        if vals['debtToEquity'] is not None:
            v=vals['debtToEquity']/100 if vals['debtToEquity']>10 else vals['debtToEquity'];ps.append(core.clamp((v-.7)/2))
        if vals['netMargin'] is not None:
            v=vals['netMargin']/100 if abs(vals['netMargin'])>2 else vals['netMargin'];ps.append(core.clamp((.08-v)/.15))
        return {'score':100*core.mean(ps) if ps else 50,'available':len(ps)>=2,'metrics':vals,'rows':len(fr),'source':'Vnstock Fundamental.ratio'}
    except Exception as e:return {'score':50,'available':False,'metrics':{},'error':str(e)[:160]}

def market_module(start,end,asof=None):
    rows,audit,intraday=fetch_history('VNINDEX',start,end,segmented=False,index=True);cur,hz,_=state_from_rows(rows,asof);a=hz['20'];score=.65*cur['technical']+.35*(a['score'] if a.get('available') else 50);return {'score':score,'available':True,'technical':cur['technical'],'analog20':a,'date':cur['date'],'audit':audit,'intradayBarExcluded':intraday}

def aggregate(mods):
    w={'technical':.30,'analog':.25,'market':.15,'macro':.10,'sentiment':.10,'fundamental':.10};total=used=0
    for k,wt in w.items():
        m=mods.get(k) or {}
        if m.get('available',True) and isinstance(m.get('score'),(int,float)):total+=wt*m['score'];used+=wt
    return (total/used if used else 50),used

def overlay(score,cur,q):
    if not q:return {'available':False,'score':score,'intradayReturn':None}
    r=q['last']/cur['close']-1;shock=core.clamp(max(0,-r)/.05);return {'available':True,'score':.85*score+.15*shock*100,'intradayReturn':r,'last':q['last'],'time':q.get('time'),'shockPressure':shock}

def classify(score,cur,conf,ov):
    eff=ov['score'] if ov.get('available') else score;dd=cur['dd60'];weak=cur['mom20']<0 or cur['trend50']<0
    if dd<=-.15:return {'phase':'ACTIVE_DRAWDOWN','color':'GRAY','state':'DRAWDOWN','effectiveScore':eff}
    if eff>=70 and weak and conf>=.70:return {'phase':'PRE_CRASH_RED','color':'RED','state':'HIGH','effectiveScore':eff}
    if eff>=55 and weak and conf>=.55:return {'phase':'PRE_CRASH_YELLOW','color':'YELLOW','state':'WATCH','effectiveScore':eff}
    return {'phase':'NORMAL','color':'GREEN','state':'CLEAR','effectiveScore':eff}

def reasons(mods):
    labels={'technical':'Technical','analog':'Historical analog','market':'VNINDEX regime','macro':'Macro/cross-asset','sentiment':'News sentiment','fundamental':'Fundamentals'};x=[]
    for k,m in mods.items():
        if m.get('available',True) and isinstance(m.get('score'),(int,float)):x.append((m['score'],labels[k]))
    x.sort(reverse=True);return [f'{name} {s:.0f}/100' for s,name in x[:4]]

def crash_events_pt(rows,fs,cutoff):
    events=[];last=-999
    for f in fs:
        i=f['i']
        if i+20>cutoff or i-last<30:continue
        d=core.future_dd(rows,i,20)
        if d is None or d>-.12:continue
        pre=[]
        for lead in (20,10,5,0):
            target=max(0,i-lead);cand=[x for x in fs if x['i']<=target]
            if cand:
                x=cand[-1];pre.append({'lead':lead,'date':x['date'],'technical':x['technical'],'close':x['close'],'drivers':x['technicalDrivers']})
        events.append({'signalDate':f['date'],'startClose':f['close'],'forwardDrawdown20':d,'preSignals':pre,'replayScope':'point-in-time technical replay'});last=i
    events.sort(key=lambda x:x['forwardDrawdown20']);return events[:8]

def resolve(q):
    today=datetime.now(VN_TZ).date();to=min(parse_date(q.get('to',[None])[0],today),today);frm=parse_date(q.get('from',[None])[0],to-timedelta(days=3*366));floor=today-timedelta(days=MAX_HISTORY_DAYS);warn=[]
    if frm<floor:warn.append('Requested history was clamped to the approximately 8-year Vnstock Community limit.');frm=floor
    if frm>to:raise ValueError('FROM must be <= TO')
    asof=parse_date(q.get('asof',[None])[0]);asof=min(max(asof,frm),to) if asof else None;warm=max(floor,frm-timedelta(days=520));return frm,to,warm,asof,warn

def detail(symbol,q):
    symbol=clean_symbol(symbol);frm,to,warm,asof,warnings=resolve(q);rows,audit,intraday=fetch_history(symbol,warm,to,True,False);cur,hz,fs=state_from_rows(rows,asof.isoformat() if asof else None);model_date=parse_date(cur['date']);mstart=max(warm,model_date-timedelta(days=3*366))
    with ThreadPoolExecutor(max_workers=4) as ex:
        fm=ex.submit(market_module,mstart,to,asof.isoformat() if asof else None);fx=ex.submit(macro_asof,asof.isoformat() if asof else None);news_end=asof or to;news_days=max(7,min(120,(news_end-frm).days+1));fn=ex.submit(core.sentiment_module,symbol,news_end.isoformat(),news_days,20);ff=ex.submit(fund_quick,symbol) if not asof else None
        market=fm.result();macro=fx.result();sent=fn.result();fund=ff.result() if ff else {'score':50,'available':False,'metrics':{},'note':'Historical fundamentals excluded to prevent look-ahead bias.'}
    qnow=None
    if not asof and to>=datetime.now(VN_TZ).date():qnow,qa=quote_now(symbol);audit.append(qa)
    mods={'technical':{'score':cur['technical'],'available':True,'drivers':cur['technicalDrivers']},'analog':hz['20'],'market':market,'macro':macro,'sentiment':sent,'fundamental':fund};score,conf=aggregate(mods);ov=overlay(score,cur,qnow);cl=classify(score,cur,conf,ov);view=[r for r in rows if frm.isoformat()<=r['date']<=to.isoformat()]
    return {'version':VERSION,'mode':'detail','symbol':symbol,'name':core.NAMES.get(symbol,symbol),'request':{'from':frm.isoformat(),'to':to.isoformat(),'asOf':asof.isoformat() if asof else None,'fetchWarmupFrom':warm.isoformat()},'fetchedAt':datetime.now(timezone.utc).isoformat(),'modelAsOf':cur['date'],'quote':qnow,'score':score,'confidence':conf,'phase':cl['phase'],'color':cl['color'],'state':cl['state'],'effectiveScore':cl['effectiveScore'],'liveOverlay':ov,'reasons':reasons(mods),'current':cur,'horizons':hz,'modules':mods,'news':sent.get('headlines',[]),'fundamentals':fund.get('metrics',{}),'history':view[-1800:],'scoreHistory':[{'date':f['date'],'technical':f['technical']} for f in fs if frm.isoformat()<=f['date']<=to.isoformat()],'crashReplay':crash_events_pt(rows,[f for f in fs if f['i']<=cur['i']],cur['i']),'dataQuality':quality(rows,warm,to,audit,intraday),'warnings':warnings,'source':{'price':'Vnstock v4 Market.equity().ohlcv() · KBS','quote':'Vnstock v4 Market.equity().quote() · KBS','market':'Vnstock v4 Market.index(VNINDEX)','fundamental':'Vnstock Fundamental current ratios when available','sentiment':'Google News RSS headline sentiment','macro':'Cross-asset proxies'}}

def scan_one(symbol,start,end,market,macro):
    rows,audit,intraday=fetch_history(symbol,start,end,False,False);cur,hz,_=state_from_rows(rows);mods={'technical':{'score':cur['technical'],'available':True},'analog':hz['20'],'market':market,'macro':macro,'sentiment':{'score':50,'available':False},'fundamental':{'score':50,'available':False}};score,conf=aggregate(mods);ov={'available':False,'score':score};cl=classify(score,cur,conf,ov);return {'symbol':symbol,'name':core.NAMES.get(symbol,symbol),'date':cur['date'],'close':cur['close'],'ret5':cur['ret5'],'score':score,'confidence':conf,'phase':cl['phase'],'color':cl['color'],'state':cl['state'],'effectiveScore':cl['effectiveScore'],'modules':mods,'current':cur,'audit':audit,'dataQuality':quality(rows,start,end,audit,intraday)}

def enrich(item):
    s=item['symbol'];q,qa=quote_now(s)
    with ThreadPoolExecutor(max_workers=2) as ex:fn=ex.submit(core.sentiment_module,s,None,45,20);ff=ex.submit(fund_quick,s);sent=fn.result();fund=ff.result()
    item['modules']['sentiment']=sent;item['modules']['fundamental']=fund;item['score'],item['confidence']=aggregate(item['modules']);item['quote']=q;item['liveOverlay']=overlay(item['score'],item['current'],q);cl=classify(item['score'],item['current'],item['confidence'],item['liveOverlay']);item.update({'phase':cl['phase'],'color':cl['color'],'state':cl['state'],'effectiveScore':cl['effectiveScore'],'reasons':reasons(item['modules'])});item['audit'].append(qa);return item

def scan(q):
    raw=q.get('symbols',[''])[0];symbols=[clean_symbol(x) for x in raw.split(',') if clean_symbol(x)] if raw else DEFAULT_SCAN[:];symbols=list(dict.fromkeys(symbols))[:SCAN_MAX];today=datetime.now(VN_TZ).date();start=today-timedelta(days=3*366)
    with ThreadPoolExecutor(max_workers=2) as ex:fm=ex.submit(market_module,start,today,None);fx=ex.submit(macro_asof,None);market=fm.result();macro=fx.result()
    items=[];errors=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut={ex.submit(scan_one,s,start,today,market,macro):s for s in symbols}
        for f in as_completed(fut):
            try:items.append(f.result())
            except Exception as e:errors.append({'symbol':fut[f],'error':str(e)[:160]})
    items.sort(key=lambda x:x['score'],reverse=True);by={x['symbol']:x for x in items};targets=[x['symbol'] for x in items[:2]]
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut={ex.submit(enrich,by[s]):s for s in targets}
        for f in as_completed(fut):
            try:by[fut[f]]=f.result()
            except Exception as e:errors.append({'symbol':fut[f],'stage':'enrich','error':str(e)[:160]})
    ranking=sorted(by.values(),key=lambda x:x.get('effectiveScore',x['score']),reverse=True)
    for x in ranking:
        if 'reasons' not in x:x['reasons']=reasons(x['modules'])
    return {'version':VERSION,'mode':'scan','asOf':datetime.now(VN_TZ).isoformat(),'universeSize':len(core.UNIVERSE),'requestedSymbols':symbols,'scanned':len(ranking),'redList':[x for x in ranking if x['color']=='RED'],'yellowList':[x for x in ranking if x['color']=='YELLOW'],'greenList':[x for x in ranking if x['color']=='GREEN'],'activeDrawdown':[x for x in ranking if x['phase']=='ACTIVE_DRAWDOWN'],'ranking':ranking,'market':market,'macro':macro,'errors':errors,'scanPolicy':{'maxSymbolsPerRequest':SCAN_MAX,'enrichedTopN':2,'priceSource':'Vnstock KBS','reason':'Request-rate protection'}}

class handler(BaseHTTPRequestHandler):
    def sendj(self,code,payload):
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query);mode=q.get('mode',['scan'])[0]
        try:
            if mode=='detail':self.sendj(200,detail(q.get('symbol',['FPT'])[0],q))
            elif mode=='health':self.sendj(200,{'ok':True,'version':VERSION,'time':datetime.now(VN_TZ).isoformat(),'priceSource':'Vnstock v4/KBS','maxScanSymbols':SCAN_MAX})
            else:self.sendj(200,scan(q))
        except Exception as e:self.sendj(503,{'error':'STOCK_EWS_REQUEST_FAILED','message':str(e),'version':VERSION,'priceSource':'Vnstock v4/KBS','retryable':True})
