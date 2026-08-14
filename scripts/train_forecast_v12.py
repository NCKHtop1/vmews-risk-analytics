import json
import pathlib
import traceback
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
parts = []
for p in sorted((ROOT / "v12_train_parts").glob("*.pyinc")):
    parts.append(p.read_text(encoding="utf-8"))
code = "\n".join(parts)

try:
    exec(compile(code, str(ROOT / "v12_train_parts" / "assembled.py"), "exec"), globals(), globals())
except BaseException as exc:
    DATA.mkdir(parents=True, exist_ok=True)
    evidence = {
        "version": "VMEWS-V12-TRAINING-ERROR-1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "exceptionType": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
    (DATA / "v12-training-error.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps({"v12TrainingError": evidence}, ensure_ascii=False), flush=True)
    raise
