import json
import os
import pathlib
import traceback
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent
DATA = REPO / "data"
EXPECTED = [
    "forecast-model-v12.json",
    "forecast-current-v12.json",
    "forecast-dashboard-v12.json",
    "forecast-backtest-v12.json",
    "data-audit-v12.json",
]
parts_paths = sorted((ROOT / "v12_train_parts").glob("*.pyinc"))
parts = [p.read_text(encoding="utf-8") for p in parts_paths]
code = "\n".join(parts)

def diagnostics(message, exc=None):
    DATA.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "VMEWS-V12-TRAINING-DIAGNOSTIC-1.1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "exceptionType": type(exc).__name__ if exc is not None else None,
        "traceback": traceback.format_exc() if exc is not None else None,
        "pythonName": __name__,
        "cwd": str(pathlib.Path.cwd()),
        "scriptRoot": str(ROOT),
        "repoRoot": str(REPO),
        "githubWorkspace": os.environ.get("GITHUB_WORKSPACE"),
        "parts": [p.name for p in parts_paths],
        "expectedOutputs": [str(DATA / x) for x in EXPECTED],
        "dataFiles": sorted(p.name for p in DATA.glob("*"))[:500],
    }
    (DATA / "v12-training-error.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps({"v12TrainingDiagnostic": payload}, ensure_ascii=False), flush=True)
    return payload

try:
    exec(compile(code, str(ROOT / "v12_train_parts" / "assembled.py"), "exec"), globals(), globals())
    missing = [name for name in EXPECTED if not (DATA / name).exists()]
    if missing:
        diagnostics(f"assembled training returned without materializing required outputs: {missing}")
        raise RuntimeError(f"V12 required outputs missing after training: {missing}")
    sizes = {name: (DATA / name).stat().st_size for name in EXPECTED}
    if any(size < 100 for size in sizes.values()):
        diagnostics(f"one or more V12 outputs are implausibly small: {sizes}")
        raise RuntimeError(f"V12 output size gate failed: {sizes}")
    print(json.dumps({"v12OutputMaterialization":"PASS","sizes":sizes}, ensure_ascii=False), flush=True)
except BaseException as exc:
    if not (DATA / "v12-training-error.json").exists():
        diagnostics(str(exc), exc)
    raise
