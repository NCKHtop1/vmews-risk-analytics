import warnings,math
import numpy as np
from scipy.stats import spearmanr,ConstantInputWarning
import train_forecast_v11 as m
warnings.filterwarnings('ignore',category=ConstantInputWarning)
warnings.filterwarnings('ignore',message='All-NaN slice encountered')

def safe_rank_stats(y,p,D):
    ics=[];sp=[]
    for d in sorted(set(D)):
        q=np.where(D==d)[0]
        if len(q)<12:continue
        yy=np.asarray(y[q],float);pp=np.asarray(p[q],float)
        if np.nanstd(yy)>1e-14 and np.nanstd(pp)>1e-14:
            z=spearmanr(yy,pp).statistic
            if z is not None and math.isfinite(float(z)):ics.append(float(z))
        order=np.argsort(pp);k=max(1,len(q)//5);sp.append(float(np.mean(yy[order[-k:]])-np.mean(yy[order[:k]])))
    return {'ic':float(np.mean(ics)) if ics else 0.,'spread':float(np.mean(sp)) if sp else 0.}
orig=m.risk_status
def safe_risk(f):
    st,n=orig(f);return st,int(n)
m.rank_stats=safe_rank_stats;m.risk_status=safe_risk
m.main()
