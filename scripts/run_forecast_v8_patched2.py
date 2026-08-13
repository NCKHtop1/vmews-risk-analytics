import os,re
from pathlib import Path
p=Path(__file__).with_name('train_forecast_v8.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r";marketAudit=\{.*?\};magnitudeApproved=",';magnitudeApproved=',s,count=1)
s=s.replace("valid=np.isfinite(y)&np.isfinite(ya);si,_,_,_=split(dates,D,valid,h,(0.,1.));simp", "valid=np.isfinite(y)&np.isfinite(ya);simp")
s=re.sub(r"\nif __name__=='__main__':train\(os\.environ\.get\('GITHUB_WORKSPACE','\.'\)\)\s*$",'',s)
ns={'__name__':'forecast_v8_patched','__file__':str(p)}
exec(compile(s,str(p),'exec'),ns)
ns['train'](os.environ.get('GITHUB_WORKSPACE','.'))
