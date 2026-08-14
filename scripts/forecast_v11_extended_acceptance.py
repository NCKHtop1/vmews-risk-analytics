import json,sys,math
from pathlib import Path
R=Path('.');checks=[]
def ck(n,c,d=''):
 checks.append((n,bool(c),str(d)));print(('PASS ' if c else 'FAIL ')+n+(f' :: {d}' if d else ''))
def load(p):return json.loads((R/p).read_text(encoding='utf-8'))
macro=load('data/macro-study-v11.json');scan=load('data/market-scan.json');dash=load('data/forecast-dashboard-v11.json');live=load('data/forecast-live-v11/summary.json')
ck('macro PIT observation depth',macro.get('observations',0)>=1200,macro.get('observations'));ck('macro strict prior-date rule','strictly earlier than T' in macro.get('pointInTimeRule',''),macro.get('pointInTimeRule'));ck('macro current state',macro.get('current',{}).get('state') in {'SUPPORTIVE','NEUTRAL','STRESS'},macro.get('current',{}));
for s in ('SUPPORTIVE','NEUTRAL','STRESS'):
 z=macro.get('groups',{}).get(s,{});ck(f'macro {s} sample',z.get('n',0)>=100,z.get('n'));ck(f'macro {s} horizons',all(z.get('horizons',{}).get(str(h),{}).get('n',0)>=80 for h in range(1,6)),z.get('horizons'))
r=[x for x in scan.get('ranking',[]) if x.get('exchange')=='HOSE'];ck('canonical VMEWS HOSE coverage',len(r)>=300,len(r));ck('dashboard consumed canonical scan',dash.get('canonicalRiskCoverage',0)>=300,dash.get('canonicalRiskCoverage'));ck('YELLOW liquidity eligibility',all(float(x.get('liquidity30',0))>=500_000_000 for x in dash['lists']['yellow']),dash['lists']['yellow'][:3]);ck('RED liquidity eligibility',all(float(x.get('liquidity30',0))>=500_000_000 for x in dash['lists']['red']),dash['lists']['red'][:3]);ck('live monitor PASS',live.get('status')=='PASS',live);ck('live monitor no bad hashes',not live.get('badHashes'),live.get('badHashes'));ck('live monitor five horizons',set(live.get('horizons',{}))==set('12345'),live.get('horizons',{}).keys());ck('live origin created',live.get('origins',0)>=1,live.get('origins'));ck('live model version current',live.get('modelVersion')==dash.get('modelVersion'),(live.get('modelVersion'),dash.get('modelVersion')))
# Ensure no evidence layer is presented as a dead placeholder.
html=(R/'forecast-final.html').read_text(encoding='utf-8');js=(R/'forecast-final-v11.js').read_text(encoding='utf-8')
for s in ['CHƯA CÓ','chưa khả dụng','không đủ tin','MẪU MỎNG','Hệ thống tách riêng','Mô hình chỉ vẽ']:
 ck('no dead UI phrase '+s,s not in html+js)
rep={'version':'VMEWS-V11-EXTENDED-ACCEPTANCE-1.0.0','tests':len(checks),'passed':sum(x[1] for x in checks),'failed':sum(not x[1] for x in checks),'failures':[{'name':n,'detail':d} for n,o,d in checks if not o]};(R/'data/forecast-v11-extended-acceptance.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(rep,ensure_ascii=False));sys.exit(1 if rep['failed'] else 0)
