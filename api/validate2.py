import pathlib, importlib.util, json, re
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

core_path=pathlib.Path(__file__).with_name('stocks.py')
spec=importlib.util.spec_from_file_location('vmews_validation_core_final',core_path)
core=importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

price_path=pathlib.Path(__file__).with_name('price_history.py')
pspec=importlib.util.spec_from_file_location('vmews_validation_price_history',price_path)
price_history=importlib.util.module_from_spec(pspec); pspec.loader.exec_module(price_history)

VERSION='QTRR-VALIDATION-2.1.0-PRODUCTION'
VN_TZ=timezone(timedelta(hours=7))
SAMPLE_STEP=5; MIN_SAMPLES=120; EVENT_HORIZON=20; PURGE_SESSIONS=20; EVENT_THRESHOLD=-0.12

def clean_symbol(s):return re.sub('[^A-Z0-9]','',str(s or '').upper())[:8]
def safe_div(a,b):return a/b if b else None

def fetch_history(symbol,end=None):
    errors=[]
    try:
        rows,_,host=core.yahoo_chart(symbol,'10y',12)
        if end:rows=[r for r in rows if r['date']<=end]
        if len(rows)>=350:
            return rows,[{'source':'Yahoo Finance','provider':host,'type':'validation.ohlcv','symbol':symbol,'rows':len(rows),'ok':True}]
        errors.append(f'Yahoo only {len(rows)} rows')
    except Exception as e:
        errors.append(f'Yahoo: {e}')
    try:
        rows,audit=price_history.vnstock_equity_history(symbol,11)
        if end:rows=[r for r in rows if r['date']<=end]
        audit={**audit,'type':'validation.ohlcv','rows':len(rows)}
        if len(rows)>=350:
            return rows,[audit]
        errors.append(f'Vnstock only {len(rows)} rows')
    except Exception as e:
        errors.append(f'Vnstock: {e}')
    raise RuntimeError(f'{symbol}: validation needs >=350 completed sessions; ' + ' | '.join(errors))

def analog_pt(rows,fs,current,h=20):
    cutoff=current['i']; cand=[f for f in fs if f['i']+max(60,h)<=cutoff and f['i']<cutoff-60]
    if len(cand)<80:return {'score':50,'rate':None,'matches':0,'available':False}
    keys=['vol20','dd60','mom20','trend50','trend200','rsi14','macdNorm','volumeZ']
    stats={k:(core.mean([f[k] for f in cand]),core.sd([f[k] for f in cand]) or 1) for k in keys}; rank=[]
    for f in cand:
        dist=(sum(((f[k]-current[k])/stats[k][1])**2 for k in keys)/len(keys))**0.5; rank.append((dist,f))
    rank.sort(key=lambda x:x[0]); events=[]
    for _,f in rank[:40]:
        d=core.future_dd(rows,f['i'],h)
        if d is not None:events.append(1 if d<=EVENT_THRESHOLD else 0)
    if not events:return {'score':50,'rate':None,'matches':0,'available':False}
    rate=core.mean(events); return {'score':100*core.clamp(rate/.30),'rate':rate,'matches':len(events),'available':True}

def make_samples(rows):
    fs=core.features(rows); samples=[]
    for pos in range(0,len(fs),SAMPLE_STEP):
        f=fs[pos]; i=f['i']
        if i+EVENT_HORIZON>=len(rows):continue
        a=analog_pt(rows,fs,f,EVENT_HORIZON)
        if not a.get('available'):continue
        d=core.future_dd(rows,i,EVENT_HORIZON)
        if d is None:continue
        score=(30*float(f['technical'])+25*float(a['score']))/55
        samples.append({'date':f['date'],'i':i,'score':score,'weakTrend':(f['mom20']<0 or f['trend50']<0),'forwardDrawdown20':d,'event':d<=EVENT_THRESHOLD})
    return samples

def metrics(samples,threshold):
    tp=fp=tn=fn=0
    for s in samples:
        pred=s['score']>=threshold and s['weakTrend']; actual=bool(s['event'])
        if pred and actual:tp+=1
        elif pred:fp+=1
        elif actual:fn+=1
        else:tn+=1
    precision=safe_div(tp,tp+fp); recall=safe_div(tp,tp+fn); specificity=safe_div(tn,tn+fp)
    f1=(2*precision*recall/(precision+recall)) if precision is not None and recall is not None and precision+recall>0 else None
    return {'threshold':threshold,'samples':len(samples),'events':tp+fn,'warnings':tp+fp,'tp':tp,'fp':fp,'tn':tn,'fn':fn,'precision':precision,'recall':recall,'specificity':specificity,'falsePositiveRate':safe_div(fp,fp+tn),'f1':f1,'accuracy':safe_div(tp+tn,len(samples))}

def choose_threshold(train):
    best=None
    for t in range(45,81,5):
        m=metrics(train,t); f1=m['f1'] if m['f1'] is not None else -1; p=m['precision'] or 0; r=m['recall'] or 0; fpr=m['falsePositiveRate'] or 0; utility=f1+.08*r+.04*p-.03*fpr
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

def clusters(samples):
    idx=[s['i'] for s in samples if s['event']]
    if not idx:return 0
    c=1; last=idx[0]
    for i in idx[1:]:
        if i-last>EVENT_HORIZON:c+=1
        last=i
    return c

def validation(symbol,q):
    symbol=clean_symbol(symbol)
    if not symbol:raise ValueError('Invalid symbol')
    end=q.get('to',[None])[0] or None; rows,audit=fetch_history(symbol,end); samples=make_samples(rows)
    if len(samples)<MIN_SAMPLES:return {'version':VERSION,'symbol':symbol,'status':'INSUFFICIENT','reason':f'Only {len(samples)} point-in-time samples available; at least {MIN_SAMPLES} required.','samples':len(samples),'audit':audit}
    split=max(60,int(len(samples)*.70)); test=samples[split:]; test_start_i=test[0]['i']; train=[s for s in samples[:split] if s['i']+PURGE_SESSIONS<test_start_i]
    if len(train)<60 or len(test)<30:return {'version':VERSION,'symbol':symbol,'status':'INSUFFICIENT','reason':'Purged calibration/holdout windows are too small for reliable evaluation.','samples':len(samples),'audit':audit}
    threshold,train_metrics=choose_threshold(train); test_metrics=metrics(test,threshold); test_metrics['auc']=auc_rank(test); prevalence=safe_div(sum(1 for s in test if s['event']),len(test)); c=clusters(test); p=test_metrics['precision']; r=test_metrics['recall']; fpr=test_metrics['falsePositiveRate']; lift=(p/prevalence) if p is not None and prevalence and prevalence>0 else None; test_metrics['precisionLiftVsBaseRate']=lift; test_metrics['independentTailEventClusters']=c
    if len(test)<40 or c<4:verdict='LIMITED'; note='Holdout contains too few independent tail-event clusters for stable performance conclusions.'
    elif p is not None and r is not None and p>=.35 and r>=.50 and (fpr is None or fpr<=.25) and (lift is None or lift>=1.5):verdict='USEFUL_SIGNAL'; note='The structural warning shows usable purged-holdout separation, but remains a risk-screening signal rather than a calibrated crash probability.'
    elif r is not None and r>=.45:verdict='WATCH'; note='The model captures part of the tail-event set but false alarms, precision or lift remain material; use as an escalation screen, not a standalone decision rule.'
    else:verdict='WEAK'; note='Out-of-sample evidence is weak for this security/window; do not rely on the warning without additional evidence.'
    return {'version':VERSION,'symbol':symbol,'status':'OK','method':'purged_chronological_holdout_point_in_time','eventDefinition':'20-session forward drawdown <= -12%','eventHorizonSessions':EVENT_HORIZON,'sampleStepSessions':SAMPLE_STEP,'purgeSessions':PURGE_SESSIONS,'scoreDefinition':'54.5% technical deterioration + 45.5% point-in-time analog stress','calibration':{'from':train[0]['date'],'to':train[-1]['date'],'metrics':train_metrics},'holdout':{'from':test[0]['date'],'to':test[-1]['date'],'prevalence':prevalence,'metrics':test_metrics},'verdict':verdict,'note':note,'audit':audit}

class handler(BaseHTTPRequestHandler):
    def sendj(self,code,payload):
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query)
        try:
            if q.get('mode',[''])[0]=='health':out={'ok':True,'version':VERSION,'time':datetime.now(VN_TZ).isoformat(),'priceSource':'Yahoo Finance with Vnstock Unified Market fallback'}
            else:out=validation(q.get('symbol',['FPT'])[0],q)
            self.sendj(200,out)
        except Exception as e:self.sendj(503,{'error':'VALIDATION_FAILED','message':str(e),'type':type(e).__name__,'version':VERSION,'retryable':True})
