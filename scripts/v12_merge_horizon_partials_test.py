from __future__ import annotations

import json
import pathlib
import tempfile

from v12_merge_horizon_partials import merge_partials


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def build(root, corrupt=False):
    for h in range(1, 6):
        d = root / f"h{h}"
        common_model = {
            "version": "VMEWS-FORECAST-12.0.0",
            "createdAt": f"2026-08-18T00:00:0{h}Z",
            "target": "direct",
            "featureNames": ["a", "b"],
            "experts": {"NUMERICAL": ["a"]},
            "universe": {"rows": 1000, "dates": 100, "start": "2020-01-01", "end": "2026-08-18"},
            "governance": {"priceSourcePolicy": "legacy", "stacking": "OOF"},
            "dataSources": {"flowVersion": "x", "eventVersion": "y"},
            "horizons": {
                str(h): {
                    "priceStatus": "PASS",
                    "directionStatus": "PASS" if h != 4 else "REVIEW",
                    "sealedAudit": {"rankIC": 0.03},
                }
            },
            "promotion": {"status": "REVIEW", "directPriceHorizons": [h]},
        }
        current = {
            "version": "VMEWS-CURRENT-12.0.0",
            "generatedAt": f"2026-08-18T00:00:0{h}Z",
            "symbols": {
                "FPT": {
                    "symbol": "FPT",
                    "date": "2026-08-18",
                    "close": 100.0,
                    "modelClose": 100.0,
                    "technical": 40.0,
                    "market": {"mret1": 0.1},
                    "riskStatus": "GREEN",
                    "riskFlags": 0,
                    "evidence": {"n": 1},
                    "flow": {"foreignAvailable": 1.0},
                    "horizons": {str(h): {"expectedReturn": 0.01 * h, "expectedPrice": 100.0 + h}},
                }
            },
        }
        dashboard = {
            "version": "VMEWS-DASHBOARD-12.4.0",
            "generatedAt": f"2026-08-18T00:00:0{h}Z",
            "modelVersion": "VMEWS-FORECAST-12.0.0",
            "asOf": "2026-08-18",
            "promotion": common_model["promotion"],
            "symbols": current["symbols"],
            "charts": {"FPT": [{"date": "2026-08-18", "close": 100.0}]},
            "lists": {"watch": [{"symbol": "FPT"}] if h == 5 else [], "yellow": [], "red": []},
            "dataAuditSummary": {"currentSymbolsPassed": 1},
        }
        backtest = {
            "version": "VMEWS-BACKTEST-12.4.0",
            "generatedAt": f"2026-08-18T00:00:0{h}Z",
            "design": "same-design",
            "horizons": {str(h): {"priceStatus": "PASS"}},
            "cases": {str(h): [{"symbol": "FPT", "predictedReturn": 0.01 * h}]},
        }
        data_audit = {"version": "AUDIT", "generatedAt": f"2026-08-18T00:00:0{h}Z", "routes": {"FROZEN": 1}}
        event_db = {"version": "EVENT", "generatedAt": f"2026-08-18T00:00:0{h}Z", "summary": {"records": 2}}
        if corrupt and h == 3:
            data_audit["routes"] = {"FROZEN": 2}
        dump(d / "forecast-model-v12.json", common_model)
        dump(d / "forecast-current-v12.json", current)
        dump(d / "forecast-dashboard-v12.json", dashboard)
        dump(d / "forecast-backtest-v12.json", backtest)
        dump(d / "data-audit-v12.json", data_audit)
        dump(d / "event-intelligence-v12.json", event_db)


def main():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        partials = root / "partials"
        out = root / "out"
        build(partials)
        assembly = merge_partials(partials, out)
        assert assembly["status"] == "PASS", assembly
        assert assembly["promotion"] == "PASS", assembly
        model = json.loads((out / "forecast-model-v12.json").read_text(encoding="utf-8"))
        current = json.loads((out / "forecast-current-v12.json").read_text(encoding="utf-8"))
        assert sorted(model["horizons"]) == ["1", "2", "3", "4", "5"], model
        assert model["promotion"]["directPriceHorizons"] == [1, 2, 3, 4, 5], model["promotion"]
        assert model["promotion"]["directionHorizons"] == [1, 2, 3, 5], model["promotion"]
        assert "runtime network price fetch" in model["governance"]["priceSourcePolicy"], model["governance"]
        assert sorted(current["symbols"]["FPT"]["horizons"]) == ["1", "2", "3", "4", "5"]

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        partials = root / "partials"
        out = root / "out"
        build(partials, corrupt=True)
        try:
            merge_partials(partials, out)
        except RuntimeError as exc:
            assert "data-audit" in str(exc), exc
        else:
            raise AssertionError("cross-horizon invariant corruption was not rejected")

    print("V12 HORIZON PARTIAL MERGE TEST PASS")


if __name__ == "__main__":
    main()
