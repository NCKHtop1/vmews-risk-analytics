"""Deterministic merge of five already-fitted V12 horizon artifacts; no refit."""
from __future__ import annotations
import argparse,copy,hashlib,json,math,pathlib
from datetime import datetime,timezone
HORIZONS=(1,2,3,4,5); REQUIRED=("forecast-model-v12.json","forecast-current-v12.json","forecast-dashboard-v12.json","forecast-backtest-v12.json","data-audit-v12.json","event-intelligence-v12.json"); ASSEMBLY_VERSION="VMEWS-V12-HORIZON-ASSEMBLY-1.0.0"
EV_FIELDS=("priceAfter","benchmarkReturn","benchmarkAvailable","benchmarkTargetDate","abnormalReturn","cumulativeAbnormalReturn","matureDate")
EV_H5=("maturedH5Records","benchmarkH5Available","benchmarkH5Coverage")
def _now():return datetime.now(timezone.utc).isoformat()
def _canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def _sha(x):return hashlib.sha256(x if isinstance(x,bytes) else _canon(x)).hexdigest()
def _load(p):return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
def _write(p,x):p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
def _finite(x):return isinstance(x,(int,float)) and math.isfinite(float(x))
def _strip(x):
    if isinstance(x,dict):return {k:_strip(v) for k,v in x.items() if k not in {"generatedAt","createdAt","updatedAt"}}
    if isinstance(x,list):return [_strip(v) for v in x]
    return x
def _same(label,a,b,h):
    if _sha(a)!=_sha(b):raise RuntimeError(f"cross-horizon invariant mismatch for {label}: h1={_sha(a)} h{h}={_sha(b)}")
def _evnames(h):return tuple(f"eventPrior{x}{int(h)}" for x in ("AR","Hit","N","Uncertainty"))
ALL_EV=set(x for h in HORIZONS for x in _evnames(h)); COMMON5={"eventPriorAR5","eventPriorHit5","eventPriorN5"}
def _model_common(m):return _strip({k:m.get(k) for k in ("version","target","universe","governance","dataSources")})
def _feature_common(m):
    e=copy.deepcopy(m.get("experts") or {});e["EVENT"]=[x for x in e.get("EVENT",[]) if x not in ALL_EV]
    return {"featureNames":[x for x in (m.get("featureNames") or []) if x not in ALL_EV],"experts":e}
def _validate_feature_contract(m,h):
    exp=set(_evnames(h))|COMMON5; f={x for x in (m.get("featureNames") or []) if x in ALL_EV};e={x for x in ((m.get("experts") or {}).get("EVENT") or []) if x in ALL_EV}
    if f!=exp or e!=exp:raise RuntimeError(f"horizon {h} event-prior feature contract mismatch: featureNames={sorted(f)} EVENT={sorted(e)} expected={sorted(exp)}")
def _ordered(xs):
    out=[];seen=set()
    for x in xs:
        if x not in seen:seen.add(x);out.append(x)
    return out
def _merge_features(P):
    first=list(P[1]["forecast-model-v12.json"].get("featureNames") or []);dyn=set(_evnames(1))-COMMON5;pos=[i for i,x in enumerate(first) if x in dyn]
    if not pos:raise RuntimeError("h1 featureNames missing horizon event-prior block")
    a,b=min(pos),max(pos)+1
    if any(x not in dyn for x in first[a:b]):raise RuntimeError("h1 horizon event-prior block is not contiguous")
    prefix=first[:a];suffix=[x for x in first[b:] if x not in ALL_EV];insert=[];seen=set(prefix)
    for h in HORIZONS:
        names=set(P[h]["forecast-model-v12.json"].get("featureNames") or [])
        for x in _evnames(h):
            if x in names and x not in seen:insert.append(x);seen.add(x)
    return _ordered(prefix+insert+suffix)
def _merge_experts(P):
    e=copy.deepcopy(P[1]["forecast-model-v12.json"].get("experts") or {});all_event=[]
    for h in HORIZONS:all_event+=((P[h]["forecast-model-v12.json"].get("experts") or {}).get("EVENT") or [])
    e["EVENT"]=_ordered(all_event);return e

def _current_common(c):return {"version":c.get("version"),"symbols":{s:_strip({k:v for k,v in r.items() if k!="horizons"}) for s,r in sorted((c.get("symbols") or {}).items())}}
def _dash_common(d):return _strip({k:d.get(k) for k in ("version","modelVersion","asOf","charts","dataAuditSummary")})
def _back_common(b):return _strip({"version":b.get("version"),"design":b.get("design")})
def _benchmark_alignment(a):return copy.deepcopy(((a.get("entityFilter") or {}).get("benchmarkAlignment") or {}))
def _benchmark_alignment_common(z):return {k:z.get(k) for k in ("method","joinKey","missingPolicy")}
def _data_audit_common(a):
    z=copy.deepcopy(a);entity=z.get("entityFilter")
    if isinstance(entity,dict):entity.pop("benchmarkAlignment",None)
    return _strip(z)
def _merge_data_audit(P):
    out=copy.deepcopy(P[1]["data-audit-v12.json"]);align={};ref=None
    for h in HORIZONS:
        z=_benchmark_alignment(P[h]["data-audit-v12.json"]);common=_benchmark_alignment_common(z)
        if ref is None:ref=common
        else:_same("benchmark-alignment-contract",ref,common,h)
        align[str(h)]=z
    entity=out.setdefault("entityFilter",{});entity["benchmarkAlignment"]={**(ref or {}),"scope":"HORIZON_SPECIFIC_EXACT_STOCK_MATURITY","byHorizon":align,"mergedWithoutAggregation":True}
    return out
def _event_top(e):
    out={k:v for k,v in e.items() if k not in {"generatedAt","records","summary"}};s=dict(e.get("summary") or {})
    for k in EV_H5:s.pop(k,None)
    out["summaryCommon"]=s;return _strip(out)
def _event_row(r):return {k:_strip(v) for k,v in r.items() if k not in EV_FIELDS}
def _rebuild_daily_ar_from_merged_car(row):
    """Daily AR is derived only after all exact-maturity CAR horizons have been merged.

    In isolated Hh jobs only arH is guaranteed to have passed through the exact VNINDEX maturity
    correction.  A partial's ar(H-1) can therefore still carry legacy pre-wrapper semantics and
    must never be used as the authority for merged daily AR.  Reconstructing here makes the
    additive log-return identity explicit: AR1=CAR1; ARh=CARh-CAR(h-1).  Missing adjacent CAR
    abstains rather than silently differencing across a gap.
    """
    car=row.get("cumulativeAbnormalReturn") or {};dar={}
    for h in HORIZONS:
        key=str(h);cur=car.get(key);prev=0.0 if h==1 else car.get(str(h-1))
        dar[key]=float(cur)-float(prev) if _finite(cur) and _finite(prev) else None
    row["abnormalReturn"]=dar
    return row
def _merge_events(P):
    first=P[1]["event-intelligence-v12.json"];top=_event_top(first);rr=first.get("records") or [];keys=[r.get("eventKey") for r in rr]
    if not rr or any(not k for k in keys) or len(keys)!=len(set(keys)):raise RuntimeError("event-intelligence reference has missing/duplicate eventKey")
    for h in HORIZONS:
        e=P[h]["event-intelligence-v12.json"] ; _same("event-intelligence-common",top,_event_top(e),h);r=e.get("records") or []
        if [x.get("eventKey") for x in r]!=keys:raise RuntimeError(f"event-intelligence eventKey/order mismatch at h{h}")
        for i,(a,b) in enumerate(zip(rr,r)):
            if _sha(_event_row(a))!=_sha(_event_row(b)):raise RuntimeError(f"event-intelligence common record mismatch at h{h} eventKey={keys[i]}")
    out=copy.deepcopy(P[5]["event-intelligence-v12.json"]);out["generatedAt"]=_now();merged=[]
    for i,ref in enumerate(rr):
        row=copy.deepcopy(ref)
        for f in EV_FIELDS:
            if f=="abnormalReturn":continue
            z={}
            for h in HORIZONS:
                for k,v in (P[h]["event-intelligence-v12.json"]["records"][i].get(f) or {}).items():
                    if k in z and z[k]!=v:raise RuntimeError(f"event-intelligence conflicting {f}[{k}] for eventKey={keys[i]}")
                    z[k]=copy.deepcopy(v)
            row[f]=z
        _rebuild_daily_ar_from_merged_car(row);merged.append(row)
    out["records"]=merged;return out
def _load_partial(root,h):
    d=pathlib.Path(root)/f"h{h}";missing=[x for x in REQUIRED if not (d/x).exists()]
    if missing:raise RuntimeError(f"horizon {h} partial missing files: {missing}")
    z={n:_load(d/n) for n in REQUIRED};mh=sorted((z["forecast-model-v12.json"].get("horizons") or {}).keys());bh=sorted((z["forecast-backtest-v12.json"].get("horizons") or {}).keys());ch=sorted((z["forecast-backtest-v12.json"].get("cases") or {}).keys())
    if mh!=[str(h)] or bh!=[str(h)] or ch!=[str(h)]:raise RuntimeError(f"horizon {h} partial malformed: model={mh} backtest={bh} cases={ch}")
    _validate_feature_contract(z["forecast-model-v12.json"],h);sy=z["forecast-current-v12.json"].get("symbols") or {}
    if not sy or any(sorted((r.get("horizons") or {}).keys())!=[str(h)] for r in sy.values()):raise RuntimeError(f"horizon {h} current partial malformed")
    return z
def _source(outdir):
    p=pathlib.Path(outdir)/"v12-source-probe.json"
    if not p.exists():return None
    z=_load(p);snap=z.get("snapshot") or {};sha=str(snap.get("snapshotFileSha256") or "")
    if z.get("status")!="PASS" or z.get("mode")!="IMMUTABLE_FROZEN_SNAPSHOT" or z.get("runtimeNetworkPriceFetch") is not False or z.get("runtimeProviderSwitching") is not False or len(sha)!=64:raise RuntimeError(f"source probe is not immutable PASS: {z}")
    return {"snapshotFileSha256":sha,"inputManifestSha256":snap.get("inputManifestSha256"),"asOf":snap.get("asOf")}
def merge_partials(partials_root,outdir):
    P={h:_load_partial(partials_root,h) for h in HORIZONS};first=P[1];mr=_model_common(first["forecast-model-v12.json"]);fr=_feature_common(first["forecast-model-v12.json"]);cr=_current_common(first["forecast-current-v12.json"]);dr=_data_audit_common(first["data-audit-v12.json"]);br=_back_common(first["forecast-backtest-v12.json"]);ar=_dash_common(first["forecast-dashboard-v12.json"]);fps={}
    for h,p in P.items():
        _same("model-common",mr,_model_common(p["forecast-model-v12.json"]),h);_same("model-feature-common",fr,_feature_common(p["forecast-model-v12.json"]),h);_same("current-common",cr,_current_common(p["forecast-current-v12.json"]),h);_same("data-audit-common",dr,_data_audit_common(p["data-audit-v12.json"]),h);_same("backtest-common",br,_back_common(p["forecast-backtest-v12.json"]),h);_same("dashboard-common",ar,_dash_common(p["forecast-dashboard-v12.json"]),h);fps[str(h)]={n:_sha(_strip(o)) for n,o in sorted(p.items())}
    model=copy.deepcopy(first["forecast-model-v12.json"]);model["createdAt"]=_now();model["featureNames"]=_merge_features(P);model["experts"]=_merge_experts(P);model["horizons"]={str(h):copy.deepcopy(P[h]["forecast-model-v12.json"]["horizons"][str(h)]) for h in HORIZONS};ph=[h for h in HORIZONS if model["horizons"][str(h)].get("priceStatus")=="PASS"];dh=[h for h in HORIZONS if model["horizons"][str(h)].get("directionStatus")=="PASS"];model["promotion"]={"status":"PASS" if ph==list(HORIZONS) else "REVIEW","directPriceHorizons":ph,"directionHorizons":dh,"exactTargetPrice":False,"calibratedScenarioPrice":True,"rule":"All five direct price horizons must pass positive-skill ranking + quantile scenario + CSCV/PBO + embargoed literal walk-forward generalization gates. Probability-up is rendered only when the independent positive-Brier direction gate also passes."};model.setdefault("governance",{})["priceSourcePolicy"]="Certified immutable frozen-source snapshot; runtime network price fetch and provider switching disabled";model["execution"]={"version":ASSEMBLY_VERSION,"mode":"FIVE_ISOLATED_DIRECT_HORIZON_JOBS_THEN_DETERMINISTIC_MERGE","scientificSemanticsChanged":False,"horizons":list(HORIZONS),"partialFingerprints":fps}
    current=copy.deepcopy(first["forecast-current-v12.json"]);current["generatedAt"]=_now();symbols=set(current.get("symbols") or {})
    for h in HORIZONS:
        if set((P[h]["forecast-current-v12.json"].get("symbols") or {}))!=symbols:raise RuntimeError(f"current symbol set mismatch at h{h}")
    for s in sorted(symbols):current["symbols"][s]["horizons"]={str(h):copy.deepcopy(P[h]["forecast-current-v12.json"]["symbols"][s]["horizons"][str(h)]) for h in HORIZONS}
    back=copy.deepcopy(first["forecast-backtest-v12.json"]);back["generatedAt"]=_now();back["horizons"]={str(h):copy.deepcopy(P[h]["forecast-backtest-v12.json"]["horizons"][str(h)]) for h in HORIZONS};back["cases"]={str(h):copy.deepcopy(P[h]["forecast-backtest-v12.json"]["cases"][str(h)]) for h in HORIZONS};back["execution"]={"version":ASSEMBLY_VERSION,"scientificSemanticsChanged":False}
    dash=copy.deepcopy(P[5]["forecast-dashboard-v12.json"]);dash["generatedAt"]=_now();dash["promotion"]=copy.deepcopy(model["promotion"]);dash["symbols"]=copy.deepcopy(current["symbols"]);dash["execution"]={"version":ASSEMBLY_VERSION,"scientificSemanticsChanged":False}
    audit=_merge_data_audit(P);audit["fullExecution"]={"version":ASSEMBLY_VERSION,"mode":"PARALLEL_HORIZON_ORCHESTRATION_ONLY","scientificSemanticsChanged":False};events=_merge_events(P);outdir=pathlib.Path(outdir);src=_source(outdir)
    if src:model["execution"]["frozenSource"]=src;back["execution"]["frozenSource"]=src;dash["execution"]["frozenSource"]=src;audit["fullExecution"]["frozenSource"]=src
    outputs={"forecast-model-v12.json":model,"forecast-current-v12.json":current,"forecast-dashboard-v12.json":dash,"forecast-backtest-v12.json":back,"data-audit-v12.json":audit,"event-intelligence-v12.json":events}
    for n,o in outputs.items():_write(outdir/n,o)
    z={"version":ASSEMBLY_VERSION,"generatedAt":_now(),"status":"PASS","scientificSemanticsChanged":False,"horizons":list(HORIZONS),"priceHorizonsPassed":ph,"directionHorizonsPassed":dh,"promotion":model["promotion"]["status"],"symbols":len(symbols),"partialFingerprints":fps,"frozenSource":src,"outputSha256":{n:_sha((outdir/n).read_bytes()) for n in REQUIRED}};_write(outdir/"v12-horizon-assembly.json",z);print(json.dumps({"v12HorizonAssembly":z},ensure_ascii=False),flush=True);return z
def main():
    p=argparse.ArgumentParser();p.add_argument("--partials-root",required=True);p.add_argument("--outdir",default="data");a=p.parse_args();merge_partials(a.partials_root,a.outdir)
if __name__=="__main__":main()