"""Deterministically merge five isolated V12 horizon runs.

This merger performs no fitting, calibration, gate selection, or prediction transformation.
It validates cross-horizon provenance and merges only fields that are scientifically defined
per direct horizon (model feature metadata and event T+h outcome maps).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import re
from datetime import datetime, timezone

HORIZONS=(1,2,3,4,5)
REQUIRED=(
    "forecast-model-v12.json","forecast-current-v12.json","forecast-dashboard-v12.json",
    "forecast-backtest-v12.json","data-audit-v12.json","event-intelligence-v12.json",
)
ASSEMBLY_VERSION="VMEWS-V12-HORIZON-ASSEMBLY-1.1.0"
_EVENT_HORIZON_FEATURE=re.compile(r"^eventPrior(?:AR|Hit|N|Uncertainty)[1-5]$")
_EVENT_MAP_FIELDS=(
    "priceAfter","benchmarkReturn","benchmarkAvailable","benchmarkTargetDate",
    "abnormalReturn","cumulativeAbnormalReturn","matureDate",
)
_EVENT_H5_SUMMARY_FIELDS=("maturedH5Records","benchmarkH5Available","benchmarkH5Coverage")


def _now(): return datetime.now(timezone.utc).isoformat()

def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")

def _sha(value): return hashlib.sha256(value if isinstance(value,bytes) else _canonical(value)).hexdigest()

def _load(path): return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

def _write(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")

def _strip_volatile(value):
    if isinstance(value,dict):
        return {k:_strip_volatile(v) for k,v in value.items() if k not in {"generatedAt","createdAt","updatedAt"}}
    if isinstance(value,list): return [_strip_volatile(v) for v in value]
    return value

def _assert_same(label,reference,candidate,horizon):
    a=_sha(reference);b=_sha(candidate)
    if a!=b: raise RuntimeError(f"cross-horizon invariant mismatch for {label}: h1={a} h{horizon}={b}")

def _ordered_union(sequences):
    out=[];seen=set()
    for seq in sequences:
        for x in seq or []:
            if x not in seen:seen.add(x);out.append(copy.deepcopy(x))
    return out

def _model_static_common(model):
    keys=("version","target","universe","governance","dataSources")
    return _strip_volatile({k:model.get(k) for k in keys})

def _normalized_features(seq):
    return [x for x in (seq or []) if not _EVENT_HORIZON_FEATURE.match(str(x))]

def _validate_and_merge_model_metadata(partials):
    models={h:partials[h]["forecast-model-v12.json"] for h in HORIZONS};ref=models[1]
    for h in HORIZONS[1:]:
        _assert_same("model-static-common",_model_static_common(ref),_model_static_common(models[h]),h)
        _assert_same("model-feature-core",_normalized_features(ref.get("featureNames")),_normalized_features(models[h].get("featureNames")),h)
    ref_experts=ref.get("experts") or {}
    for h in HORIZONS[1:]:
        cur=models[h].get("experts") or {}
        if set(cur)!=set(ref_experts):raise RuntimeError(f"expert key set mismatch at h{h}")
        for name in sorted(ref_experts):
            a=ref_experts[name];b=cur[name]
            if name=="EVENT":_assert_same(f"expert-{name}-core",_normalized_features(a),_normalized_features(b),h)
            else:_assert_same(f"expert-{name}",a,b,h)
    feature_names=_ordered_union([models[h].get("featureNames") or [] for h in HORIZONS])
    experts={name:_ordered_union([(models[h].get("experts") or {}).get(name) or [] for h in HORIZONS]) for name in ref_experts}
    added=[x for x in feature_names if x not in (ref.get("featureNames") or [])]
    illegal=[x for x in added if not _EVENT_HORIZON_FEATURE.match(str(x))]
    if illegal:raise RuntimeError(f"illegal cross-horizon feature union additions: {illegal[:20]}")
    return feature_names,experts

def _current_common(current):
    out={"version":current.get("version"),"symbols":{}}
    for symbol,row in sorted((current.get("symbols") or {}).items()):
        out["symbols"][symbol]=_strip_volatile({k:v for k,v in row.items() if k!="horizons"})
    return out

def _dashboard_common(dashboard):
    return _strip_volatile({
        "version":dashboard.get("version"),"modelVersion":dashboard.get("modelVersion"),
        "asOf":dashboard.get("asOf"),"charts":dashboard.get("charts"),
        "dataAuditSummary":dashboard.get("dataAuditSummary"),
    })

def _backtest_common(backtest):
    return _strip_volatile({"version":backtest.get("version"),"design":backtest.get("design")})

def _event_record_common(record):
    return _strip_volatile({k:v for k,v in record.items() if k not in _EVENT_MAP_FIELDS})

def _event_top_common(db):
    return _strip_volatile({k:v for k,v in db.items() if k not in {"records","summary","generatedAt","createdAt","updatedAt"}})

def _event_summary_common(summary):
    return {k:v for k,v in (summary or {}).items() if k not in _EVENT_H5_SUMMARY_FIELDS}

def _validate_horizon_map(record,h,field):
    value=record.get(field)
    if not isinstance(value,dict):raise RuntimeError(f"event {record.get('eventKey')} field {field} is not a horizon map at h{h}")
    bad=[k for k in value if str(k)!=str(h)]
    if bad:raise RuntimeError(f"event {record.get('eventKey')} field {field} contains foreign horizon keys at h{h}: {bad}")

def _merge_event_intelligence(partials):
    dbs={h:partials[h]["event-intelligence-v12.json"] for h in HORIZONS};ref=dbs[1]
    for h in HORIZONS[1:]:
        _assert_same("event-top-common",_event_top_common(ref),_event_top_common(dbs[h]),h)
        _assert_same("event-summary-common",_event_summary_common(ref.get("summary")),_event_summary_common(dbs[h].get("summary")),h)
    refs=ref.get("records") or [];keys=[str(r.get("eventKey")) for r in refs]
    if len(keys)!=len(set(keys)):raise RuntimeError("duplicate eventKey in h1 event-intelligence")
    by_h={}
    for h in HORIZONS:
        rows=dbs[h].get("records") or []
        if len(rows)!=len(refs):raise RuntimeError(f"event record count mismatch h1={len(refs)} h{h}={len(rows)}")
        k=[str(r.get("eventKey")) for r in rows]
        if k!=keys:raise RuntimeError(f"event record order/identity mismatch at h{h}")
        by_h[h]=rows
    merged=[]
    for i,key in enumerate(keys):
        base=copy.deepcopy(refs[i]);common=_event_record_common(refs[i])
        for field in _EVENT_MAP_FIELDS:base[field]={}
        for h in HORIZONS:
            row=by_h[h][i];_assert_same(f"event-record-common:{key}",common,_event_record_common(row),h)
            for field in _EVENT_MAP_FIELDS:
                _validate_horizon_map(row,h,field);base[field].update(copy.deepcopy(row[field]))
        merged.append(base)
    out=copy.deepcopy(ref);out["generatedAt"]=_now();out["records"]=merged;out["summary"]=copy.deepcopy(dbs[5].get("summary") or {})
    out["assembly"]={
        "version":ASSEMBLY_VERSION,"horizons":list(HORIZONS),"recordIdentityValidated":True,
        "commonFieldsValidated":True,"mergedFields":list(_EVENT_MAP_FIELDS),"scientificSemanticsChanged":False,
    }
    return out

def _partial_dir(root,horizon): return pathlib.Path(root)/f"h{int(horizon)}"

def _load_partial(root,horizon):
    folder=_partial_dir(root,horizon);missing=[name for name in REQUIRED if not (folder/name).exists()]
    if missing:raise RuntimeError(f"horizon {horizon} partial missing files: {missing}")
    out={name:_load(folder/name) for name in REQUIRED}
    model_h=sorted((out["forecast-model-v12.json"].get("horizons") or {}).keys())
    if model_h!=[str(horizon)]:raise RuntimeError(f"horizon {horizon} model partial contains horizons {model_h}")
    backtest_h=sorted((out["forecast-backtest-v12.json"].get("horizons") or {}).keys());case_h=sorted((out["forecast-backtest-v12.json"].get("cases") or {}).keys())
    if backtest_h!=[str(horizon)] or case_h!=[str(horizon)]:raise RuntimeError(f"horizon {horizon} backtest partial malformed: horizons={backtest_h} cases={case_h}")
    symbols=out["forecast-current-v12.json"].get("symbols") or {}
    if not symbols:raise RuntimeError(f"horizon {horizon} current partial has no symbols")
    bad=[s for s,row in symbols.items() if sorted((row.get("horizons") or {}).keys())!=[str(horizon)]]
    if bad:raise RuntimeError(f"horizon {horizon} current partial malformed for symbols {bad[:10]}")
    return out

def _source_identity(outdir):
    probe_path=pathlib.Path(outdir)/"v12-source-probe.json"
    if not probe_path.exists():return None
    probe=_load(probe_path)
    if probe.get("status")!="PASS" or probe.get("mode")!="IMMUTABLE_FROZEN_SNAPSHOT":raise RuntimeError(f"source probe is not immutable PASS: {probe}")
    if probe.get("runtimeNetworkPriceFetch") is not False:raise RuntimeError("source probe reports runtimeNetworkPriceFetch != false")
    if probe.get("runtimeProviderSwitching") is not False:raise RuntimeError("source probe reports runtimeProviderSwitching != false")
    snap=probe.get("snapshot") or {};sha=str(snap.get("snapshotFileSha256") or "")
    if len(sha)!=64:raise RuntimeError(f"invalid frozen source snapshot sha: {sha!r}")
    return {"snapshotFileSha256":sha,"inputManifestSha256":snap.get("inputManifestSha256"),"asOf":snap.get("asOf")}

def merge_partials(partials_root,outdir):
    partials={h:_load_partial(partials_root,h) for h in HORIZONS};first=partials[1]
    feature_names,experts=_validate_and_merge_model_metadata(partials)
    current_ref=_current_common(first["forecast-current-v12.json"]);data_ref=_strip_volatile(first["data-audit-v12.json"])
    backtest_ref=_backtest_common(first["forecast-backtest-v12.json"]);dashboard_ref=_dashboard_common(first["forecast-dashboard-v12.json"])
    fingerprints={}
    for h,part in partials.items():
        _assert_same("current-common",current_ref,_current_common(part["forecast-current-v12.json"]),h)
        _assert_same("data-audit",data_ref,_strip_volatile(part["data-audit-v12.json"]),h)
        _assert_same("backtest-common",backtest_ref,_backtest_common(part["forecast-backtest-v12.json"]),h)
        _assert_same("dashboard-common",dashboard_ref,_dashboard_common(part["forecast-dashboard-v12.json"]),h)
        fingerprints[str(h)]={name:_sha(_strip_volatile(obj)) for name,obj in sorted(part.items())}

    model=copy.deepcopy(first["forecast-model-v12.json"]);model["createdAt"]=_now();model["featureNames"]=feature_names;model["experts"]=experts
    model["horizons"]={str(h):copy.deepcopy(partials[h]["forecast-model-v12.json"]["horizons"][str(h)]) for h in HORIZONS}
    price_h=[h for h in HORIZONS if model["horizons"][str(h)].get("priceStatus")=="PASS"]
    direction_h=[h for h in HORIZONS if model["horizons"][str(h)].get("directionStatus")=="PASS"]
    model["promotion"]={
        "status":"PASS" if price_h==list(HORIZONS) else "REVIEW","directPriceHorizons":price_h,"directionHorizons":direction_h,
        "exactTargetPrice":False,"calibratedScenarioPrice":True,
        "rule":"All five direct price horizons must pass positive-skill ranking + quantile scenario + CSCV/PBO + embargoed literal walk-forward generalization gates. Probability-up is rendered only when the independent positive-Brier direction gate also passes.",
    }
    model.setdefault("governance",{})["priceSourcePolicy"]="Certified immutable frozen-source snapshot; runtime network price fetch and provider switching disabled"
    model["execution"]={
        "version":ASSEMBLY_VERSION,"mode":"FIVE_ISOLATED_DIRECT_HORIZON_JOBS_THEN_DETERMINISTIC_MERGE","scientificSemanticsChanged":False,
        "horizons":list(HORIZONS),"partialFingerprints":fingerprints,
        "horizonMetadataMerge":{"featureNames":"ORDERED_UNION_WITH_STRICT_EVENT_PRIOR_ALLOWLIST","experts.EVENT":"ORDERED_UNION_WITH_STRICT_EVENT_PRIOR_ALLOWLIST"},
    }

    current=copy.deepcopy(first["forecast-current-v12.json"]);current["generatedAt"]=_now();symbol_set=set(current.get("symbols") or {})
    for h in HORIZONS:
        other=partials[h]["forecast-current-v12.json"].get("symbols") or {}
        if set(other)!=symbol_set:raise RuntimeError(f"current symbol set mismatch at h{h}: {len(other)} vs {len(symbol_set)}")
    for symbol in sorted(symbol_set):
        current["symbols"][symbol]["horizons"]={str(h):copy.deepcopy(partials[h]["forecast-current-v12.json"]["symbols"][symbol]["horizons"][str(h)]) for h in HORIZONS}

    backtest=copy.deepcopy(first["forecast-backtest-v12.json"]);backtest["generatedAt"]=_now()
    backtest["horizons"]={str(h):copy.deepcopy(partials[h]["forecast-backtest-v12.json"]["horizons"][str(h)]) for h in HORIZONS}
    backtest["cases"]={str(h):copy.deepcopy(partials[h]["forecast-backtest-v12.json"]["cases"][str(h)]) for h in HORIZONS};backtest["execution"]={"version":ASSEMBLY_VERSION,"scientificSemanticsChanged":False}

    dashboard=copy.deepcopy(partials[5]["forecast-dashboard-v12.json"]);dashboard["generatedAt"]=_now();dashboard["promotion"]=copy.deepcopy(model["promotion"]);dashboard["symbols"]=copy.deepcopy(current["symbols"]);dashboard["execution"]={"version":ASSEMBLY_VERSION,"scientificSemanticsChanged":False}
    data_audit=copy.deepcopy(first["data-audit-v12.json"]);data_audit["fullExecution"]={"version":ASSEMBLY_VERSION,"mode":"PARALLEL_HORIZON_ORCHESTRATION_ONLY","scientificSemanticsChanged":False}
    event_db=_merge_event_intelligence(partials)

    outdir=pathlib.Path(outdir);source=_source_identity(outdir)
    if source:
        model["execution"]["frozenSource"]=source;backtest["execution"]["frozenSource"]=source;dashboard["execution"]["frozenSource"]=source;data_audit["fullExecution"]["frozenSource"]=source
    outputs={
        "forecast-model-v12.json":model,"forecast-current-v12.json":current,"forecast-dashboard-v12.json":dashboard,
        "forecast-backtest-v12.json":backtest,"data-audit-v12.json":data_audit,"event-intelligence-v12.json":event_db,
    }
    for name,obj in outputs.items():_write(outdir/name,obj)
    assembly={
        "version":ASSEMBLY_VERSION,"generatedAt":_now(),"status":"PASS","scientificSemanticsChanged":False,"horizons":list(HORIZONS),
        "priceHorizonsPassed":price_h,"directionHorizonsPassed":direction_h,"promotion":model["promotion"]["status"],"symbols":len(symbol_set),
        "partialFingerprints":fingerprints,"frozenSource":source,
        "horizonMetadataMerge":{"status":"PASS","featureNames":len(feature_names),"eventExpertFeatures":len(experts.get("EVENT") or [])},
        "eventIntelligenceMerge":{"status":"PASS","records":len(event_db.get("records") or []),"horizonMapFields":list(_EVENT_MAP_FIELDS)},
        "outputSha256":{name:_sha(pathlib.Path(outdir/name).read_bytes()) for name in REQUIRED},
    }
    _write(outdir/"v12-horizon-assembly.json",assembly);print(json.dumps({"v12HorizonAssembly":assembly},ensure_ascii=False),flush=True);return assembly

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--partials-root",required=True);parser.add_argument("--outdir",default="data")
    args=parser.parse_args();merge_partials(args.partials_root,args.outdir)

if __name__=="__main__":main()
