import math
import numpy as np

MIN_ROWS=80
FEATURES=['ret1','ret2','ret3','ret5','ret10','ret20','dd20','dd60','trend5','trend10','trend20','trend50','vol5','vol20','rsi14','macdNorm','volumeZ','range1','range5','technicalShort','technicalDelta5']

def ema(a,n):
 out=[];e=None;k=2/(n+1)
 for v in a:e=float(v) if e is None else k*float(v)+(1-k)*e;out.append(e)
 return np.asarray(out,float)
def rsi(c,i):
 if i<14:return 50.
 d=np.diff(c[i-14:i+1]);g=np.maximum(d,0).mean();l=np.maximum(-d,0).mean();return 100. if l<1e-12 else 100-100/(1+g/l)
def sanitize(raw):
 d={}
 for r in raw or []:
  try:
   c=float(r['close']);
   if not math.isfinite(c) or c<=0:continue
   o=float(r.get('open') or c);h=float(r.get('high') or c);l=float(r.get('low') or c);v=max(0.,float(r.get('volume') or 0));h=max(h,o,l,c);l=min(l,o,h,c);d[str(r['date'])[:10]]={'date':str(r['date'])[:10],'open':o,'high':h,'low':l,'close':c,'volume':v}
  except:pass
 rows=[d[k] for k in sorted(d)]
 if not rows:return []
 m=[rows[0]['close']]
 for i in range(1,len(rows)):
  z=math.log(rows[i]['close']/rows[i-1]['close']);m.append(m[-1]*math.exp(0 if abs(z)>.22 else z))
 for r,x in zip(rows,m):r['modelClose']=max(1e-9,x)
 return rows
def features(raw):
 rows=sanitize(raw)
 if len(rows)<MIN_ROWS:return rows,[]
 c=np.asarray([x['modelClose'] for x in rows],float);v=np.asarray([x['volume'] for x in rows],float);hi=np.asarray([x['high'] for x in rows],float);lo=np.asarray([x['low'] for x in rows],float);lr=np.zeros(len(c));lr[1:]=np.log(c[1:]/c[:-1]);mac=ema(c,12)-ema(c,26);sig=ema(mac,9);out=[]
 for i in range(60,len(rows)):
  ret=lambda k:math.log(c[i]/c[i-k]);sma=lambda k:max(1e-9,float(np.mean(c[i-k+1:i+1])));tr={k:c[i]/sma(k)-1 for k in (5,10,20,50)};dd20=c[i]/max(c[i-19:i+1])-1;dd60=c[i]/max(c[i-59:i+1])-1;vol5=float(np.std(lr[i-4:i+1],ddof=1)*math.sqrt(252));vol20=float(np.std(lr[i-19:i+1],ddof=1)*math.sqrt(252));rs=rsi(c,i);mn=float((mac[i]-sig[i])/max(c[i],1e-9));rv=v[max(1,i-20):i];rv=rv[rv>0];sd=float(rv.std(ddof=1)) if len(rv)>1 else 0;vz=float((v[i]-rv.mean())/(sd if sd>1e-12 else 1)) if v[i]>0 and len(rv) else 0.;r5=[max(0.,float((hi[j]-lo[j])/max(c[j],1e-9))) for j in range(i-4,i+1)];mom=c[i]/c[i-20]-1
  pdd=min(1,max(0,-dd60/.18));pm=min(1,max(0,-mom/.12));pt=min(1,max(0,-tr[50]/.10));pv=min(1,max(0,(vol20-.22)/.35));pr=min(1,max(0,(45-rs)/20));pma=min(1,max(0,-mn/.025));pvol=min(1,max(0,vz/3))*min(1,max(0,-lr[i]/.05));tech=100*(.22*pdd+.20*pm+.18*pt+.14*pv+.10*pr+.08*pma+.08*pvol)
  out.append({'i':i,'date':rows[i]['date'],'ret1':float(lr[i]),'ret2':ret(2),'ret3':ret(3),'ret5':ret(5),'ret10':ret(10),'ret20':ret(20),'dd20':float(dd20),'dd60':float(dd60),'trend5':float(tr[5]),'trend10':float(tr[10]),'trend20':float(tr[20]),'trend50':float(tr[50]),'vol5':vol5,'vol20':vol20,'rsi14':rs/100,'macdNorm':mn,'volumeZ':vz,'range1':max(0.,float((hi[i]-lo[i])/max(c[i],1e-9))),'range5':float(np.mean(r5)),'technicalShort':float(tech)})
 by={x['date']:x['technicalShort'] for x in out}
 for x in out:x['technicalDelta5']=(x['technicalShort']-by.get(rows[max(0,x['i']-5)]['date'],x['technicalShort']))/100
 return rows,out
