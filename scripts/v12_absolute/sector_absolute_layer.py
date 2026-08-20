"""
V12.1 Sector Absolute Return Layer

Adds sector context so stock forecasts are not independent from industry regime.
"""

from dataclasses import dataclass


@dataclass
class SectorForecast:
    sector: str
    horizon: int
    expected_return: float
    confidence: float


def build_sector_absolute_forecast(sector: str, sector_features: dict, horizon: int) -> SectorForecast:
    momentum = sector_features.get("momentum", 0.0)
    breadth = sector_features.get("breadth", 0.0)
    volume = sector_features.get("volume", 0.0)

    value = 0.5 * momentum + 0.3 * breadth + 0.2 * volume
    value = max(-0.08, min(0.08, value))

    return SectorForecast(
        sector=sector,
        horizon=horizon,
        expected_return=float(value),
        confidence=min(1.0, abs(value) * 8)
    )
