"""Explain the sealed price gate without changing its promotion decision."""
from __future__ import annotations

import math


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def describe_horizon_price_gate(horizon, audit, walk_forward, passed):
    """Preserve the sealed gate while making every failing condition observable."""
    folds=audit.get("chronologicalFolds") or []
    wf_folds=walk_forward.get("folds") or []
    paired=audit.get("pairedNoChangeAudit") or {}
    checks={
        "maeSkill>=0.005": float(audit.get("maeSkill") or 0)>=.005,
        "rankIC>=0.05": float(audit.get("rankIC") or 0)>=.05,
        "coverage20_80[0.52,0.72]": .52<=float(audit.get("coverage20_80") or 0)<=.72,
        "executableMedianAbs>=0.0015": float(audit.get("executableMedianAbs") or 0)>=.0015,
        "executableMAESkill>=0.003": float(audit.get("executableMAESkill") or 0)>=.003,
        "chronologicalMAEPositive>=3": sum(float(fold.get("maeSkill") or 0)>0 for fold in folds)>=3,
        "chronologicalExecutableMAEPositive>=3": sum(float(fold.get("executableMAESkill") or 0)>0 for fold in folds)>=3,
        "magnitudeMAESkill>0": float(audit.get("magnitudeMAESkill") or 0)>0,
        "walkForwardExecutablePositive>=2": int(walk_forward.get("positiveExecutableMAEFolds") or 0)>=2,
        "walkForwardMagnitudePositive>=2": int(walk_forward.get("positiveMagnitudeFolds") or 0)>=2,
        "walkForwardMeanExecutableMAE>0": float(walk_forward.get("meanExecutableMAESkill") or 0)>0,
        "walkForwardMeanRankIC>=0.05": float(walk_forward.get("meanRankIC") or 0)>=.05,
    }
    if audit.get("architecture")=="MARKET_RELATIVE":
        checks.update({
            "marketRegimeStatus=ACTIVE": audit.get("marketRegimeStatus")=="ACTIVE",
            "regimeArchitectureStatus=ACTIVE": audit.get("regimeArchitectureStatus")=="ACTIVE",
            "walkForwardFoldCount=3": len(wf_folds)==3,
            "allWalkForwardArchitecture=MARKET_RELATIVE": len(wf_folds)==3 and all(fold.get("architecture")=="MARKET_RELATIVE" for fold in wf_folds),
            "walkForwardPositiveMAEFolds=3": int(walk_forward.get("positiveMAEFolds") or 0)==3,
            "walkForwardPositiveExecutableMAEFolds=3": int(walk_forward.get("positiveExecutableMAEFolds") or 0)==3,
            "walkForwardMeanExecutableMAE>=0.005": float(walk_forward.get("meanExecutableMAESkill") or 0)>=.005,
            "latestWalkForwardExecutableMAE>0": bool(wf_folds) and float(wf_folds[-1].get("executableMAESkill") or 0)>0,
            "directionalAccuracy>=0.53": float(audit.get("directionalAccuracy") or 0)>=.53,
            "pairedImprovement>DailySE": float(paired.get("meanImprovement") or 0)>float(paired.get("dailyStandardError") or float("inf")),
            "pairedPositiveChronologicalBlocks>=3": int(paired.get("positiveChronologicalBlocks") or 0)>=3,
        })
    payload={
        "horizon":horizon,
        "passed":passed,
        "architecture":audit.get("architecture"),
        "failedChecks":[name for name,ok in checks.items() if not ok],
        "metrics":{
            "maeSkill":audit.get("maeSkill"),
            "rankIC":audit.get("rankIC"),
            "coverage20_80":audit.get("coverage20_80"),
            "executableMedianAbs":audit.get("executableMedianAbs"),
            "executableMAESkill":audit.get("executableMAESkill"),
            "magnitudeMAESkill":audit.get("magnitudeMAESkill"),
            "directionalAccuracy":audit.get("directionalAccuracy"),
            "marketRegimeStatus":audit.get("marketRegimeStatus"),
            "regimeArchitectureStatus":audit.get("regimeArchitectureStatus"),
            "pairedMeanImprovement":paired.get("meanImprovement"),
            "pairedDailyStandardError":paired.get("dailyStandardError"),
            "pairedPositiveChronologicalBlocks":paired.get("positiveChronologicalBlocks"),
            "walkForwardPositiveMAEFolds":walk_forward.get("positiveMAEFolds"),
            "walkForwardPositiveExecutableMAEFolds":walk_forward.get("positiveExecutableMAEFolds"),
            "walkForwardPositiveMagnitudeFolds":walk_forward.get("positiveMagnitudeFolds"),
            "walkForwardMeanExecutableMAESkill":walk_forward.get("meanExecutableMAESkill"),
            "walkForwardMeanRankIC":walk_forward.get("meanRankIC"),
            "latestWalkForwardExecutableMAESkill":(wf_folds[-1].get("executableMAESkill") if wf_folds else None),
        },
    }
    return _json_safe(payload)
