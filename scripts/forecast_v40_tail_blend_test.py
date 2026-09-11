from __future__ import annotations

import numpy as np

from forecast_v40_tail_blend import select_tail_guarded_directional_blend


def synthetic_case(seed: int = 7):
    rng = np.random.default_rng(seed)
    sessions = 80
    per_session = 40
    n = sessions * per_session
    dates = np.repeat(np.arange(sessions), per_session)
    direction = rng.choice([-1.0, 1.0], size=n)
    conviction = rng.uniform(.04, .18, size=n)
    probability = .5 + direction * conviction
    ordinary = rng.normal(.006, .002, size=n)
    tail = rng.random(n) < .28
    actual_magnitude = np.where(tail, rng.normal(.030, .006, size=n), ordinary)
    actual_magnitude = np.clip(actual_magnitude, .001, None)
    actual = direction * actual_magnitude
    point = direction * np.where(tail, .006, .0055)
    magnitude = np.where(tail, .027, .0065)
    return actual, point, probability, magnitude, dates


def test_tail_recovery_can_activate():
    actual, point, probability, magnitude, dates = synthetic_case()
    out = select_tail_guarded_directional_blend(actual, point, probability, magnitude, dates)
    assert out["sealedLabelsUsed"] == 0
    assert out["candidateCount"] == 30
    assert out["status"] == "ACTIVE", out
    assert 0.0 < out["weight"] <= .50
    assert out["tailMeanPairedMAEImprovement"] > out["tailPairedStandardError"]
    assert out["positiveChronologicalBlocks"] >= 3
    assert out["tailPositiveChronologicalBlocks"] >= 3
    assert out["selectedMAE"] < out["baselineMAE"]


def test_wrong_direction_magnitude_abstains():
    actual, point, probability, magnitude, dates = synthetic_case()
    probability = 1.0 - probability
    out = select_tail_guarded_directional_blend(actual, point, probability, magnitude, dates)
    assert out["status"] == "ABSTAIN", out
    assert out["weight"] == 0.0
    assert out["sealedLabelsUsed"] == 0


def test_row_order_does_not_change_selection():
    actual, point, probability, magnitude, dates = synthetic_case()
    a = select_tail_guarded_directional_blend(actual, point, probability, magnitude, dates)
    order = np.random.default_rng(99).permutation(len(actual))
    b = select_tail_guarded_directional_blend(
        actual[order], point[order], probability[order], magnitude[order], dates[order]
    )
    for key in ("status", "weight", "probabilityMargin", "tailThreshold"):
        assert a[key] == b[key], (key, a[key], b[key])


def test_no_tail_help_means_abstain():
    actual, point, probability, magnitude, dates = synthetic_case()
    magnitude = np.abs(point)
    out = select_tail_guarded_directional_blend(actual, point, probability, magnitude, dates)
    assert out["status"] == "ABSTAIN", out
    assert out["weight"] == 0.0


if __name__ == "__main__":
    test_tail_recovery_can_activate()
    test_wrong_direction_magnitude_abstains()
    test_row_order_does_not_change_selection()
    test_no_tail_help_means_abstain()
    print("V40 tail blend tests PASS")
