import os, pathlib, importlib.util
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Vercel/Vnstock writable bootstrap before loading the stock core.
os.environ['VNSTOCK_DATA_DIR']='/tmp/.vnstock'
os.environ['HOME']='/tmp'
os.environ['USERPROFILE']='/tmp'
os.environ['XDG_CACHE_HOME']='/tmp/.cache'
os.environ['XDG_CONFIG_HOME']='/tmp/.config'
for p in ['/tmp/.vnstock','/tmp/.vnstock/id','/tmp/.cache','/tmp/.config']:
    try: os.makedirs(p, exist_ok=True)
    except Exception: pass
pathlib.Path.home = classmethod(lambda cls: cls('/tmp'))

core_path=pathlib.Path(__file__).with_name('stocks.py')
spec=importlib.util.spec_from_file_location('stock_ews_core', core_path)
core=importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
VERSION='STOCK-EWS-3.1.0'


def phase(score,current):
    dd=float(current.get('dd60') or 0); mom=float(current.get('mom20') or 0); t50=float(current.get('trend50') or 0)
    if dd <= -.15: return 'ACTIVE_DRAWDOWN'
    if score >= 70 and mom < 0 and t50 < 0: return 'PRE_CRASH_RED'
    if score >= 55 and (mom < 0 or t50 < 0): return 'PRE_CRASH_GOLD'
    if dd <= -.08 and mom > 0: return 'RECOVERY'
    return 'NORMAL'


def _asof_rows(rows,asof):
    if not asof:return rows
    x=[r for r in rows if r['date']<=asof]
    return x if x else rows[:1]


def macro_asof(asof=None):
    specs={'vix':'^VIX','usdVnd':'USDVND=X','dxy':'DX-Y.NYB','us10y':'^TNX','brent':'BZ=F'}
    data={}; pressure=[]
    for k,s in specs.items():
        try:
            rows,_,_=core.yahoo_chart(s,'10y' if asof else '6mo',timeout=7); rows=_asof_rows(rows,asof); c=[r['close'] for r in rows]
            if len(c)<22:continue
            d={'last':c[-1],'ret20':c[-1]/c[-21]-1,'ret5':c[-1]/c[-6]-1,'date':rows[-1]['date']};data[k]=d
        except Exception: pass
    if 'vix' in data: pressure.append(core.clamp((data['vix']['last']-17)/20))
    if 'usdVnd' in data: pressure.append(core.clamp(max(0,data['usdVnd']['ret20'])/.025))
    if 'dxy' in data: pressure.append(core.clamp(max(0,data['dxy']['ret20'])/.04))
    if 'us10y' in data: pressure.append(core.clamp(max(0,data['us10y']['ret20'])/.08))
    if 'brent' in data: pressure.append(core.clamp(abs(data['brent']['ret20'])/.18))
    return {'score':100*core.mean(pressure) if pressure else 50,'available':bool(pressure),'factors':data,'asOf':asof}


def market_asof(asof=None):
    rows,_,_=core.yahoo_chart('^VNINDEX.VN','10y' if asof else '3y',timeout=8); rows=_asof_rows(rows,asof)
    cur,an,_=core.technical_state(rows)
    return {'score':.65*cur['technical']+.35*an['20']['score'],'technical':cur['technical'],'analog20':an['20'],'date':cur['date'],'available':True,'asOf':asof}


def stock_detail(symbol,asof=None,start=None,end=None):
    symbol=''.join(c for c in symbol.upper() if c.isalnum())[:8]
    if not symbol:raise ValueError('Invalid symbol')
    rows,_,_=core.yahoo_chart(symbol,'10y',timeout=12)
    if end:rows=[r for r in rows if r['date']<=end]
    cur,an,fs=core.technical_state(rows,asof)
    market=market_asof(asof);macro=macro_asof(asof);sent=core.sentiment_module(symbol,asof)
    # Historical replay excludes today's financial statements to avoid look-ahead bias.
    fund={'score':50,'available':False,'metrics':{},'note':'Point-in-time fundamentals excluded from historical replay.'} if asof else core.fundamental_module(symbol)
    mods={'technical':{'score':cur['technical'],'available':True,'drivers':cur['technicalDrivers']},'analog':an['20'],'market':market,'macro':macro,'sentiment':sent,'fundamental':fund}
    score,conf=core.aggregate(mods); view=rows if not start else [r for r in rows if r['date']>=start]
    return {'version':VERSION,'symbol':symbol,'name':core.NAMES.get(symbol,symbol),'requestedAsOf':asof,'modelAsOf':cur['date'],'score':score,'state':core.state(score),'phase':phase(score,cur),'confidence':conf,'reasons':core.explain(mods),'modules':mods,'current':cur,'horizons':an,'news':sent.get('headlines',[]),'history':view[-1600:],'scoreHistory':[{'date':f['date'],'technical':f['technical']} for f in fs if not start or f['date']>=start],'crashReplay':core.crash_events(rows,fs),'source':{'price':'Yahoo Finance broad history adapter','sentiment':'Google News RSS lexical sentiment','fundamental':'Vnstock Fundamental (current only)','macro':'Cross-asset market proxies','market':'VNINDEX'}}


def stock_scan(limit=22):
    p=core.scan(max(limit,30)); ranking=p.get('ranking',[])
    for x in ranking:x['phase']=phase(x.get('score',0),x.get('current') or {})
    confirmed=[x for x in ranking if x.get('confidence',0)>=.85]
    p['version']=VERSION;p['ranking']=ranking[:limit]
    p['redList']=[x for x in confirmed if x['phase']=='PRE_CRASH_RED'][:10]
    p['goldList']=[x for x in confirmed if x['phase']=='PRE_CRASH_GOLD'][:10]
    p['activeDrawdown']=[x for x in confirmed if x['phase']=='ACTIVE_DRAWDOWN'][:10]
    p['phaseDefinition']={'PRE_CRASH_RED':'high composite risk + negative momentum + below MA50, before a 15% 60D drawdown has already occurred','PRE_CRASH_GOLD':'elevated composite risk with early momentum/trend weakness','ACTIVE_DRAWDOWN':'already at least 15% below the recent 60D peak','RECOVERY':'still deeply below the peak but 20D momentum has turned positive'}
    return p


class handler(BaseHTTPRequestHandler):
    def _json(self,code,payload,cache):
        import json
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Cache-Control',cache);self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query);mode=q.get('mode',['scan'])[0]
        try:
            if mode=='detail':
                self._json(200,stock_detail(q.get('symbol',['FPT'])[0],q.get('asof',[None])[0],q.get('from',[None])[0],q.get('to',[None])[0]),'s-maxage=90, stale-while-revalidate=180')
            elif mode=='health':self._json(200,{'ok':True,'version':VERSION,'universe':len(core.UNIVERSE),'time':datetime.now(core.VN_TZ).isoformat()},'no-store')
            else:self._json(200,stock_scan(min(30,max(5,int(q.get('limit',['22'])[0])))),'s-maxage=90, stale-while-revalidate=180')
        except Exception as e:self._json(503,{'error':'STOCK_EWS_V31_FAILED','message':str(e),'version':VERSION},'no-store')
