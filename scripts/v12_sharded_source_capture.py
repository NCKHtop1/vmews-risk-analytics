"""Resumable, sharded VNStock-only source acquisition for VMEWS V12.

This module changes orchestration only. Scientific source rules and final gates are
reused from freeze_v12_source_snapshot.py unchanged. Captured symbol histories are
checkpointed on one dedicated branch per shard so successful symbols survive runner
or workflow failure and are never fetched again within the same immutable capture
policy/as-of epoch.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import pathlib
import runpy
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WORKFLOW = ROOT / ".github" / "workflows" / "v12-source-freeze-resilient.yml"
PLAN_PATH = DATA / "v12-source-shard-plan.json"
ASSEMBLY_PATH = DATA / "v12-source-shard-assembly.json"
CHECKPOINT_ROOT = pathlib.PurePosixPath("checkpoints/v12-source")

POLICY_VERSION = "VMEWS-V12-VNSTOCK-SHARDED-RESUMABLE-1.0.0"
PLAN_VERSION = "VMEWS-V12-SOURCE-SHARD-PLAN-1.0.0"
CHECKPOINT_VERSION = "VMEWS-V12-SOURCE-SHARD-CHECKPOINT-1.0.0"
CHECKPOINT_MANIFEST_VERSION = "VMEWS-V12-SOURCE-SHARD-CHECKPOINT-MANIFEST-1.0.0"
ASSEMBLY_VERSION = "VMEWS-V12-SOURCE-SHARD-ASSEMBLY-1.0.0"
DEFAULT_SHARDS = 8
DEFAULT_CHECKPOINT_EVERY = 5


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(value):
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = _canonical(value)
    return hashlib.sha256(raw).hexdigest()


def _stable(v):
    try:
        x = float(v)
        return round(x, 10) if math.isfinite(x) else None
    except Exception:
        return None


def row_fingerprint(rows):
    arr = [[
        str(r.get("date", ""))[:10],
        _stable(r.get("open")),
        _stable(r.get("high")),
        _stable(r.get("low")),
        _stable(r.get("close")),
        _stable(r.get("modelClose", r.get("close"))),
        _stable(r.get("volume")),
        _stable(r.get("adjustmentFactor", 1.0)),
    ] for r in rows]
    return _sha(arr)


def _git(*args, cwd=ROOT, check=True, text=True):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=text,
    )


def _git_out(*args, cwd=ROOT):
    return _git(*args, cwd=cwd).stdout.strip()


def _runtime_identity():
    scripts_tree = _git_out("rev-parse", "HEAD:scripts")
    source_sha = os.environ.get("GITHUB_SHA") or _git_out("rev-parse", "HEAD")
    workflow_sha = _sha(WORKFLOW.read_bytes())
    runtime_policy = {
        "networkCallTimeoutSeconds": float(os.environ.get("V12_NETWORK_CALL_TIMEOUT", "12")),
        "symbolWallBudgetSeconds": float(os.environ.get("V12_SYMBOL_WALL_BUDGET", "45")),
        "universeWallBudgetSeconds": float(os.environ.get("V12_UNIVERSE_WALL_BUDGET", "20")),
        "minRows": int(os.environ.get("V12_MIN_ROWS", "520")),
        "vnstockIntervalSeconds": float(os.environ.get("V12_VNSTOCK_INTERVAL", "6.50")),
        "rawReturnGuard": float(os.environ.get("V12_MAX_RAW_RETURN_GUARD", "0.12")),
        "crossSourceMADLimit": float(os.environ.get("V12_CROSS_SOURCE_MAD_LIMIT", "0.003")),
        "yahooRuntimeNetworkCall": False,
        "globalCircuitBreaker": False,
    }
    return {
        "sourceTriggerSha": source_sha,
        "runtimeScriptsTreeSha": scripts_tree,
        "workflowSha256": workflow_sha,
        "runtimePolicy": runtime_policy,
    }


def _assignment(current_symbols, historical_symbols, shard_count):
    shards = {str(i): [] for i in range(shard_count)}
    for i, symbol in enumerate(sorted(current_symbols)):
        shards[str(i % shard_count)].append(symbol)
    offset = len(current_symbols) % shard_count
    for i, symbol in enumerate(sorted(historical_symbols)):
        shards[str((offset + i) % shard_count)].append(symbol)
    return shards


def _modal_end(store, current_symbols):
    ends = [
        str((store.get(s) or [{}])[-1].get("date", ""))[:10]
        for s in current_symbols
        if store.get(s)
    ]
    if not ends:
        return None
    counts = Counter(ends)
    return max(counts, key=lambda d: (counts[d], d))


def normalize_store_to_asof(store, as_of):
    out = {}
    for symbol, rows in sorted(store.items()):
        kept = [r for r in rows if str(r.get("date", ""))[:10] <= as_of]
        if kept:
            out[symbol] = kept
    return out


def _dynamic_vci_event_window(capture):
    """Remove the old hard-coded event end date without changing CA semantics."""
    def dynamic(symbol, attempts):
        try:
            from vnstock.explorer.vci import Company

            start, end = capture.base._history_window(8)
            company = Company(symbol=symbol, show_log=False)
            events = company._fetch_events(
                event_codes="DIV,ISS",
                from_date=str(start).replace("-", "")[:8],
                to_date=str(end).replace("-", "")[:8],
                page=0,
                size=500,
            )
            dates = set()
            count = 0
            for event in events or []:
                if not isinstance(event, dict):
                    continue
                count += 1
                value = event.get("exrightDate") or event.get("exright_date")
                if value:
                    dates.add(str(value)[:10])
            audit = {
                "source": "VNSTOCK_VCI_EVENT_REFERENCE",
                "provider": "Vietcap IQ corporate events",
                "api": "vnstock.explorer.vci.Company._fetch_events",
                "eventCodes": "DIV,ISS",
                "eventCount": count,
                "exrightDateCount": len(dates),
                "eventWindowStart": str(start)[:10],
                "eventWindowEnd": str(end)[:10],
                "role": "EVENT_BOUNDARY_CLASSIFICATION_ONLY_NOT_RETURN_ADJUSTMENT",
            }
            attempts.append({
                "stage": "VCI_CORPORATE_ACTION_EVENT_REFERENCE",
                "ok": True,
                **audit,
            })
            return dates, audit
        except BaseException as exc:
            attempts.append({
                "stage": "VCI_CORPORATE_ACTION_EVENT_REFERENCE",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:700],
            })
            return set(), None

    capture._vci_corporate_action_dates = dynamic


def _install_capture_stack():
    import v12_source_capture as capture
    import v12_reference_resilience as resilience
    import v12_universe as universe
    import v12_freeze_runtime_guard as runtime_guard
    from v12_source_capture_methodfix import install as install_continuity

    _dynamic_vci_event_window(capture)
    install_continuity()
    source_audit = resilience.install(capture, max_attempts=2, backoff_seconds=(2.0,))
    runtime_audit = runtime_guard.install(capture, universe, resilience, repo_root=ROOT)
    return capture, resilience, universe, runtime_guard, source_audit, runtime_audit


def _symbol_budget(runtime_guard):
    return max(5.0, float(os.environ.get("V12_SYMBOL_WALL_BUDGET", "45")))


def _capture_one(capture, runtime_guard, symbol):
    with runtime_guard._deadline(_symbol_budget(runtime_guard)):
        return capture.capture_price_history(symbol)


def _preflight(capture, runtime_guard, symbols):
    anchors = [s for s in ("FPT", "VCB", "HPG") if s in set(symbols)]
    start, end = capture.base._history_window(8)
    audit = {}
    successes = []
    for symbol in anchors:
        attempts = []
        route = None
        try:
            with runtime_guard._deadline(_symbol_budget(runtime_guard)):
                route = capture._capture_unified(
                    symbol, 8, attempts, "VNSTOCK_PREFLIGHT_UNIFIED"
                )
                if route is None:
                    route = capture._capture_provider(
                        symbol, "VCI", start, end, attempts, "VNSTOCK_PREFLIGHT_VCI"
                    )
                if route is None:
                    route = capture._capture_provider(
                        symbol, "KBS", start, end, attempts, "VNSTOCK_PREFLIGHT_KBS"
                    )
        except BaseException as exc:
            attempts.append({
                "stage": "VNSTOCK_PREFLIGHT_SYMBOL_BUDGET",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:700],
            })
        ok = route is not None and bool(route[0])
        if ok:
            rows, source_audit = route
            successes.append({
                "symbol": symbol,
                "end": str(rows[-1].get("date", ""))[:10],
                "rows": len(rows),
                "providerCode": source_audit.get("providerCode"),
            })
        audit[symbol] = {"ok": ok, "attempts": attempts}
    required = min(2, len(anchors))
    if anchors and len(successes) < required:
        raise RuntimeError(
            f"VNStock preflight failed: {len(successes)}/{len(anchors)} anchors reachable"
        )
    cutoff = None
    if successes:
        counts = Counter(x["end"] for x in successes if x["end"])
        cutoff = max(counts, key=lambda d: (counts[d], d)) if counts else None
    return {
        "status": "PASS",
        "anchors": audit,
        "successes": successes,
        "required": required,
        "targetAsOfHint": cutoff,
    }


def create_plan(shard_count=DEFAULT_SHARDS, out=PLAN_PATH):
    capture, _, universe, runtime_guard, source_audit, runtime_audit = _install_capture_stack()
    current = sorted(universe.current_hose_symbols())
    historical, discovery = universe.discover_candidates()
    discovery_error = (
        (discovery.get("vnstockReference") or {}).get("error")
        if isinstance(discovery, dict)
        else "invalid universe discovery payload"
    )
    if discovery_error:
        raise RuntimeError(f"historical_universe_discovery:{discovery_error}")
    historical = {s: m for s, m in sorted(historical.items()) if s not in set(current)}
    hist_symbols = sorted(historical)
    requested = sorted(set(current) | set(hist_symbols))
    preflight = _preflight(capture, runtime_guard, current)
    if not preflight.get("targetAsOfHint"):
        raise RuntimeError("VNStock preflight produced no target as-of cutoff")

    identity = _runtime_identity()
    assignments = _assignment(current, hist_symbols, shard_count)
    material = {
        "policyVersion": POLICY_VERSION,
        "runtimeScriptsTreeSha": identity["runtimeScriptsTreeSha"],
        "workflowSha256": identity["workflowSha256"],
        "runtimePolicy": identity["runtimePolicy"],
        "targetAsOfHint": preflight["targetAsOfHint"],
        "shardCount": shard_count,
        "currentHOSESymbols": current,
        "historicalCandidates": historical,
        "assignments": assignments,
    }
    plan = {
        "version": PLAN_VERSION,
        "generatedAt": _utcnow(),
        "policyVersion": POLICY_VERSION,
        **identity,
        "targetAsOfHint": preflight["targetAsOfHint"],
        "preflight": preflight,
        "sourceAudit": source_audit,
        "runtimeAudit": runtime_audit,
        "currentHOSESymbols": current,
        "historicalCandidates": historical,
        "universeDiscovery": discovery,
        "requestedSymbols": requested,
        "shardCount": shard_count,
        "assignments": assignments,
        "planFingerprint": _sha(material),
    }
    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "v12ShardedPlan": "PASS",
        "requested": len(requested),
        "currentHOSE": len(current),
        "historical": len(hist_symbols),
        "shards": shard_count,
        "targetAsOfHint": plan["targetAsOfHint"],
        "planFingerprint": plan["planFingerprint"],
    }, ensure_ascii=False), flush=True)
    return plan


def checkpoint_branch(shard):
    return f"v12-source-checkpoint-{int(shard):02d}"


def checkpoint_path(shard):
    return CHECKPOINT_ROOT / f"shard-{int(shard):02d}.json.gz"


def checkpoint_manifest_path(shard):
    return CHECKPOINT_ROOT / f"shard-{int(shard):02d}-manifest.json"


def _load_checkpoint_bytes_from_git(shard):
    branch = checkpoint_branch(shard)
    path = str(checkpoint_path(shard))
    probe = _git("ls-remote", "--exit-code", "--heads", "origin", branch, check=False)
    if probe.returncode != 0:
        return None
    fetch = _git("fetch", "-q", "origin", branch, check=False)
    if fetch.returncode != 0:
        return None
    show = subprocess.run(
        ["git", "show", f"FETCH_HEAD:{path}"],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
    )
    return show.stdout if show.returncode == 0 and show.stdout else None


def _assignment_fingerprint(plan, shard):
    return _sha(plan["assignments"][str(int(shard))])


def validate_checkpoint(checkpoint, plan, shard):
    required = {
        "version": CHECKPOINT_VERSION,
        "policyVersion": POLICY_VERSION,
        "planFingerprint": plan["planFingerprint"],
        "runtimeScriptsTreeSha": plan["runtimeScriptsTreeSha"],
        "workflowSha256": plan["workflowSha256"],
        "targetAsOfHint": plan["targetAsOfHint"],
        "shard": int(shard),
        "shardCount": int(plan["shardCount"]),
        "assignmentFingerprint": _assignment_fingerprint(plan, shard),
    }
    for key, expected in required.items():
        if checkpoint.get(key) != expected:
            return False, f"{key}_mismatch"

    assigned = set(plan["assignments"][str(int(shard))])
    entries = checkpoint.get("entries") or {}
    if not set(entries).issubset(assigned):
        return False, "checkpoint_contains_symbol_outside_assignment"
    for symbol, item in entries.items():
        rows = item.get("rows") or []
        audit = item.get("audit") or {}
        if not rows:
            return False, f"{symbol}:empty_rows"
        if row_fingerprint(rows) != item.get("sha256"):
            return False, f"{symbol}:row_fingerprint_mismatch"
        runtime_policy = audit.get("runtimeSourcePolicy")
        if runtime_policy != "VNSTOCK_ONLY_NO_YAHOO_NO_GLOBAL_CIRCUIT":
            return False, f"{symbol}:runtime_source_policy_mismatch"
        adjustment = audit.get("adjustmentReference") or {}
        if adjustment.get("networkCall") is True:
            return False, f"{symbol}:yahoo_network_reference_forbidden"
    return True, "PASS"


def load_checkpoint(plan, shard):
    raw = _load_checkpoint_bytes_from_git(shard)
    if not raw:
        return None, "checkpoint_absent"
    try:
        checkpoint = json.loads(gzip.decompress(raw).decode("utf-8"))
    except BaseException as exc:
        return None, f"checkpoint_decode_error:{type(exc).__name__}:{exc}"
    ok, reason = validate_checkpoint(checkpoint, plan, shard)
    return (checkpoint if ok else None), reason


def _new_checkpoint(plan, shard):
    return {
        "version": CHECKPOINT_VERSION,
        "policyVersion": POLICY_VERSION,
        "createdAt": _utcnow(),
        "updatedAt": _utcnow(),
        "sourceTriggerSha": plan["sourceTriggerSha"],
        "planFingerprint": plan["planFingerprint"],
        "runtimeScriptsTreeSha": plan["runtimeScriptsTreeSha"],
        "workflowSha256": plan["workflowSha256"],
        "targetAsOfHint": plan["targetAsOfHint"],
        "shard": int(shard),
        "shardCount": int(plan["shardCount"]),
        "assignmentFingerprint": _assignment_fingerprint(plan, shard),
        "assignedSymbols": list(plan["assignments"][str(int(shard))]),
        "entries": {},
        "failures": {},
        "attemptedSymbols": [],
    }


def _failure_payload(symbol, exc):
    attempts = list(getattr(exc, "attempts", []) or [])
    return {
        "symbol": symbol,
        "error": f"{type(exc).__name__}: {exc}"[:900],
        "attempts": attempts,
        "updatedAt": _utcnow(),
    }


def _failure_transient(failure, resilience):
    if resilience._transient(failure.get("error")):
        return True
    for attempt in failure.get("attempts") or []:
        text = " ".join(str(attempt.get(k) or "") for k in ("error", "reason", "stage"))
        if resilience._transient(text):
            return True
    return False


def _checkpoint_bytes(checkpoint):
    raw = _canonical(checkpoint)
    return gzip.compress(raw, compresslevel=9, mtime=0)


class CheckpointPublisher:
    def __init__(self, plan, shard):
        self.plan = plan
        self.shard = int(shard)
        self.branch = checkpoint_branch(shard)
        base_tmp = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())
        self.worktree = base_tmp / f"v12-checkpoint-worktree-{self.shard:02d}"
        if self.worktree.exists():
            shutil.rmtree(self.worktree, ignore_errors=True)
        _git("worktree", "prune", check=False)
        _git("worktree", "add", "--detach", str(self.worktree), plan["sourceTriggerSha"])
        _git("config", "user.name", "github-actions[bot]", cwd=self.worktree)
        _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=self.worktree)

    def publish(self, checkpoint, last_symbol=None):
        checkpoint = dict(checkpoint)
        checkpoint["updatedAt"] = _utcnow()
        payload = _checkpoint_bytes(checkpoint)
        cp_path = self.worktree / pathlib.Path(str(checkpoint_path(self.shard)))
        mf_path = self.worktree / pathlib.Path(str(checkpoint_manifest_path(self.shard)))
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        cp_path.write_bytes(payload)
        assigned = checkpoint.get("assignedSymbols") or []
        entries = checkpoint.get("entries") or {}
        failures = checkpoint.get("failures") or {}
        pending = [s for s in assigned if s not in entries]
        manifest = {
            "version": CHECKPOINT_MANIFEST_VERSION,
            "policyVersion": POLICY_VERSION,
            "updatedAt": checkpoint["updatedAt"],
            "planFingerprint": checkpoint["planFingerprint"],
            "runtimeScriptsTreeSha": checkpoint["runtimeScriptsTreeSha"],
            "workflowSha256": checkpoint["workflowSha256"],
            "targetAsOfHint": checkpoint["targetAsOfHint"],
            "shard": self.shard,
            "shardCount": checkpoint["shardCount"],
            "assigned": len(assigned),
            "captured": len(entries),
            "failed": len(failures),
            "pending": len(pending),
            "lastSymbol": last_symbol,
            "checkpointFileSha256": _sha(payload),
            "recentFailures": {k: failures[k] for k in list(failures)[-8:]},
        }
        mf_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        _git("add", str(checkpoint_path(self.shard)), str(checkpoint_manifest_path(self.shard)), cwd=self.worktree)
        if _git("diff", "--cached", "--quiet", cwd=self.worktree, check=False).returncode == 0:
            return manifest
        _git("commit", "-m", f"Checkpoint V12 source shard {self.shard:02d}", cwd=self.worktree)
        _git("push", "--force", "origin", f"HEAD:refs/heads/{self.branch}", cwd=self.worktree)
        print(json.dumps({"v12ShardCheckpoint": manifest}, ensure_ascii=False), flush=True)
        return manifest


def capture_shard(plan_path, shard, checkpoint_every=DEFAULT_CHECKPOINT_EVERY):
    plan = json.loads(pathlib.Path(plan_path).read_text(encoding="utf-8"))
    shard = int(shard)
    if shard < 0 or shard >= int(plan["shardCount"]):
        raise ValueError(f"invalid shard {shard}")
    identity = _runtime_identity()
    if identity["runtimeScriptsTreeSha"] != plan["runtimeScriptsTreeSha"]:
        raise RuntimeError("runtime scripts tree changed after plan")
    if identity["workflowSha256"] != plan["workflowSha256"]:
        raise RuntimeError("workflow changed after plan")

    capture, resilience, _, runtime_guard, _, _ = _install_capture_stack()
    existing, reason = load_checkpoint(plan, shard)
    checkpoint = existing or _new_checkpoint(plan, shard)
    print(json.dumps({
        "v12ShardResume": {
            "shard": shard,
            "status": "REUSED" if existing else "NEW",
            "reason": reason,
            "captured": len(checkpoint.get("entries") or {}),
            "assigned": len(checkpoint.get("assignedSymbols") or []),
        }
    }, ensure_ascii=False), flush=True)

    publisher = CheckpointPublisher(plan, shard)
    publisher.publish(checkpoint, last_symbol=None)

    assigned = list(plan["assignments"][str(shard)])
    entries = checkpoint.setdefault("entries", {})
    failures = checkpoint.setdefault("failures", {})
    attempted = checkpoint.setdefault("attemptedSymbols", [])
    pending = [s for s in assigned if s not in entries]
    attempts_since_publish = 0

    def attempt_symbol(symbol, recovery_round=0):
        nonlocal attempts_since_publish
        started = time.monotonic()
        try:
            rows, audit = _capture_one(capture, runtime_guard, symbol)
            if not rows:
                raise RuntimeError(f"{symbol}: source capture returned empty rows")
            entries[symbol] = {
                "capturedAt": _utcnow(),
                "recoveryRound": recovery_round,
                "rows": rows,
                "audit": audit,
                "sha256": row_fingerprint(rows),
            }
            failures.pop(symbol, None)
            status = "CAPTURED"
        except BaseException as exc:
            failures[symbol] = _failure_payload(symbol, exc)
            status = "FAILED"
        if symbol not in attempted:
            attempted.append(symbol)
        attempts_since_publish += 1
        print(json.dumps({
            "v12ShardSymbol": {
                "shard": shard,
                "symbol": symbol,
                "status": status,
                "elapsedSeconds": round(time.monotonic() - started, 3),
                "captured": len(entries),
                "failed": len(failures),
                "assigned": len(assigned),
                "recoveryRound": recovery_round,
            }
        }, ensure_ascii=False), flush=True)
        if attempts_since_publish >= max(1, int(checkpoint_every)):
            publisher.publish(checkpoint, last_symbol=symbol)
            attempts_since_publish = 0

    for symbol in pending:
        attempt_symbol(symbol, recovery_round=0)

    retry = [
        s for s in assigned
        if s not in entries and _failure_transient(failures.get(s) or {}, resilience)
    ]
    if retry:
        print(json.dumps({"v12ShardTargetedFailureRetry": {"shard": shard, "symbols": retry}}, ensure_ascii=False), flush=True)
        for symbol in retry:
            attempt_symbol(symbol, recovery_round=1)

    manifest = publisher.publish(checkpoint, last_symbol=(attempted[-1] if attempted else None))
    print(json.dumps({
        "v12ShardCapture": "PASS" if manifest["pending"] == 0 else "COMPLETE_WITH_MISSING",
        "shard": shard,
        "captured": manifest["captured"],
        "failed": manifest["failed"],
        "pending": manifest["pending"],
    }, ensure_ascii=False), flush=True)
    return checkpoint


def _load_checkpoint_for_assembly(plan, shard):
    checkpoint, reason = load_checkpoint(plan, shard)
    if checkpoint is None:
        return None, reason, None
    raw = _load_checkpoint_bytes_from_git(shard)
    return checkpoint, "PASS", _sha(raw)


def merge_checkpoints(plan, checkpoints):
    store = {}
    audits = {}
    failures = {}
    provenance = {}
    for shard in range(int(plan["shardCount"])):
        checkpoint, reason, file_sha = checkpoints.get(shard, (None, "missing", None))
        assigned = list(plan["assignments"][str(shard)])
        provenance[str(shard)] = {
            "branch": checkpoint_branch(shard),
            "status": reason,
            "checkpointFileSha256": file_sha,
            "assigned": len(assigned),
            "captured": len((checkpoint or {}).get("entries") or {}),
        }
        if checkpoint is None:
            for symbol in assigned:
                failures[symbol] = {
                    "error": f"shard_checkpoint_unavailable:{reason}",
                    "attempts": [{"stage": "SHARD_CHECKPOINT_LOAD", "ok": False, "reason": reason}],
                }
            continue
        entries = checkpoint.get("entries") or {}
        cp_failures = checkpoint.get("failures") or {}
        for symbol in assigned:
            if symbol in entries:
                if symbol in store:
                    raise RuntimeError(f"duplicate symbol across shards: {symbol}")
                store[symbol] = entries[symbol]["rows"]
                audits[symbol] = entries[symbol]["audit"]
            else:
                failures[symbol] = cp_failures.get(symbol) or {
                    "error": "assigned_symbol_missing_from_checkpoint",
                    "attempts": [{"stage": "SHARD_CHECKPOINT_MISSING_SYMBOL", "ok": False}],
                }
    return store, audits, failures, provenance


def _write_assembly(payload):
    DATA.mkdir(parents=True, exist_ok=True)
    ASSEMBLY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def assemble(plan_path):
    plan = json.loads(pathlib.Path(plan_path).read_text(encoding="utf-8"))
    identity = _runtime_identity()
    if identity["runtimeScriptsTreeSha"] != plan["runtimeScriptsTreeSha"]:
        raise RuntimeError("runtime scripts tree changed after plan")
    if identity["workflowSha256"] != plan["workflowSha256"]:
        raise RuntimeError("workflow changed after plan")

    loaded = {}
    for shard in range(int(plan["shardCount"])):
        loaded[shard] = _load_checkpoint_for_assembly(plan, shard)
    store, audits, failures, provenance = merge_checkpoints(plan, loaded)
    actual_asof = _modal_end(store, plan["currentHOSESymbols"])
    assembly = {
        "version": ASSEMBLY_VERSION,
        "generatedAt": _utcnow(),
        "policyVersion": POLICY_VERSION,
        "sourceTriggerSha": plan["sourceTriggerSha"],
        "planFingerprint": plan["planFingerprint"],
        "runtimeScriptsTreeSha": plan["runtimeScriptsTreeSha"],
        "workflowSha256": plan["workflowSha256"],
        "targetAsOfHint": plan["targetAsOfHint"],
        "actualModalAsOf": actual_asof,
        "requested": len(plan["requestedSymbols"]),
        "captured": len(store),
        "failed": len(failures),
        "shards": provenance,
    }
    if not actual_asof:
        assembly["status"] = "FAIL_NO_CURRENT_MODAL_ASOF"
        _write_assembly(assembly)
        raise RuntimeError("sharded assembly has no current-HOSE modal as-of")
    if actual_asof != plan["targetAsOfHint"]:
        assembly["status"] = "FAIL_SOURCE_EPOCH_SHIFT"
        _write_assembly(assembly)
        raise RuntimeError(
            f"source epoch shifted during capture: plan={plan['targetAsOfHint']} actual={actual_asof}"
        )

    store = normalize_store_to_asof(store, actual_asof)
    assembly["normalizedCaptured"] = len(store)
    assembly["status"] = "ASSEMBLED_FOR_UNCHANGED_SOURCE_GATES"
    _write_assembly(assembly)

    import v12_universe as universe
    import v12_source_capture as capture

    discovery = dict(plan.get("universeDiscovery") or {})
    discovery["shardedCapture"] = {
        "version": ASSEMBLY_VERSION,
        "policyVersion": POLICY_VERSION,
        "planFingerprint": plan["planFingerprint"],
        "runtimeScriptsTreeSha": plan["runtimeScriptsTreeSha"],
        "workflowSha256": plan["workflowSha256"],
        "targetAsOfHint": plan["targetAsOfHint"],
        "checkpointShards": provenance,
        "successfulSymbolsReusedWithoutRefetch": True,
        "retryScope": "MISSING_OR_FAILED_SYMBOLS_ONLY",
        "finalGateImplementation": "freeze_v12_source_snapshot.py_UNCHANGED_GATES",
    }
    current_symbols = list(plan["currentHOSESymbols"])
    historical = dict(plan.get("historicalCandidates") or {})
    universe.current_hose_symbols = lambda: set(current_symbols)
    universe.discover_candidates = lambda: (historical, discovery)
    capture.build_source_capture_store = lambda _symbols: (store, audits, failures)

    try:
        runpy.run_path(str(ROOT / "scripts" / "freeze_v12_source_snapshot.py"), run_name="__main__")
        from freeze_v12_source_snapshot_resilient import _postvalidate_original_deep_ca_cohort
        _postvalidate_original_deep_ca_cohort()
    except BaseException as exc:
        assembly["status"] = "FAIL_FINAL_SOURCE_GATES"
        assembly["error"] = f"{type(exc).__name__}: {exc}"[:1200]
        _write_assembly(assembly)
        raise

    assembly["status"] = "PASS"
    _write_assembly(assembly)
    print(json.dumps({
        "v12ShardedAssembly": "PASS",
        "captured": len(store),
        "failures": len(failures),
        "asOf": actual_asof,
        "planFingerprint": plan["planFingerprint"],
    }, ensure_ascii=False), flush=True)
    return assembly


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--shards", type=int, default=DEFAULT_SHARDS)
    p_plan.add_argument("--out", default=str(PLAN_PATH))
    p_cap = sub.add_parser("capture-shard")
    p_cap.add_argument("--plan", required=True)
    p_cap.add_argument("--shard", type=int, required=True)
    p_cap.add_argument("--checkpoint-every", type=int, default=DEFAULT_CHECKPOINT_EVERY)
    p_asm = sub.add_parser("assemble")
    p_asm.add_argument("--plan", required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        create_plan(args.shards, args.out)
    elif args.command == "capture-shard":
        capture_shard(args.plan, args.shard, args.checkpoint_every)
    elif args.command == "assemble":
        assemble(args.plan)


if __name__ == "__main__":
    main()
