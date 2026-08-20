"""
V12.1 Conditional Magnitude Calibration

Prevents the failure mode where all forecasts collapse around T0.
Magnitude is conditioned by risk state instead of arbitrary scaling.
"""


def calibrate_magnitude(volatility: float,
                        regime_score: float,
                        confidence: float,
                        liquidity: float) -> float:
    vol_component = 1.0 / max(volatility, 0.5)
    regime_component = 1.0 + 0.25 * regime_score
    confidence_component = 0.8 + 0.4 * confidence
    liquidity_component = 0.8 + 0.2 * liquidity

    multiplier = (
        vol_component
        * regime_component
        * confidence_component
        * liquidity_component
    )

    # Prevent artificial amplification or collapse.
    return max(0.5, min(1.5, multiplier))


def apply_absolute_forecast(raw_return: float, magnitude: float) -> float:
    return raw_return * magnitude
