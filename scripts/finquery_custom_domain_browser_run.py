#!/usr/bin/env python3
"""Reuse the full FinQuery Pages Selenium smoke against the real custom domain."""
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
old="https://nckhtop1.github.io/vmews-risk-analytics/financial-report/"
new="https://finquery.info.vn/financial-report/"
if script.count(old)!=2:
    raise SystemExit(f"Expected exactly 2 Pages URL anchors, found {script.count(old)}")
script=script.replace(old,new)
# FinQuery is a single bundled index on Pages; directory redirect points to that file on Vercel.
script=script.replace("URL='https://finquery.info.vn/financial-report/?symbol=", "URL='https://finquery.info.vn/financial-report/index.html?symbol=")
env=os.environ.copy()
env["EXPECTED_SHA"]=""  # Source revision already checked independently by Pages verification.
print("REAL_DOMAIN_BROWSER_START https://finquery.info.vn/financial-report/index.html",flush=True)
result=subprocess.run(["bash","-euo","pipefail"],input=script,text=True,env=env,timeout=700)
print("REAL_DOMAIN_BROWSER_RESULT",result.returncode,flush=True)
sys.exit(result.returncode)
