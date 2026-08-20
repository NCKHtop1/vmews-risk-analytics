"""
Promotion gate for V12.1 Absolute Challenger.

Never promote because forecast magnitude looks larger.
Only promote when blind OOS evidence wins.
"""


def promotion_check(summary):
    required = [
        summary.get('mae_improved') is True,
        summary.get('blind_holdout_pass') is True,
        summary.get('calibration_pass') is True,
        summary.get('regime_stability_pass') is True,
        summary.get('rank_ic_not_worse') is True,
    ]
    return all(required)


if __name__ == '__main__':
    raise SystemExit('Use promotion_check() with frozen OOS evaluation summary')
