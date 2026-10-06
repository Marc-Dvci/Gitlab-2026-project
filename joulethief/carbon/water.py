"""Water: the other footprint of compute (SCI for AI includes it).

    water = E_IT × WUE_onsite(T)  +  E_IT × PUE × EWIF(grid)

Onsite WUE depends on cooling technology and outside temperature: evaporative towers
use more water on hot afternoons — exactly when solar makes the grid cleanest. That is
why Joule Thief optimises carbon and water together instead of carbon alone.
Defaults use the provider WUE ranges in EcoLogits (0.13–0.999 L/kWh); the temperature
curve is an illustrative model to be calibrated against provider disclosures.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..estimate import Estimate


@dataclass(frozen=True)
class CoolingProfile:
    name: str
    wue_annual: Estimate  # L/kWh at the site's annual mean temperature
    temperature_sensitivity: float  # relative change in WUE per °C above the annual mean
    annual_mean_c: float = 12.0
    floor_fraction: float = 0.15  # free-cooling floor as a fraction of the annual WUE

    def wue_at(self, temp_c: float) -> Estimate:
        factor = max(self.floor_fraction, 1.0 + self.temperature_sensitivity * (temp_c - self.annual_mean_c))
        return self.wue_annual * factor


EVAPORATIVE = CoolingProfile("evaporative", Estimate.from_range(0.13, 0.999), temperature_sensitivity=0.06)
# Hamina (europe-north1) is cooled with Baltic seawater: freshwater consumption on site is ~0.
SEAWATER = CoolingProfile("seawater", Estimate(0.0, 0.01, 0.05), temperature_sensitivity=0.0)
AIR = CoolingProfile("air", Estimate(0.0, 0.05, 0.2), temperature_sensitivity=0.02)
PROFILES = {p.name: p for p in (EVAPORATIVE, SEAWATER, AIR)}


def water_litres(it_energy_kwh: Estimate, cooling: CoolingProfile, temp_c: float, pue: Estimate,
                 ewif_l_per_kwh: float) -> Estimate:
    onsite = it_energy_kwh * cooling.wue_at(temp_c)
    offsite = it_energy_kwh * pue * ewif_l_per_kwh
    return onsite + offsite


def grid_ewif(zone_iso3: str) -> float:
    """Electricity water intensity factor (L/kWh) from EcoLogits' electricity mixes."""
    import json
    import os

    import ecologits  # optional dependency

    path = os.path.join(os.path.dirname(ecologits.__file__), "data", "electricity_mixes.json")
    with open(path) as fh:
        for mix in json.load(fh)["electricity_mixes"]:
            if mix["name"] == zone_iso3:
                return float(mix["wue"])
    raise KeyError(zone_iso3)
