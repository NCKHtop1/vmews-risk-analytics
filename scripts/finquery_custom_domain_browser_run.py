#!/usr/bin/env python3
"""Exercise public FinQuery Pages UI while auth remains enforced on custom domain.

Uncredentialed Selenium cannot open the protected production dashboard.
The production-domain smoke checks the login and 401/307 auth gates instead.
"""
import os
import subprocess
import sys
from pathlib import Path
import yaml

root=Path(__file__).resolve().parents[1]
with (root/".github/workflows/financial-dashboard-browser-smoke.yml").open(encoding="utf-8") as f:
    flow=yaml.safe_load(f)
steps=flow["jobs"]["browser-smoke"]["steps"]
step=next(item for item in steps if "Exercise production chart" in item.get("name",""))
script=step["run"]
anchor="https://nckhtop1.github.io/vmews-risk-analytics/financial-report/"
if script.count(anchor)!=2:
    raise SystemExit(f"Expected exactly 2 public Pages URL anchors, found {script.count(anchor)}")
env=os.environ.copy()
env["EXPECTED_SHA"]=""
print("FINQUERY_PUBLIC_PAGES_UI_BROWSER_START",anchor,flush=True)
result=subprocess.run(["bash","-euo","pipefail"],input=script,text=True,env=env,timeout=700)
print("FINQUERY_PUBLIC_PAGES_UI_BROWSER_RESULT",result.returncode,flush=True)
sys.exit(result.returncode)
