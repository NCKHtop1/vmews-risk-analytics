"""Regression tests for leakage-safe V34 challenger diagnostics."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.forecast_v34_challenger_audit import (
    CorrectionParameters,
    causal_momentum_correction,
    causal_residual_correction,
)


class CausalChallengerTest(unittest.TestCase):
    @staticmethod
    def rows() -> pd.DataFrame:
        dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"])
        return pd.DataFrame(
            {
                "date": dates,
                "symbol": ["FPT"] * 4,
                "forward_vol": [.10] * 4,
                "market_ret5": [.02] * 4,
                "relative_ret5": [.01] * 4,
                "target1": [.08, .06, -.02, .04],
                "maturity1": dates + pd.to_timedelta(1, unit="D"),
            }
        )

    def test_residual_is_unavailable_until_strictly_after_maturity(self) -> None:
        correction, audit = causal_residual_correction(
            self.rows(),
            np.zeros(4),
            1,
            CorrectionParameters(half_life=5, market_weight=1.0, symbol_weight=0.0),
        )
        self.assertEqual(correction[0], 0.0)
        self.assertEqual(correction[1], 0.0)
        self.assertGreater(correction[2], 0.0)
        self.assertTrue(audit["strictMaturityBeforeOrigin"])

    def test_future_outcome_cannot_change_earlier_dynamic_predictions(self) -> None:
        original = self.rows()
        altered = original.copy()
        altered.loc[3, "target1"] = -9.0
        first, _ = causal_momentum_correction(
            original,
            np.zeros(4),
            1,
            half_life=5,
            shrinkage=.5,
            relative_weight=.5,
        )
        second, _ = causal_momentum_correction(
            altered,
            np.zeros(4),
            1,
            half_life=5,
            shrinkage=.5,
            relative_weight=.5,
        )
        np.testing.assert_allclose(first, second)


if __name__ == "__main__":
    unittest.main()
