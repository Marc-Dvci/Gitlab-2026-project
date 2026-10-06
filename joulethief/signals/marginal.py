"""Decision signals: what does *one more kWh* emit, here and now?

Scheduling on the *average* intensity of a grid is the classic mistake of carbon-aware
computing: it can move load to hours where the average looks clean while a gas plant
still answers the extra demand, and it herds everyone into the same hours. Joule Thief
decides on a *marginal* signal and reports on both.

Priority of signals per zone:
    1. WattTime MOER, when a (free) account is configured.
    2. Day-ahead price heuristic (this module) for European bidding zones: when the price
       is at or below zero, inflexible renewable output exceeds demand and is being
       exported at a loss or curtailed — extra demand consumes energy that would have
       been thrown away. When the price is high, a thermal plant is on the margin.
    3. Average intensity (e.g. NESO for Great Britain), explicitly flagged as a proxy.

Lifecycle factors are IPCC AR5 WGIII Annex III medians (gCO2e/kWh).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .base import Point, Series

IPCC_AR5_LIFECYCLE_MEDIAN = {
    "coal": 820.0,
    "gas_ccgt": 490.0,
    "biomass_dedicated": 230.0,
    "solar_pv_utility": 48.0,
    "solar_pv_rooftop": 41.0,
    "geothermal": 38.0,
    "concentrated_solar": 27.0,
    "hydro": 24.0,
    "nuclear": 12.0,
    "wind_offshore": 12.0,
    "wind_onshore": 11.0,
}


@dataclass(frozen=True)
class PriceMarginalModel:
    """Map a day-ahead price (EUR/MWh) to an estimated marginal emission rate (gCO2e/kWh).

    This is a transparent heuristic, not a dispatch model. ``fossil_margin_g`` should be set
    from the zone's annual marginal intensity when known (the GSF Real Time Cloud dataset
    publishes WattTime-derived values per cloud region) and ``fossil_price`` from the zone's
    typical gas short-run marginal cost.
    """

    fossil_margin_g: float = IPCC_AR5_LIFECYCLE_MEDIAN["gas_ccgt"]
    surplus_g: float = IPCC_AR5_LIFECYCLE_MEDIAN["wind_onshore"]
    surplus_price: float = 0.0
    fossil_price: float = 40.0

    def g_per_kwh(self, price: float) -> float:
        if price <= self.surplus_price:
            return self.surplus_g
        if price >= self.fossil_price:
            return self.fossil_margin_g
        frac = (price - self.surplus_price) / (self.fossil_price - self.surplus_price)
        return self.surplus_g + frac * (self.fossil_margin_g - self.surplus_g)

    def series(self, prices: Series) -> Series:
        pts = [Point(p.start, self.g_per_kwh(p.value)) for p in prices]
        return Series(prices.zone, "carbon_intensity_marginal_estimate", "gCO2/kWh", prices.resolution, pts,
                      f"price heuristic over {prices.source}", kind=prices.kind,
                      notes={"model": "price-marginal-v1", "fossil_margin_g": self.fossil_margin_g,
                             "surplus_g": self.surplus_g, "fossil_price": self.fossil_price})


def surplus_windows(prices: Series, threshold: float = 0.0) -> list[tuple[datetime, datetime, float]]:
    """Contiguous windows where the price is at or below ``threshold``: (start, end, min price)."""
    windows: list[tuple[datetime, datetime, float]] = []
    current: list[Point] = []
    for p in prices:
        if p.value <= threshold and (not current or current[-1].start + prices.resolution == p.start):
            current.append(p)
            continue
        if current:
            windows.append((current[0].start, current[-1].start + prices.resolution, min(x.value for x in current)))
            current = []
        if p.value <= threshold:
            current = [p]
    if current:
        windows.append((current[0].start, current[-1].start + prices.resolution, min(x.value for x in current)))
    return windows


def intensity_from_mix(shares: dict[str, float], factors: dict[str, float]) -> float:
    """Weighted lifecycle intensity of a generation mix; ``shares`` need not sum to 1."""
    total = sum(v for v in shares.values() if v > 0)
    if total <= 0:
        raise ValueError("empty generation mix")
    missing = [k for k, v in shares.items() if v > 0 and k not in factors]
    if missing:
        raise KeyError(f"no emission factor for: {', '.join(sorted(missing))}")
    return sum(factors[k] * v for k, v in shares.items() if v > 0) / total


# Factors for NESO's fuel categories. "imports" and "other" are assumptions, documented as such.
NESO_FUEL_FACTORS = {
    "biomass": IPCC_AR5_LIFECYCLE_MEDIAN["biomass_dedicated"],
    "coal": IPCC_AR5_LIFECYCLE_MEDIAN["coal"],
    "gas": IPCC_AR5_LIFECYCLE_MEDIAN["gas_ccgt"],
    "hydro": IPCC_AR5_LIFECYCLE_MEDIAN["hydro"],
    "nuclear": IPCC_AR5_LIFECYCLE_MEDIAN["nuclear"],
    "solar": IPCC_AR5_LIFECYCLE_MEDIAN["solar_pv_utility"],
    "wind": IPCC_AR5_LIFECYCLE_MEDIAN["wind_onshore"],
    "imports": 250.0,  # assumption: blend of FR/NO/NL/BE interconnector sources
    "other": 300.0,  # assumption
}
