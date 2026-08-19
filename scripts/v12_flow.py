import bisect
import math
import statistics

FLOW_FEATURES = [
    "foreignNetRatio1",
    "foreignNetRatio5",
    "foreignNetRatio20",
    "foreignZ60",
    "foreignAccel5",
    "foreignAvailable",
    "propNetRatio1",
    "propNetRatio5",
    "propNetRatio20",
    "propZ60",
    "propAccel5",
    "propAvailable",
]


def _finite(x, default=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _empty_features(typ):
    return {
        f"{typ}NetRatio1": 0.0,
        f"{typ}NetRatio5": 0.0,
        f"{typ}NetRatio20": 0.0,
        f"{typ}Z60": 0.0,
        f"{typ}Accel5": 0.0,
        f"{typ}Available": 0.0,
    }


class FlowTimeline:
    """Point-in-time institutional-flow features with explicit source missingness.

    `flow-v12.json` stores the union of foreign and proprietary observation dates.
    A row can therefore contain only one source.  Missing keys from the other source
    must never be interpreted as a genuine zero-flow observation.
    """

    def __init__(self, rows):
        self.rows = sorted(rows or [], key=lambda x: str(x.get("date") or ""))
        self.by_type = {}
        self.type_dates = {}
        for typ in ("foreign", "prop"):
            source_keys = {
                typ + "NetValue",
                typ + "BuyValue",
                typ + "SellValue",
            }
            typed_rows = [
                r
                for r in self.rows
                if r.get("date") and any(k in r for k in source_keys)
            ]
            self.by_type[typ] = typed_rows
            self.type_dates[typ] = [str(r.get("date") or "")[:10] for r in typed_rows]

    def _features_for(self, typ, date):
        out = _empty_features(typ)
        dates = self.type_dates.get(typ) or []
        rows = self.by_type.get(typ) or []
        i = bisect.bisect_right(dates, date) - 1

        # Do not carry a stale observation forward and label it as available for T.
        # The forecast panel is EOD/session dated, so availability requires a genuine
        # source record on the requested session date.
        if i < 0 or dates[i] != date:
            return out

        min_obs = 40 if typ == "foreign" else 20
        window = rows[max(0, i - 119) : i + 1]
        if len(window) < min_obs:
            return out

        key = typ + "NetValue"
        buy = typ + "BuyValue"
        sell = typ + "SellValue"
        hist = [_finite(r.get(key), 0.0) for r in window]
        gross = [
            abs(_finite(r.get(buy), 0.0)) + abs(_finite(r.get(sell), 0.0))
            for r in window
        ]

        # Presence of a source row, not non-zero turnover, defines availability.
        # A genuine reported zero remains a valid zero observation.
        n1 = hist[-1]
        n5 = sum(hist[-5:])
        n20 = sum(hist[-20:])
        g1 = gross[-1]
        g5 = sum(gross[-5:])
        g20 = sum(gross[-20:])
        av = hist[-60:]
        mu = statistics.mean(av) if av else 0.0
        sd = statistics.stdev(av) if len(av) > 2 else 0.0
        prev5 = sum(hist[-10:-5])
        scale = g20 / max(1, min(20, len(gross))) if g20 > 0 else 1.0

        return {
            f"{typ}NetRatio1": n1 / g1 if g1 else 0.0,
            f"{typ}NetRatio5": n5 / g5 if g5 else 0.0,
            f"{typ}NetRatio20": n20 / g20 if g20 else 0.0,
            f"{typ}Z60": max(-8.0, min(8.0, (n1 - mu) / (sd or 1.0))),
            f"{typ}Accel5": max(
                -5.0,
                min(5.0, (n5 - prev5) / (5.0 * scale if scale else 1.0)),
            ),
            f"{typ}Available": 1.0,
        }

    def features(self, date):
        out = {}
        out.update(self._features_for("foreign", date))
        out.update(self._features_for("prop", date))
        return out


class FlowFeatureStore:
    def __init__(self, flow_json):
        self.source = str((flow_json or {}).get("source") or "unknown")
        self.timelines = {
            s: FlowTimeline(rows) for s, rows in (flow_json or {}).get("symbols", {}).items()
        }

    def features(self, symbol, date):
        tl = self.timelines.get(symbol)
        return tl.features(date) if tl else {k: 0.0 for k in FLOW_FEATURES}

    def coverage_summary(self, symbols, date):
        f = p = 0
        for s in symbols:
            z = self.features(s, date)
            f += z["foreignAvailable"] > 0
            p += z["propAvailable"] > 0
        n = max(1, len(symbols))
        return {
            "source": self.source,
            "symbols": len(symbols),
            "foreignAvailable": int(f),
            "foreignCoverage": f / n,
            "propAvailable": int(p),
            "propCoverage": p / n,
        }
