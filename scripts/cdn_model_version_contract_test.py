#!/usr/bin/env python3

import unittest

from cdn_model_version_contract import validate_versions


class CdnModelVersionContractTest(unittest.TestCase):
    def payloads(self, version: str):
        return (
            {"version": version},
            {"modelVersion": version},
            {"modelVersion": version},
        )

    def test_v41_passes(self):
        market, dashboard, current = self.payloads("VMEWS-MARKET-FORECAST-41.0.0")
        self.assertEqual(
            validate_versions(market=market, dashboard=dashboard, current=current),
            "VMEWS-MARKET-FORECAST-41.0.0",
        )

    def test_future_major_passes_without_workflow_rewrite(self):
        market, dashboard, current = self.payloads("VMEWS-MARKET-FORECAST-42.0.0")
        self.assertEqual(
            validate_versions(market=market, dashboard=dashboard, current=current),
            "VMEWS-MARKET-FORECAST-42.0.0",
        )

    def test_parity_mismatch_fails(self):
        market, dashboard, current = self.payloads("VMEWS-MARKET-FORECAST-41.0.0")
        dashboard["modelVersion"] = "VMEWS-MARKET-FORECAST-42.0.0"
        with self.assertRaises(AssertionError):
            validate_versions(market=market, dashboard=dashboard, current=current)

    def test_regression_below_v41_fails(self):
        market, dashboard, current = self.payloads("VMEWS-MARKET-FORECAST-39.0.0")
        with self.assertRaises(AssertionError):
            validate_versions(market=market, dashboard=dashboard, current=current)

    def test_malformed_version_fails(self):
        market, dashboard, current = self.payloads("V41")
        with self.assertRaises(AssertionError):
            validate_versions(market=market, dashboard=dashboard, current=current)


if __name__ == "__main__":
    unittest.main()
