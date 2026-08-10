import os, pathlib, json, math, statistics, time, re
from datetime import datetime, timezone, date, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote_plus, quote
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET

os.environ['VNSTOCK_DATA_DIR']='/tmp/.vnstock'
os.environ['HOME']='/tmp'
os.environ['USERPROFILE']='/tmp'
os.environ['XDG_CACHE_HOME']='/tmp/.cache'
os.environ['XDG_CONFIG_HOME']='/tmp/.config'
for p in ['/tmp/.vnstock','/tmp/.vnstock/id','/tmp/.cache','/tmp/.config']:
    try: os.makedirs(p, exist_ok=True)
    except Exception: pass
pathlib.Path.home = classmethod(lambda cls: cls('/tmp'))

VERSION='STOCK-EWS-3.0.0'
VN_TZ=timezone(timedelta(hours=7))
UNIVERSE=['FPT','PNJ','VCB','BID','CTG','MBB','TCB','VPB','ACB','HDB','STB','TPB','VIB','SHB','HPG','DGC','GVR','MSN','MWG','VNM','VIC','VHM','VRE','BCM','KDH','KBC','PDR','DXG','NLG','DIG','GAS','PLX','VJC','SAB','SSI','VCI','HCM']
NAMES={'FPT':'FPT Corporation','PNJ':'Phu Nhuan Jewelry','VCB':'Vietcombank','BID':'BIDV','CTG':'VietinBank','MBB':'MB Bank','TCB':'Techcombank','VPB':'VPBank','ACB':'ACB','HDB':'HDBank','STB':'Sacombank','TPB':'TPBank','VIB':'VIB','SHB':'SHB','HPG':'Hoa Phat','DGC':'Duc Giang Chemicals','GVR':'Vietnam Rubber Group','MSN':'Masan Group','MWG':'Mobile World','VNM':'Vinamilk','VIC':'Vingroup','VHM':'Vinhomes','VRE':'Vincom Retail','BCM':'Becamex IDC','KDH':'Khang Dien House','KBC':'Kinh Bac City','PDR':'Phat Dat Real Estate','DXG':'Dat Xanh Group','NLG':'Nam Long','DIG':'DIC Corp','GAS':'PV Gas','PLX':'Petrolimex','VJC':'VietJet Air','SAB':'Sabeco','SSI':'SSI Securities','VCI':'Vietcap','HCM':'HSC'}
NEG_WORDS=['khởi tố','bắt giữ','điều tra','vi phạm','xử phạt','truy thu','thua lỗ','báo lỗ','lỗ ròng','giảm mạnh','lao dốc','sụt giảm','bán tháo','cắt giảm','hủy','nợ xấu','vỡ nợ','cảnh báo','rủi ro','suy giảm','đóng cửa','trì hoãn','downgrade','sell','fraud','investigation','loss','decline','slump','warning','risk','miss']
POS_WORDS=['tăng trưởng','lợi nhuận tăng','lãi tăng','kỷ lục','mở rộng','trúng thầu','nâng hạng','khuyến nghị mua','vượt kế hoạch','tăng mạnh','record','growth','profit rises','upgrade','buy','beat','outperform']

def clamp(x,a=0.0,b=1.0): return max(a,min(b,x))
def mean(a): return sum(a)/len(a) if a else 0.0
def sd(a): return statistics.stdev(a) if len(a)>1 else 0.0
def pctile(a,p):
    x=sorted(v for v in a if isinstance(v,(int,float)) and math.isfinite(v))
    if not x:return 0.0
    pos=clamp(p)*(len(x)-1); lo=int(pos); hi=min(len(x)-1,lo+1); w=pos-lo
    return x[lo]*(1-w)+x[hi]*w

def rank_pct(v,h):
    h=[x for x in h if isinstance(x,(int,float)) and math.isfinite(x)]
    return sum(x<=v for x in h)/len(h) if h else .5

def yahoo_chart(symbol, range_value='3y', timeout=10):
    ys=symbol if symbol.startswith('^') or '=' in symbol or symbol.endswith('.VN') else f'{symbol}.VN'
    last=None
    for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
        try:
            u=f'https://{host}/v8/finance/chart/{quote(ys)}?interval=1d&includePrePost=false&events=div%2Csplits&range={range_value}'
            req=Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS/3.0','Accept':'application/json'})
            with urlopen(req,timeout=timeout) as r: payload=json.loads(r.read().decode())
            res=(payload.get('chart',{}).get('result') or [None])[0]
            if not res: raise RuntimeError(str(payload.get('chart',{}).get('error')))
            ts=res.get('timestamp') or []; qd=((res.get('indicators') or {}).get('quote') or [{}])[0]
            rows=[]
            for i,t in enumerate(ts):
                try:
                    c=float((qd.get('close') or [])[i])
                    if not math.isfinite(c) or c<=0: continue
                    def n(k,d):
                        try:
                            v=float((qd.get(k) or [])[i]); return v if math.isfinite(v) else d
                        except: return d
                    rows.append({'date':datetime.fromtimestamp(t,timezone.utc).date().isoformat(),'open':n('open',c),'high':n('high',c),'low':n('low',c),'close':c,'volume':n('volume',0.0)})
                except: pass
            ded={r['date']:r for r in rows}; rows=[ded[k] for k in sorted(ded)]
            if len(rows)<80: raise RuntimeError(f'{ys}: only {len(rows)} rows')
            return rows,res.get('meta') or {},host
        except Exception as e: last=e
    raise RuntimeError(f'{ys}: {last}')

def sma(x,n,i): return mean(x[max(0,i-n+1):i+1])
def ema_series(x,n):
    a=2/(n+1); out=[]; e=None
    for v in x:
        e=v if e is None else a*v+(1-a)*e; out.append(e)
    return out

def rsi14(closes,i):
    if i<14:return 50.0
    gains=[];loss=[]
    for j in range(i-13,i+1):
        d=closes[j]-closes[j-1]; gains.append(max(d,0)); loss.append(max(-d,0))
    ag=mean(gains); al=mean(loss)
    return 100.0 if al<1e-12 else 100-100/(1+ag/al)

def features(rows):
    closes=[r['close'] for r in rows]; vols=[r.get('volume',0) for r in rows]
    rets=[0.0]+[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
    e12=ema_series(closes,12); e26=ema_series(closes,26); macd=[a-b for a,b in zip(e12,e26)]; sig=ema_series(macd,9)
    vol20=[sd(rets[max(1,i-19):i+1])*math.sqrt(252) for i in range(len(rows))]
    out=[]
    for i in range(200,len(rows)):
        c=closes[i]; peak=max(closes[i-59:i+1]); dd=c/peak-1; mom20=c/closes[i-20]-1; ret5=c/closes[i-5]-1
        ma50=sma(closes,50,i); ma200=sma(closes,200,i); trend50=c/ma50-1; trend200=c/ma200-1
        rs=rsi14(closes,i); mh=(macd[i]-sig[i])/c if c else 0
        histv=vol20[max(200,i-252):i]; vp=rank_pct(vol20[i],histv)
        vh=[v for v in vols[max(1,i-20):i] if v>0]; vz=(vols[i]-mean(vh))/(sd(vh) or 1) if vols[i]>0 and vh else 0
        p_dd=clamp(abs(min(dd,0))/.22); p_mom=clamp(abs(min(mom20,0))/.14); p_t50=clamp(abs(min(trend50,0))/.12); p_t200=clamp(abs(min(trend200,0))/.18)
        p_vol=clamp((vp-.45)/.55); p_rsi=clamp((45-rs)/20); p_macd=clamp(max(0,-mh)/.025); p_volume=clamp(max(0,vz)/3.0)*clamp(max(0,-rets[i])/.05)
        tech=100*(.18*p_dd+.16*p_mom+.14*p_t50+.10*p_t200+.16*p_vol+.10*p_rsi+.08*p_macd+.08*p_volume)
        out.append({'i':i,'date':rows[i]['date'],'close':c,'ret1':rets[i],'ret5':ret5,'dd60':dd,'mom20':mom20,'trend50':trend50,'trend200':trend200,'vol20':vol20[i],'volPct':vp,'rsi14':rs,'macdNorm':mh,'volumeZ':vz,'technical':tech,'technicalDrivers':{'drawdown60':p_dd,'momentum20':p_mom,'ma50Break':p_t50,'ma200Break':p_t200,'volatilityRegime':p_vol,'rsiWeakness':p_rsi,'macdWeakness':p_macd,'volumeSelloff':p_volume}})
    return out

def future_dd(rows,i,h):
    if i+h>=len(rows):return None
    base=rows[i]['close']; return min(rows[j]['close']/base-1 for j in range(i+1,i+h+1))

def analog_module(rows,fs,current,h=20):
    cand=[f for f in fs if f['i']+60<len(rows) and f['i']<current['i']-60]
    if len(cand)<80:return {'score':50,'rate':None,'threshold':None,'matches':0,'available':False}
    keys=['vol20','dd60','mom20','trend50','trend200','rsi14','macdNorm','volumeZ']
    stat={k:(mean([f[k] for f in cand]),sd([f[k] for f in cand]) or 1.0) for k in keys}
    ranks=[]
    for f in cand:
        d=sum(((f[k]-current[k])/stat[k][1])**2 for k in keys)/len(keys); ranks.append((math.sqrt(d),f))
    ranks.sort(key=lambda x:x[0]); near=ranks[:40]
    all_dd=[future_dd(rows,f['i'],h) for f in cand]; all_dd=[x for x in all_dd if x is not None]
    thr=min(-.10,pctile(all_dd,.05)); events=[]
    for dist,f in near:
        d=future_dd(rows,f['i'],h)
        if d is not None: events.append(d<=thr)
    rate=mean([1 if x else 0 for x in events]) if events else 0; score=100*clamp(rate/.30)
    examples=[]
    for dist,f in near[:5]:
        d=future_dd(rows,f['i'],h); examples.append({'date':f['date'],'similarity':1/(1+dist),'forwardDrawdown':d,'event':bool(d is not None and d<=thr)})
    return {'score':score,'rate':rate,'threshold':thr,'matches':len(events),'available':True,'examples':examples}

def technical_state(rows,asof=None):
    fs=features(rows)
    if not fs:raise ValueError('insufficient technical history')
    cur=fs[-1]
    if asof:
        eligible=[f for f in fs if f['date']<=asof]
        if not eligible:raise ValueError(f'No model observation on or before {asof}')
        cur=eligible[-1]
    return cur,{str(h):analog_module(rows,fs,cur,h) for h in (5,20,60)},fs

def macro_module():
    specs={'vix':'^VIX','usdVnd':'USDVND=X','dxy':'DX-Y.NYB','us10y':'^TNX','brent':'BZ=F'}; data={}; pressures=[]
    def one(k,s):
        rows,_,_=yahoo_chart(s,'6mo',7); c=[r['close'] for r in rows]
        return k,{'last':c[-1],'ret20':c[-1]/c[-21]-1 if len(c)>21 else 0,'ret5':c[-1]/c[-6]-1 if len(c)>6 else 0,'date':rows[-1]['date']}
    with ThreadPoolExecutor(max_workers=5) as ex:
        for f in as_completed([ex.submit(one,k,s) for k,s in specs.items()]):
            try:k,v=f.result(); data[k]=v
            except:pass
    if 'vix' in data:pressures.append(clamp((data['vix']['last']-17)/20))
    if 'usdVnd' in data:pressures.append(clamp(max(0,data['usdVnd']['ret20'])/.025))
    if 'dxy' in data:pressures.append(clamp(max(0,data['dxy']['ret20'])/.04))
    if 'us10y' in data:pressures.append(clamp(max(0,data['us10y']['ret20'])/.08))
    if 'brent' in data:pressures.append(clamp(abs(data['brent']['ret20'])/.18))
    return {'score':100*mean(pressures) if pressures else 50,'available':bool(pressures),'factors':data}

def market_module():
    rows,_,_=yahoo_chart('^VNINDEX.VN','3y',8); cur,an,_=technical_state(rows)
    return {'score':.65*cur['technical']+.35*an['20']['score'],'technical':cur['technical'],'analog20':an['20'],'date':cur['date'],'available':True}

def sentiment_module(symbol,asof=None,days=45,limit=20):
    name=NAMES.get(symbol,symbol); q=f'"{symbol}" cổ phiếu {name}'
    if asof:
        try:
            end=date.fromisoformat(asof)+timedelta(days=1); start=end-timedelta(days=days); q+=f' after:{start.isoformat()} before:{end.isoformat()}'
        except:pass
    u='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=vi&gl=VN&ceid=VN:vi'
    try:
        with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0 VMEWS/3.0'}),timeout=8) as r: root=ET.fromstring(r.read())
        items=[]
        for it in root.findall('.//item')[:limit]:
            title=(it.findtext('title') or '').strip(); low=title.lower(); pos=sum(w in low for w in POS_WORDS); neg=sum(w in low for w in NEG_WORDS); s=(pos-neg)/max(1,pos+neg)
            items.append({'title':title,'link':(it.findtext('link') or '').strip(),'published':(it.findtext('pubDate') or '').strip(),'sentiment':s})
        if not items:return {'score':50,'available':False,'headlines':[]}
        avg=mean([x['sentiment'] for x in items]); negshare=mean([1 if x['sentiment']<0 else 0 for x in items]); risk=100*clamp(.65*((1-avg)/2)+.35*negshare)
        return {'score':risk,'available':True,'headlines':items[:8],'meanSentiment':avg,'articleCount':len(items)}
    except Exception as e:return {'score':50,'available':False,'headlines':[],'error':str(e)[:120]}

def _records(df):
    try:
        fr=df.copy().reset_index(); fr.columns=['_'.join(str(y) for y in x if str(y)) if isinstance(x,tuple) else str(x) for x in fr.columns]; return fr.to_dict('records')
    except:return []
def _metric(records,keywords):
    hits=[]; kw=[x.lower() for x in keywords]
    for row in records:
        text=' '.join(str(v).lower() for v in row.values() if isinstance(v,str))
        for k,v in row.items():
            if any(w in str(k).lower() for w in kw):
                try:
                    x=float(v)
                    if math.isfinite(x):hits.append(x)
                except:pass
        if any(w in text for w in kw):
            vals=[]
            for v in row.values():
                try:
                    x=float(v)
                    if math.isfinite(x):vals.append(x)
                except:pass
            if vals:hits.extend(vals[-2:])
    return hits[-1] if hits else None

def fundamental_module(symbol):
    try:
        from vnstock import Fundamental
        eq=Fundamental().equity(symbol); frames=[]
        for meth,args in [('ratio',{}),('income_statement',{'period':'quarter'}),('balance_sheet',{'period':'quarter'})]:
            try:frames.append(getattr(eq,meth)(**args))
            except Exception:
                try:frames.append(getattr(eq,meth)())
                except:pass
        rec=[]
        for f in frames:rec.extend(_records(f))
        vals={'roe':_metric(rec,['roe','return_on_equity','return on equity']),'pe':_metric(rec,['pe','p/e','price_to_earning']),'debtToEquity':_metric(rec,['debt_to_equity','debt/equity','d/e']),'netMargin':_metric(rec,['net_profit_margin','net margin','net_margin']),'revenueGrowth':_metric(rec,['revenue_growth','revenue growth','growth_revenue'])}
        if not any(v is not None for v in vals.values()):return {'score':50,'available':False,'metrics':vals}
        ps=[]
        if vals['roe'] is not None: rv=vals['roe']/100 if abs(vals['roe'])>2 else vals['roe']; ps.append(clamp((.12-rv)/.18))
        if vals['pe'] is not None and vals['pe']>0:ps.append(clamp((vals['pe']-18)/30))
        if vals['debtToEquity'] is not None: dv=vals['debtToEquity']/100 if vals['debtToEquity']>10 else vals['debtToEquity']; ps.append(clamp((dv-.7)/2.0))
        if vals['netMargin'] is not None: mv=vals['netMargin']/100 if abs(vals['netMargin'])>2 else vals['netMargin']; ps.append(clamp((.08-mv)/.15))
        if vals['revenueGrowth'] is not None: gv=vals['revenueGrowth']/100 if abs(vals['revenueGrowth'])>2 else vals['revenueGrowth']; ps.append(clamp((-gv)/.20))
        return {'score':100*mean(ps) if ps else 50,'available':bool(ps),'metrics':vals}
    except Exception as e:return {'score':50,'available':False,'metrics':{},'error':str(e)[:140]}

def aggregate(mods):
    weights={'technical':.30,'analog':.25,'market':.10,'macro':.10,'sentiment':.10,'fundamental':.15}; total=used=0
    for k,w in weights.items():
        m=mods.get(k) or {}
        if m.get('available',True) and isinstance(m.get('score'),(int,float)):total+=w*m['score'];used+=w
    return (total/used if used else 50),used

def state(score):return 'RED' if score>=70 else 'GOLD' if score>=55 else 'WATCH' if score>=42 else 'CLEAR'
def explain(mods):
    labels={'technical':'Technical','analog':'Historical analog','market':'Market regime','macro':'Macro/cross-asset','sentiment':'News sentiment','fundamental':'Fundamentals'}; ranked=[]
    for k,m in mods.items():
        if m.get('available',True) and isinstance(m.get('score'),(int,float)):ranked.append((m['score'],labels.get(k,k)))
    ranked.sort(reverse=True);return [f'{name} {score:.0f}/100' for score,name in ranked[:3]]

def scan_one(symbol,market,macro):
    rows,_,_=yahoo_chart(symbol,'3y',9); cur,an,fs=technical_state(rows)
    mods={'technical':{'score':cur['technical'],'available':True},'analog':an['20'],'market':market,'macro':macro,'sentiment':{'score':50,'available':False},'fundamental':{'score':50,'available':False}}
    score,conf=aggregate(mods)
    return {'symbol':symbol,'name':NAMES.get(symbol,symbol),'date':cur['date'],'close':cur['close'],'ret5':cur['ret5'],'score':score,'state':state(score),'confidence':conf,'modules':mods,'current':cur,'rows':rows,'features':fs}

def enrich(item):
    s=item['symbol'];item['modules']['sentiment']=sentiment_module(s);item['modules']['fundamental']=fundamental_module(s);item['score'],item['confidence']=aggregate(item['modules']);item['state']=state(item['score']);item['reasons']=explain(item['modules']);return item

def scan(limit=18):
    market=market_module();macro=macro_module();items=[];errors=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut={ex.submit(scan_one,s,market,macro):s for s in UNIVERSE}
        for f in as_completed(fut):
            try:items.append(f.result())
            except Exception as e:errors.append({'symbol':fut[f],'error':str(e)[:100]})
    items.sort(key=lambda x:x['score'],reverse=True);targets={x['symbol'] for x in items[:12]}|{'FPT','PNJ'};by={x['symbol']:x for x in items}
    with ThreadPoolExecutor(max_workers=5) as ex:
        fut={ex.submit(enrich,by[s]):s for s in targets if s in by}
        for f in as_completed(fut):
            try:by[fut[f]]=f.result()
            except:pass
    clean=[]
    for x in sorted(by.values(),key=lambda z:z['score'],reverse=True):
        x=dict(x);x.pop('rows',None);x.pop('features',None);clean.append(x)
    confirmed=[x for x in clean if x['confidence']>=.85]
    return {'version':VERSION,'asOf':datetime.now(VN_TZ).isoformat(),'universeSize':len(UNIVERSE),'scanned':len(clean),'market':market,'macro':macro,'goldList':[x for x in confirmed if x['state']=='GOLD'][:10],'redList':[x for x in confirmed if x['state']=='RED'][:10],'ranking':clean[:limit],'errors':errors}

def crash_events(rows,fs):
    events=[];used=[]
    for f in fs:
        i=f['i'];d=future_dd(rows,i,20)
        if d is None or d>-.12 or (used and i-used[-1]<30):continue
        pre=[]
        for lead in (20,10,5,0):
            j=max(0,i-lead);cand=[x for x in fs if x['i']<=j]
            if cand:pre.append({'lead':lead,'date':cand[-1]['date'],'technical':cand[-1]['technical'],'close':cand[-1]['close'],'drivers':cand[-1]['technicalDrivers']})
        events.append({'signalDate':f['date'],'startClose':f['close'],'forwardDrawdown20':d,'preSignals':pre});used.append(i)
    events.sort(key=lambda x:x['forwardDrawdown20']);return events[:8]

def detail(symbol,asof=None,start=None,end=None):
    symbol=re.sub('[^A-Z0-9]','',symbol.upper())[:8]
    if not symbol:raise ValueError('Invalid symbol')
    rows,_,_=yahoo_chart(symbol,'10y',12)
    if end:rows=[r for r in rows if r['date']<=end]
    cur,an,fs=technical_state(rows,asof);market=market_module();macro=macro_module();sent=sentiment_module(symbol,asof);fund=fundamental_module(symbol)
    mods={'technical':{'score':cur['technical'],'available':True,'drivers':cur['technicalDrivers']},'analog':an['20'],'market':market,'macro':macro,'sentiment':sent,'fundamental':fund};score,conf=aggregate(mods);view=rows
    if start:view=[r for r in view if r['date']>=start]
    return {'version':VERSION,'symbol':symbol,'name':NAMES.get(symbol,symbol),'requestedAsOf':asof,'modelAsOf':cur['date'],'score':score,'state':state(score),'confidence':conf,'reasons':explain(mods),'modules':mods,'current':cur,'horizons':an,'news':sent.get('headlines',[]),'history':view[-1600:],'scoreHistory':[{'date':f['date'],'technical':f['technical']} for f in fs if not start or f['date']>=start],'crashReplay':crash_events(rows,fs),'source':{'price':'Yahoo Finance chart adapter','sentiment':'Google News RSS lexical sentiment','fundamental':'Vnstock Fundamental when available','macro':'Yahoo cross-asset proxies','market':'VNINDEX'}}

class handler(BaseHTTPRequestHandler):
    def sendj(self,code,payload,cache='s-maxage=180, stale-while-revalidate=300'):
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Cache-Control',cache);self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query);mode=q.get('mode',['scan'])[0]
        try:
            if mode=='detail':self.sendj(200,detail(q.get('symbol',['FPT'])[0],q.get('asof',[None])[0],q.get('from',[None])[0],q.get('to',[None])[0]),'s-maxage=120, stale-while-revalidate=240')
            elif mode=='health':self.sendj(200,{'ok':True,'version':VERSION,'universe':len(UNIVERSE)},'no-store')
            else:self.sendj(200,scan(min(30,max(5,int(q.get('limit',['18'])[0])))))
        except Exception as e:self.sendj(503,{'error':'STOCK_EWS_FAILED','message':str(e),'version':VERSION},'no-store')
