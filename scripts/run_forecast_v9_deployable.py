import os,re
from pathlib import Path
p=Path(__file__).with_name('train_forecast_v9.py')
s=p.read_text(encoding='utf-8')
s=s.replace("an=A[0]['name'];dn=C[0]['name'];mn=MC[0]['name'];", "an='ridge';dn='logit';mn='logit';")
s=re.sub(r"\nif __name__=='__main__':train\(os\.environ\.get\('GITHUB_WORKSPACE','\.'\)\)\s*$",'',s)
ns={'__name__':'v9_deployable','__file__':str(p)}
exec(compile(s,str(p),'exec'),ns)
ns['train'](os.environ.get('GITHUB_WORKSPACE','.'))
