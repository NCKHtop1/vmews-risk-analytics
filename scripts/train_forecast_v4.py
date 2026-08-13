import os,json,glob,math
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from sklearn.linear_model import Ridge
from forecast_v4_features import FEATURE_NAMES,stock_features,external,aligned
VERSION='VMEWS-FORECAST-4.1.0';H=[1,2,3,4,5]

def panel(root):
 pth={}
 for p in sorted(glob.glob(str(Path(root)/'data/hose-fallbacks/*.json'))+glob.glob(str(Path(root)/'data/deep-alerts/*.json'))):pth.setdefault(Path(p).stem,p)
 ext=external();out=[];used=0
 for sym,p in pth.items():
  try:d=json.load(open(p,encoding='utf-8'));rows,fs=stock_features(d.get('history') or [])
  except:continue
  if len(rows)<520 or len(fs)<260:continue
  used+=1
  for f in fs:
   z={'symbol':d.get('symbol') or sym,**f};dt=f['date'];z['marketTechnical']=aligned(ext.get('marketTechnical'),dt,50);z['vixLevel']=aligned(ext.get('vixLevel'),dt);z['vixRet20']=aligned(ext.get('vixRet20'),dt);z['usdVndRet20']=aligned(ext.get('usdVndRet20'),dt);z['dxyRet20']=aligned(ext.get('dxyRet20'),dt);z['us10yRet20']=aligned(ext.get('us10yRet20'),dt);z['brentRet20']=aligned(ext.get('brentRet20'),dt)
   for h in H:z['y'+str(h)]=math.log(rows[f['i']+h]['modelClose']/rows[f['i']]['modelClose']) if f['i']+h<len(rows) else np.nan
   out.append(z)
 return out,used

def ranks(a):o=np.argsort(a,kind='mergesort');r=np.empty(len(a));r[o]=np.arange(len(a));return r
def rho(y,p):
 if len(y)<3:return 0.
 a,b=ranks(np.asarray(y)),ranks(np.asarray(p));return float(np.corrcoef(a,b)[0,1]) if np.std(a)>0 and np.std(b)>0 else 0.
def metric(y,p):
 y=np.asarray(y);p=np.asarray(p);e=y-p;mid=len(y)//2
 def spr(yy,pp):
  if len(yy)<20:return 0.
  q=np.quantile(pp,[.2,.8]);a=yy[pp<=q[0]];b=yy[pp>=q[1]];return float(b.mean()-a.mean()) if len(a) and len(b) else 0.
 pos=float(np.mean(y>0));base=max(pos,1-pos);mae=float(np.mean(abs(e)));mae0=float(np.mean(abs(y)));mse=float(np.mean(e*e));mse0=float(np.mean(y*y))
 return {'n':len(y),'r2':1-mse/(mse0 or 1e-18),'mae':mae,'maeImprove':1-mae/(mae0 or 1e-18),'direction':float(np.mean((y>=0)==(p>=0))),'majority':base,'spearman':rho(y,p),'spread':spr(y,p),'half1Spread':spr(y[:mid],p[:mid]),'half2Spread':spr(y[mid:],p[mid:])}
def objective(m):return .30*m['r2']+.25*m['maeImprove']+.20*(m['direction']-m['majority'])+.25*m['spearman']
def fitridge(X,y,a):return Ridge(alpha=a).fit(X,y)
def exp(m):return {'type':'ridge','coef':[float(x) for x in m.coef_],'intercept':float(m.intercept_)}

def market_table(P,dates):
 groups={d:[] for d in dates}
 for i,x in enumerate(P):groups[x['date']].append(i)
 names=['ret1Mean','ret5Mean','ret20Mean','technicalMean','riskShare','positive5Share','trendShare','vol20Mean','marketTechnical','vixLevel','vixRet20','usdVndRet20','dxyRet20','us10yRet20','brentRet20'];vals=[]
 for d in dates:
  ix=groups[d];a=[P[i] for i in ix];med=lambda k:float(np.nanmedian([x.get(k,np.nan) for x in a]));mean=lambda k:float(np.nanmean([x.get(k,np.nan) for x in a]));vals.append([mean('ret1'),mean('ret5'),mean('ret20'),med('technical'),float(np.mean([x['technical']>=50 for x in a])),float(np.mean([x['ret5']>0 for x in a])),float(np.mean([x['trend20']>0 for x in a])),med('vol20'),med('marketTechnical'),med('vixLevel'),med('vixRet20'),med('usdVndRet20'),med('dxyRet20'),med('us10yRet20'),med('brentRet20')])
 A=np.array(vals,float);im=np.nanmedian(A,0);q=np.where(~np.isfinite(A));A[q]=np.take(im,q[1]);mu=A.mean(0);sd=A.std(0);sd[sd<1e-9]=1
 return groups,names,im,mu,sd,(A-mu)/sd

def train(root='.'):
 P,ns=panel(root)
 if len(P)<15000:raise SystemExit('panel too small')
 dates=sorted(set(x['date'] for x in P));D=np.array([x['date'] for x in P]);X0=np.array([[x.get(k,np.nan) for k in FEATURE_NAMES] for x in P],float);im=np.nanmedian(X0,0);q=np.where(~np.isfinite(X0));X0[q]=np.take(im,q[1]);mu=X0.mean(0);sd=X0.std(0);sd[sd<1e-9]=1;X=(X0-mu)/sd;groups,mnames,mim,mmu,msd,MX=market_table(P,dates);didx={d:i for i,d in enumerate(dates)}
 out={'version':VERSION,'trainedAt':datetime.now(timezone.utc).isoformat(),'featureNames':FEATURE_NAMES,'impute':im.tolist(),'mean':mu.tolist(),'std':sd.tolist(),'marketFeatureNames':mnames,'marketImpute':mim.tolist(),'marketMean':mmu.tolist(),'marketStd':msd.tolist(),'modelDate':dates[-1],'universe':{'symbols':ns,'rows':len(P),'dates':len(dates),'start':dates[0],'end':dates[-1]},'horizons':{}};rep={}
 for h in H:
  y=np.array([x['y'+str(h)] for x in P],float);ok=np.isfinite(y);ym=np.full(len(dates),np.nan)
  for j,d in enumerate(dates):
   z=[y[i] for i in groups[d] if np.isfinite(y[i])];ym[j]=float(np.median(z)) if z else np.nan
  alpha=np.array([y[i]-ym[didx[D[i]]] if ok[i] and np.isfinite(ym[didx[D[i]]]) else np.nan for i in range(len(P))]);a60=int(.60*len(dates));a80=int(.80*len(dates));devEnd=max(1,a60-h);valEnd=max(a60+1,a80-h);dev=ok&(D<dates[devEnd]);val=ok&(D>=dates[a60])&(D<dates[valEnd]);test=ok&(D>=dates[a80]);mdev=np.arange(0,devEnd);mval=np.arange(a60,valEnd);mtest=np.arange(a80,len(dates));mdev=mdev[np.isfinite(ym[mdev])];mval=mval[np.isfinite(ym[mval])];mtest=mtest[np.isfinite(ym[mtest])]
  if dev.sum()<5000 or val.sum()<1000 or test.sum()<1000 or len(mval)<100:continue
  ac=[]
  for a in (.1,1,10,100,1000):
   m=fitridge(X[dev],alpha[dev],a);p=m.predict(X[val]);ac.append((rho(alpha[val],p),a,m))
  ac.sort(reverse=True,key=lambda z:z[0]);aa=ac[0][1]
  mc=[]
  for a in (.1,1,10,100,1000):
   m=fitridge(MX[mdev],ym[mdev],a);mt=metric(ym[mval],m.predict(MX[mval]));mc.append((objective(mt),a,m))
  mc.sort(reverse=True,key=lambda z:z[0]);ma=mc[0][1]
  am=fitridge(X[dev],alpha[dev],aa);marketm=fitridge(MX[mdev],ym[mdev],ma);ap=am.predict(X[val]);mpdate=marketm.predict(MX[mval]);mp={dates[j]:mpdate[k] for k,j in enumerate(mval)};best=None
  for lam in (0,.25,.5,.75,1):
   base=np.array([mp.get(D[i],0)+lam*ap[k] for k,i in enumerate(np.where(val)[0])]);cal=float(np.median(y[val]-base));pr=base+cal;mt=metric(y[val],pr);sc=objective(mt)
   if best is None or sc>best[0]:best=(sc,lam,cal,mt)
  lam,cal=best[1],best[2];train=ok&(D<dates[valEnd]);atrain=np.isfinite(alpha)&(D<dates[valEnd]);mtrain=np.arange(0,valEnd);mtrain=mtrain[np.isfinite(ym[mtrain])];am=fitridge(X[atrain],alpha[atrain],aa);marketm=fitridge(MX[mtrain],ym[mtrain],ma);ap=am.predict(X[test]);mpt=marketm.predict(MX[mtest]);mp={dates[j]:mpt[k] for k,j in enumerate(mtest)};pred=np.array([mp.get(D[i],0)+lam*ap[k]+cal for k,i in enumerate(np.where(test)[0])]);mt=metric(y[test],pred)
  checks={'accuracy':mt['r2']>0 or mt['maeImprove']>0,'rank':mt['spearman']>.02,'spread':mt['spread']>.002,'stability':mt['half1Spread']>0 and mt['half2Spread']>0,'direction':mt['direction']>=mt['majority']-.01};passed=checks['accuracy'] and checks['rank'] and checks['spread'] and checks['stability'] and checks['direction']
  rv=y[val]-(np.array([best[2]+(fitridge(MX[mdev],ym[mdev],ma).predict(MX[[didx[D[i]]]])[0] if didx[D[i]]<valEnd else 0) for i in np.where(val)[0]])+lam*fitridge(X[dev],alpha[dev],aa).predict(X[val]));q10,q90=np.quantile(rv,[.10,.90])
  afinal=np.isfinite(alpha);mfinal=np.where(np.isfinite(ym))[0];af=fitridge(X[afinal],alpha[afinal],aa);mf=fitridge(MX[mfinal],ym[mfinal],ma);mkt=float(mf.predict(MX[[-1]])[0]+cal);out['horizons'][str(h)]={'status':'PASS' if passed else 'REVIEW','sealed':mt,'checks':checks,'q10':float(q10),'q90':float(q90),'alphaWeight':lam,'calibration':cal,'marketForecast':mkt,'stockModel':exp(af)};rep[str(h)]={'status':'PASS' if passed else 'REVIEW',**mt,'alphaWeight':lam,'marketForecast':mkt}
 core=sum(out['horizons'].get(str(h),{}).get('status')=='PASS' for h in (3,4,5));out['promotion']={'status':'PASS' if core>=2 else 'REVIEW','passedCore':core};Path(root,'data/forecast-model-v4.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');Path(root,'forecast-validation-v4.json').write_text(json.dumps({'version':VERSION,'promotion':out['promotion'],'universe':out['universe'],'horizons':rep},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'promotion':out['promotion'],'universe':out['universe'],'horizons':{k:{x:v[x] for x in ('status','r2','maeImprove','direction','majority','spearman','spread','alphaWeight')} for k,v in rep.items()}},indent=2))
 if out['promotion']['status']!='PASS':raise SystemExit('MODEL_REVIEW_REQUIRED')
if __name__=='__main__':train(os.environ.get('GITHUB_WORKSPACE','.'))
