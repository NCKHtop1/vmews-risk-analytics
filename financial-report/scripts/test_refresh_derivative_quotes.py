import unittest
from datetime import date, datetime, timezone
from refresh_derivative_quotes import (
    BASE, collect, defaults, krx_code, normalize_board, parse_contract,
    parse_trade_time, retain_series, source_catalog, third_thursday,
)

STAMP = datetime(2026, 10, 23, 3, 17, tzinfo=timezone.utc)
VN30 = "41I1GB000"
VN100 = "41I2GB000"


def provider(url, payload=None):
    if url == BASE + "/index/DER/stocks":
        return {"data": [VN30, VN100, "AAA", "41I1GA000"]}
    if url == BASE + "/derivative/iss":
        assert payload and VN30 in payload["code"] and VN100 in payload["code"]
        return {"data": [
            {"SB": VN30, "CP": 1842.5, "RE": 1838, "TT": 34000,
             "OI": 35000, "HI": 1858, "LO": 1826, "OP": 1838, "B1": 1842.4,
             "S1": 1842.6, "V1": 20, "U1": 16},
            {"SB": VN100, "CP": 1878.7, "RE": 1874.4, "TT": 1230,
             "OI": 220, "HI": 1900, "LO": 1870},
        ]}
    if "/trade/history/" in url:
        code = url.split("/trade/history/")[1].split("?")[0]
        if code not in (VN30, VN100): raise ValueError("not a traded future")
        return {"data": [{"SB": code, "TD": "23/10/2026", "FT": "10:15:07",
                          "FMP": 1842.5, "FV": 10}]}
    raise AssertionError(url)


class DerivativeFeedTests(unittest.TestCase):
    def test_rollover_excludes_expired_october_contract(self):
        self.assertEqual(third_thursday(2026, 10), date(2026, 10, 15))
        self.assertIsNone(parse_contract("41I1GA000", date(2026, 10, 23)))
        self.assertEqual(parse_contract(VN30, date(2026, 10, 23))["symbol"], "VN30F2611")
        self.assertEqual(parse_contract(VN100, date(2026, 10, 23))["underlying"], "VN100")
        self.assertEqual(krx_code("VN30", 2026, 11), VN30)
        self.assertIn(VN30, defaults(date(2026, 10, 23)))

    def test_contract_source_catalog_is_scoped_to_derivatives(self):
        catalog = source_catalog(provider, date(2026, 10, 23))
        self.assertIn(VN30, catalog)
        self.assertIn(VN100, catalog)
        self.assertNotIn("AAA", catalog)
        self.assertNotIn("41I1GA000", catalog)

    def test_actual_trade_time_is_per_contract_and_timezone_aware(self):
        stamp = parse_trade_time({"TD": "23/10/2026", "FT": "10:15:07"}, STAMP)
        self.assertEqual(stamp, "2026-10-23T03:15:07+00:00")
        self.assertIsNone(parse_trade_time({"TD": "23/10/2026", "FT": "14:45:00"}, STAMP))
        self.assertIsNone(parse_trade_time({}, STAMP))

    def test_vn30_vn100_prices_volume_and_oi_from_actual_board(self):
        snapshot = collect(provider, STAMP)
        self.assertEqual(snapshot["schemaVersion"], 1)
        self.assertEqual(snapshot["type"], "FUTURES_ONLY")
        self.assertEqual(snapshot["intervalTargetSeconds"], 300)
        self.assertEqual(len(snapshot["contracts"]), 2)
        a = snapshot["contracts"][0]
        self.assertEqual(a["symbol"], "VN30F2611")
        self.assertEqual(a["price"], 1842.5)
        self.assertEqual(a["volume"], 34000)
        self.assertEqual(a["openInterest"], 35000)
        self.assertEqual(a["unit"], "points")
        self.assertEqual(a["sourceTime"], "2026-10-23T03:15:07+00:00")

    def test_missing_trade_timestamp_never_borrows_another_contract_clock(self):
        def one_stale(url, payload=None):
            if url.startswith(BASE + "/trade/history/" + VN100): return {"data": []}
            return provider(url, payload)
        snapshot = collect(one_stale, STAMP)
        self.assertEqual([x["symbol"] for x in snapshot["contracts"]], ["VN30F2611"])

    def test_price_with_bad_reference_or_old_trade_is_dropped(self):
        catalog = {VN30: parse_contract(VN30, date(2026, 10, 23))}
        board = {"data": [{"SB": VN30, "CP": 1842.5, "RE": 0, "TT": 100}]}
        self.assertEqual(normalize_board(board, catalog, {VN30: "2026-10-23T03:15:07+00:00"}, STAMP), {})
        self.assertIsNone(parse_trade_time({"TD": "01/01/2026", "FT": "10:15:07"}, STAMP))

    def test_series_append_source_stamps_not_fake_minutes(self):
        recent = {"schemaVersion": 1, "contracts": [
            {"symbol": "VN30F2611", "series": [{"time": "2026-10-23T03:10:07+00:00", "price": 1840}]}
        ]}
        snapshot = collect(provider, STAMP)
        retain_series(snapshot, recent)
        a = snapshot["contracts"][0]
        self.assertEqual(len(a["series"]), 2)
        self.assertEqual(a["series"][-1], {"time": a["sourceTime"], "price": a["price"]})
        retain_series(snapshot, {"contracts": snapshot["contracts"]})
        self.assertEqual(len(snapshot["contracts"][0]["series"]), 2)

if __name__ == "__main__":
    unittest.main()
