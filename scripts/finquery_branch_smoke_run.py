#!/usr/bin/env python3
"""Run the existing official browser smoke from THIS branch as-is against public Pages."""
import os,subprocess,sys,yaml
with open(".github/workflows/financial-dashboard-browser-smoke.yml",encoding="utf-8") as f: workflow=yaml.safe_load(f)
job=workflow["jobs"]["browser-smoke"]
step=next(s for s in job["steps"] if "Exercise production chart" in s.get("name",""))
script=step["run"]
if "wait.until" not in script or "vn_open" not in script:raise AssertionError("browser smoke change missing")
env=os.environ.copy()
env["EXPECTED_SHA"]=""
r=subprocess.run(["bash","-euxo","pipefail"],input=script,text=True,env=env,timeout=620)
print("BRANCH_BROWSER_SMOKE_EXIT="+str(r.returncode),flush=True)
sys.exit(r.returncode)
