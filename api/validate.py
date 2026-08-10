import os, pathlib, importlib.util, json, math, re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

os.environ['VNSTOCK_DATA_DIR']='/tmp/.vnstock'
os.environ['HOME']='/tmp'
os.environ['USERPROFILE']='/tmp'
os.environ['XDG_CACHE_HOME']='/tmp/.cache'
os.environ['XDG_CONFIG_HOME']='/tmp/.config'
os.environ['XDG_DATA_HOME']='/tmp/.local/share'
for p in ['/tmp/.vnstock','/tmp/.vnstock/id','/tmp/.cache','/tmp/.config','/tmp/.local/share']:
    try: os.makedirs(p, exist_ok=True)
    except Exception: pass
pathlib.Path.home=classmethod(lambda cls: cls('/tmp'))

try:
    from vnstock.ui import Market
except Exception:
    from vnstock import Market

core_path=pathlib.Path(__file__).with_name('stocks.py')
spec=importlib.util.spec_from_file_location('stock_core_validation',core_path)
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

VERSION='QTRR-VALIDATION-1.1.0'
VN_TZ=ZoneInfo('Asia/Ho_Chi_Minh')
MAX_HISTORY_DAYS=8*366
SAMPLE_STEP=5
MIN_SAMPLES=120
EVENT_HORIZON=20
PURGE_SESSIONS=20
EVENT_THRESHOLD=-0.12

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
    tc=col(fr,['time','date','datetime','trading_date','index']); cc=col(fr,['close','price','index_value'])
    oc=col(fr,['open']); hc=col(fr,['high']); lc=col(fr,['low']); vc=col(fr,['volume','match_volume','total_volume'])
    if not tc or not cc:raise ValueError(f'Unexpected Vnstock OHLCV schema: {list(fr.columns)}')
    out=[]
    for _,r in fr.iterrows():
        try:
            close=float(r.get(cc)); raw=r.get(tc); d=raw.isoformat()[:10] if hasattr(raw,'isoformat') else str(raw)[:10]
            if not math.isfinite(close) or close<=0 or len(d)!=10:continue
            def num(c,default):
                if not c:return default
                try:
                    v=float(r.get(c)); return v if math.isfinite(v) else default
                except Exception:return default
            out.append({'date':d,'open':num(oc,close),'high':num(hc,close),'low':num(lc,close),'close':close,'volume':num(vc,0.0)})
        except Exception:pass
    ded={r['date']:r for r in out}; return [ded[k] for k in sorted(ded)]

def fetch_history(symbol,start,end):
    obj=Market().equity(symbol); windows=[]; cur=start
    while cur<=end:
        nxt=min(end,cur+timedelta(days=370)); windows.append((cur,nxt)); cur=nxt+timedelta(days=1)
    rows=[]; audit=[]
    for a,b in windows:
        try:
            part=normalize_ohlcv(obj.ohlcv(start=a.isoformat(),end=(b+timedelta(days=1)).isoformat(),interval='1D'))
            rows+=part; audit.append({'start':a.isoformat(),'end':b.isoformat(),'rows':len(part),'ok':True})
        except Exception as e:audit.append({'start':a.isoformat(),'end':b.isoformat(),'rows':0,'ok':False,'error':str(e)[:160]})
    ded={r['date']:r for r in rows}; rows=[ded[k] for k in sorted(ded)]
    if len(rows)<350:raise RuntimeError(f'Only {len(rows)} usable rows; validation needs at least 350 completed sessions')
    return rows,audit

def analog_pt(rows,fs,current,h=20):
    cutoff=current['i']
    cand=[f for f in fs if f['i']+max(60,h)<=cutoff and f['i']<cutoff-60]
    if len(cand)<80:return {'score':50,'rate':None,'matches':0,'available':False}
    keys=['vol20','dd60','mom20','trend50','trend200','rsi14','macdNorm','volumeZ']
    stats={k:(core.mean([f[k] for f in cand]),core.sd([f[k] for f in cand]) or 1) for k in keys}
    rank=[]
    for f in cand:
        dist=math.sqrt(sum(((f[k]-current[k])/stats[k][1])**2 for k in keys)/len(keys)); rank.append((dist,f))
    rank.sort(key=lambda x:x[0]); events=[]
    for _,f in rank[:40]:
        d=core.future_dd(rows,f['i'],h)
        if d is not None:events.append(1 if d<=EVENT_THRESHOLD else 0)
    if not events:return {'score':50,'rate':None,'matches':0,'available':False}
    rate=core.mean(events)
    return {'score':100*core.clamp(rate/.30),'rate':rate,'matches':len(events),'available':True}

def structural_score(technical,analog): return (30*technical+25*analog)/55

def make_samples(rows):
    fs=core.features(rows)
    if not fs:return []
    samples=[]
    for pos in range(0,len(fs),SAMPLE_STEP):
        f=fs[pos]; i=f['i']
        if i+EVENT_HORIZON>=len(rows):continue
        a=analog_pt(rows,fs,f,EVENT_HORIZON)
        if not a.get('available'):continue
        d=core.future_dd(rows,i,EVENT_HORIZON)
        if d is None:continue
        samples.append({'date':f['date'],'i':i,'score':structural_score(float(f['technical']),float(a['score'])),'technical':f['technical'],'analogScore':a['score'],'analogRate':a['rate'],'weakTrend':(f['mom20']<0 or f['trend50']<0),'forwardDrawdown20':d,'event':d<=EVENT_THRESHOLD})
    return samples

def safe_div(a,b):return a/b if b else None

def metrics(samples,threshold):
    tp=fp=tn=fn=0; warned=[]; clear=[]
    for s in samples:
        pred=s['score']>=threshold and s['weakTrend']; actual=bool(s['event'])
        if pred and actual:tp+=1
        elif pred and not actual:fp+=1
        elif not pred and actual:fn+=1
        else:tn+=1
        (warned if pred else clear).append(s['forwardDrawdown20'])
    precision=safe_div(tp,tp+fp); recall=safe_div(tp,tp+fn); specificity=safe_div(tn,tn+fp)
    f1=(2*precision*recall/(precision+recall)) if precision is not None and recall is not None and precision+recall>0 else None
    return {'threshold':threshold,'samples':len(samples),'events':tp+fn,'warnings':tp+fp,'tp':tp,'fp':fp,'tn':tn,'fn':fn,'precision':precision,'recall':recall,'specificity':specificity,'falsePositiveRate':safe_div(fp,fp+tn),'f1':f1,'accuracy':safe_div(tp+tn,len(samples)),'avgForwardDrawdownWarned':core.mean(warned) if warned else None,'avgForwardDrawdownClear':core.mean(clear) if clear else None}

def choose_threshold(train):
    best=None
    for t in range(45,81,5):
        m=metrics(train,t); f1=m['f1'] if m['f1'] is not None else -1; p=m['precision'] or 0; r=m['recall'] or 0; fpr=m['falsePositiveRate'] or 0
        utility=f1+.08*r+.04*p-.03*fpr
        if best is None or utility>best[0]:best=(utility,t,m)
    return best[1],best[2]

def auc_rank(samples):
    pos=[s for s in samples if s['event']]; neg=[s for s in samples if not s['event']]
    if not pos or not neg:return None
    wins=ties=0
    for p in pos:
        for n in neg:
            if p['score']>n['score']:wins+=1
            elif p['score']==n['score']:ties+=1
    return (wins+.5*ties)/(len(pos)*len(neg))

def independent_event_clusters(samples):
    idx=[s['i'] for s in samples if s['event']]
    if not idx:return 0
    clusters=1; last=idx[0]
    for i in idx[1:]:
        if i-last>EVENT_HORIZON:clusters+=1
        last=i
    return clusters

def validation(symbol,q):
    symbol=clean_symbol(symbol)
    if not symbol:raise ValueError('Invalid symbol')
    today=datetime.now(VN_TZ).date(); end=min(parse_date(q.get('to',[None])[0],today),today); start=max(today-timedelta(days=MAX_HISTORY_DAYS),end-timedelta(days=MAX_HISTORY_DAYS))
    rows,audit=fetch_history(symbol,start,end); samples=make_samples(rows)
    if len(samples)<MIN_SAMPLES:return {'version':VERSION,'symbol':symbol,'status':'INSUFFICIENT','reason':f'Only {len(samples)} point-in-time samples available; at least {MIN_SAMPLES} required.','samples':len(samples),'audit':audit}
    split=max(60,int(len(samples)*.70))
    if split>=len(samples):raise RuntimeError('Not enough samples for holdout')
    test=samples[split:]; test_start_i=test[0]['i']
    train=[s for s in samples[:split] if s['i']+PURGE_SESSIONS<test_start_i]
    if len(train)<60 or len(test)<30:return {'version':VERSION,'symbol':symbol,'status':'INSUFFICIENT','reason':'Purged calibration/holdout windows are too small for reliable evaluation.','samples':len(samples),'calibrationSamples':len(train),'holdoutSamples':len(test),'audit':audit}
    threshold,train_metrics=choose_threshold(train); test_metrics=metrics(test,threshold); test_metrics['auc']=auc_rank(test)
    prevalence=safe_div(sum(1 for s in test if s['event']),len(test)); clusters=independent_event_clusters(test); p=test_metrics['precision']; r=test_metrics['recall']; fpr=test_metrics['falsePositiveRate']
    lift=(p/prevalence) if p is not None and prevalence and prevalence>0 else None
    test_metrics['precisionLiftVsBaseRate']=lift; test_metrics['independentTailEventClusters']=clusters
    if len(test)<40 or clusters<4:verdict='LIMITED'; note='Holdout contains too few independent tail-event clusters for stable performance conclusions.'
    elif p is not None and r is not None and p>=.35 and r>=.50 and (fpr is None or fpr<=.25) and (lift is None or lift>=1.5):verdict='USEFUL_SIGNAL'; note='The structural warning shows usable purged-holdout separation, but remains a risk-screening signal rather than a calibrated crash probability.'
    elif r is not None and r>=.45:verdict='WATCH'; note='The model captures part of the tail-event set but false alarms, precision or lift remain material; use as an escalation screen, not a standalone decision rule.'
    else:verdict='WEAK'; note='Out-of-sample evidence is weak for this security/window; do not rely on the warning without additional evidence.'
    return {'version':VERSION,'symbol':symbol,'status':'OK','method':'purged_chronological_holdout_point_in_time','eventDefinition':'20-session forward drawdown <= -12%','eventHorizonSessions':EVENT_HORIZON,'sampleStepSessions':SAMPLE_STEP,'purgeSessions':PURGE_SESSIONS,'scoreDefinition':'54.5% technical deterioration + 45.5% point-in-time analog stress','scope':'Structural screening-layer validation only; not a validation of the full six-module production composite and not a reproduction of the thesis ANFIS+VAE model.','thesisAlignment':'The thesis uses ANFIS+VAE and a 3.09-sigma CRASH definition; this operational validation intentionally uses a separate 20-session <= -12% drawdown event for QTRR screening.','calibration':{'from':train[0]['date'],'to':train[-1]['date'],'metrics':train_metrics},'holdout':{'from':test[0]['date'],'to':test[-1]['date'],'prevalence':prevalence,'metrics':test_metrics,'overlapNote':'Samples are observed every 5 sessions while the label horizon is 20 sessions; performance rows are screening observations, not independent crash events. Independent event clusters are reported separately.'},'verdict':verdict,'note':note,'governance':{'use':'Model-risk evidence for screening/escalation calibration','notFor':'Automatic trading, VaR replacement, or calibrated default/crash probability','recalibration':'Re-run after material methodology/data changes and review stability across market regimes'},'audit':audit}

class handler(BaseHTTPRequestHandler):
    def sendj(self,code,payload):
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query)
        try:
            if q.get('mode',[''])[0]=='health':self.sendj(200,{'ok':True,'version':VERSION,'time':datetime.now(VN_TZ).isoformat()})
            else:self.sendj(200,validation(q.get('symbol',['FPT'])[0],q))
        except Exception as e:self.sendj(503,{'error':'VALIDATION_FAILED','message':str(e),'version':VERSION,'retryable':True})
