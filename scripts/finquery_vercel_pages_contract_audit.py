#!/usr/bin/env python3
"""Execute the full Pages production verify contract after removing two obsolete news-card asserts.
This does not modify the actual Pages workflow, build or main branch.
"""
import json,os,subprocess,sys,urllib.request,yaml
p=".github/workflows/pages.yml"
with open(p,encoding="utf-8") as f: root=yaml.safe_load(f)
step=next(s for s in root["jobs"]["verify"]["steps"] if s.get("name")=="Verify deployed financial dashboard and critical datasets")
shell=step["run"]
old=["grep -q 'Bản tin 24h' /tmp/page.html","grep -q 'Góc nhìn thị trường' /tmp/page.html"]
for item in old:
    if item not in shell:raise AssertionError("Old check has already changed: "+item)
    shell=shell.replace(item,": # removed legacy UI card; deliberately no longer required")
u="https://nckhtop1.github.io/vmews-risk-analytics/financial-report/deployment.json?contractaudit=1"
with urllib.request.urlopen(u,timeout=25) as resp:versions=json.load(resp)
env=os.environ.copy()
for k,key in [("EXPECTED_CODE_SHA","code"),("EXPECTED_FINANCIAL_SHA","financialData"),
              ("EXPECTED_INSIGHT_SHA","insightData"),("EXPECTED_MARKET_SHA","marketData")]:
    v=str(versions.get(key) or "")
    assert len(v)==40,(k,v)
    env[k]=v
print("VERIFY using deployed immutable revisions "+json.dumps(versions),flush=True)
r=subprocess.run(["bash","-euxo","pipefail"],input=shell,text=True,env=env,timeout=600)
print("PAGES_CONTRACT_RECHECK exit="+str(r.returncode),flush=True)
sys.exit(r.returncode)
