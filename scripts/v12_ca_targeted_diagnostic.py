import json
from datetime import datetime, timezone
from pathlib import Path

import v12_source_capture as capture

SYMBOLS = [
    "ABR","ADG","ADP","AFX","ANT","BCM","BSR","BVB","CTR","DSC","EVF","GEE","GHC","GVR","HHV","HNA","HTG","KLB","KOS","LPB","MCH","MCM","NAB","NHH","NHT","NTC","ORS","PDV","PGV","PVP","SIP","TAL","TCI","TDP","TSA","VAB","VBB","VCA","VIB","VTP","VVS"
]


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        if value != value:
            return None
    except Exception:
        pass
    return str(value)


def _vci_events(symbol):
    try:
        from vnstock.explorer.vci import Company
        c = Company(symbol=symbol, show_log=False)
        events = c._fetch_events(
            event_codes="DIV,ISS",
            from_date="20180701",
            to_date="20260817",
            page=0,
            size=500,
        )
        chart = c._fetch_news_events(
            from_date="20180701",
            to_date="20260817",
            event_codes="DIV,ISS",
        )
        return {
            "ok": True,
            "events": _jsonable(events),
            "chartEvents": _jsonable(chart),
        }
    except BaseException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:1200]}


def main():
    capture.reset_provider_circuits()
    result = {
        "version": "VMEWS-V12-CA-TARGETED-DIAGNOSTIC-1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "symbols": {},
    }
    for i, symbol in enumerate(SYMBOLS, 1):
        entry = {}
        try:
            rows, audit = capture.capture_price_history(symbol)
            entry["captured"] = True
            entry["rows"] = len(rows)
            entry["eligible"] = audit.get("eligible") is True
            entry["route"] = audit.get("route")
            entry["ineligibleReasons"] = audit.get("ineligibleReasons")
            entry["crossSourceReturnMAD"] = audit.get("crossSourceReturnMAD")
            entry["corporateAction"] = audit.get("corporateAction")
            entry["adjustmentReference"] = audit.get("adjustmentReference")
            entry["attempts"] = audit.get("attempts")
        except BaseException as exc:
            entry["captured"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"[:1200]
            entry["attempts"] = getattr(exc, "attempts", [])
        entry["vciCorporateEvents"] = _vci_events(symbol)
        result["symbols"][symbol] = _jsonable(entry)
        print(json.dumps({
            "targetedCADiagnostic": i,
            "total": len(SYMBOLS),
            "symbol": symbol,
            "eligible": entry.get("eligible"),
            "caVerified": ((entry.get("corporateAction") or {}).get("verified")),
            "vciEvents": len(((entry.get("vciCorporateEvents") or {}).get("events") or [])),
        }, ensure_ascii=False), flush=True)

    summary = {
        "requested": len(SYMBOLS),
        "captured": sum(bool(v.get("captured")) for v in result["symbols"].values()),
        "eligible": sum(v.get("eligible") is True for v in result["symbols"].values()),
        "caVerified": sum(((v.get("corporateAction") or {}).get("verified")) is True for v in result["symbols"].values()),
        "vciEventReferenceAvailable": sum((v.get("vciCorporateEvents") or {}).get("ok") is True for v in result["symbols"].values()),
    }
    result["summary"] = summary
    path = Path("data/v12-ca-targeted-diagnostic.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
