import json, math, re, sys
from pathlib import Path
R=Path('.'); checks=[]
def ck(name,cond,detail=''):
    ok=bool(cond);checks.append((name,ok,str(detail)));print(('PASS ' if ok else 'FAIL ')+name+(f' :: {detail}' if detail else ''));return ok

def load(p):return json.loads((R/p).read_text(encoding='utf-8'))
js=(R/'forecast-final-v12.js').read_text(encoding='utf-8')
html=(R/'forecast-final-v12.html').read_text(encoding='utf-8')
mathjs=(R/'forecast-v12-math.js').read_text(encoding='utf-8')
trainer=(R/'scripts/train_forecast_v11_vnstock.py').read_text(encoding='utf-8')
adapter=(R/'scripts/vnstock_primary_history.py').read_text(encoding='utf-8')
builder=(R/'scripts/build_dashboard_v11_consistent.py').read_text(encoding='utf-8')

# Source lineage / fallback order
ck('VNStock adapter exists','vnstock_adjusted' in adapter)
ck('Unified first',adapter.index('VNSTOCK_UNIFIED')<adapter.index('VNSTOCK_VCI')<adapter.index('VNSTOCK_KBS'))
ck('trainer calls VNStock before Yahoo',trainer.index('vnstock_adjusted')<trainer.index("_YAHOO(sym"))
ck('Yahoo explicitly fallback only','YAHOO_ADJUSTED_FALLBACK' in trainer)
ck('local snapshot last resort','LOCAL_SNAPSHOT_LAST_RESORT' in trainer)
ck('corporate action guard retained','modelClose' in adapter and 'CA_LOG_JUMP' in adapter and 'rawClose' in trainer)
ck('chart exact model lineage','Exact accepted model history' in builder)
ck('dashboard avoids chart refetch','base.chart = model_chart' in builder)

# Forecast price math and chart semantics
for token in ['Math.exp','expectedPrice','lowPrice','highPrice','historicalUpRate','auditSummary']:
    ck('math helper '+token,token in mathjs)
ck('UI has explicit expected price','Giá dự kiến T+1' in html and 'Giá dự kiến T+5' in html)
ck('UI documents central scenario','kịch bản trung tâm' in html)
ck('tooltip present','chartTip' in html and 'showTip' in js)
for token in ['Giá dự kiến:','Vùng 20–80%:','Tỷ lệ tăng calibration:','Cỡ mẫu:','Nguồn giá:']:
    ck('tooltip field '+token,token in js)
ck('forecast path has five direct horizons','for(let i=1;i<=5;i++)' in js)
ck('whisker interval used',"c.moveTo(xx,yl);c.lineTo(xx,yh)" in js)
ck('no filled fan wedge',"c.closePath();c.fillStyle='rgba(226,171,70,.12)'" not in js)
ck('direction visible',all(x in js for x in ['TĂNG','GIẢM','ĐI NGANG']))

# Whole-basis decision engine
for token in ['Mô hình T+5','VMEWS risk','Thị trường','Tin & event study','Khối ngoại','Tự doanh','Vĩ mô','Cơ bản']:
    ck('decision basis '+token,token in js)
ck('RED is hard priority',"if(z.riskStatus==='RED')" in js and "label='GIẢM RỦI RO'" in js)
ck('YELLOW is hard warning',"else if(z.riskStatus==='YELLOW')" in js and "label='CẢNH BÁO RỦI RO'" in js)
ck('fundamentals context only','context only' in js and 'không ép hướng 1–5 phiên' in js)

# Backtest detail
for token in ['Alpha IC','Spread','Đúng hướng','MCC','Brier skill','ECE','Scenario rank IC','MAE improve','Coverage 20–80','gates R:']:
    ck('backtest field '+token,token in js)
ck('chronological audit disclosure','Chronological DEV → CAL → sealed AUD' in js)
ck('exact target disabled disclosure','exact target price bị vô hiệu hóa' in js)

# Relative data root keeps branch/commit-pinned data consistent with the page.
ck('no hardcoded main data root',"/main/data/" not in js and "const ROOT=new URL('.',document.currentScript" in js)

# Existing production snapshots must still satisfy basic model invariants if present.
if (R/'data/forecast-model-v11.json').exists():
    model=load('data/forecast-model-v11.json')
    ck('model has five horizons',set(model.get('horizons',{}))==set('12345'))
    for h in range(1,6):
        a=model['horizons'][str(h)].get('sealedAudit',{})
        ck(f'T+{h} sealed audit n',a.get('n',0)>=10000,a.get('n'))
        ck(f'T+{h} quant metrics finite',all(math.isfinite(float(a.get(k,0))) for k in ['alphaIC','alphaSpread','balancedAccuracy','mcc','coverage20_80']))

failed=[x for x in checks if not x[1]]
report={'version':'VMEWS-FORECAST-V12-ACCEPTANCE-1.0.0','tests':len(checks),'passed':len(checks)-len(failed),'failed':len(failed),'failures':[{'name':n,'detail':d} for n,_,d in failed]}
(R/'data/forecast-v12-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False));sys.exit(1 if failed else 0)
