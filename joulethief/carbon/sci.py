"""Software Carbon Intensity (ISO/IEC 21031:2024): SCI = ((E × I) + M) per R."""

from __future__ import annotations

from dataclasses import dataclass

from ..estimate import Estimate


@dataclass(frozen=True)
class SCIResult:
    operational_g: Estimate
    embodied_g: Estimate
    functional_units: float
    functional_unit: str

    @property
    def total_g(self) -> Estimate:
        return self.operational_g + self.embodied_g

    @property
    def per_unit_g(self) -> Estimate:
        return self.total_g / self.functional_units

    def to_dict(self) -> dict:
        return {
            "operational_g": self.operational_g.to_dict(),
            "embodied_g": self.embodied_g.to_dict(),
            "total_g": self.total_g.to_dict(),
            "functional_unit": self.functional_unit,
            "functional_units": self.functional_units,
            "sci_g_per_unit": self.per_unit_g.to_dict(),
        }


def sci(energy_kwh: Estimate, intensity_g_per_kwh: Estimate | float, embodied_g: Estimate | float,
        functional_units: float, functional_unit: str) -> SCIResult:
    if functional_units <= 0:
        raise ValueError("functional_units must be positive")
    intensity = intensity_g_per_kwh if isinstance(intensity_g_per_kwh, Estimate) else Estimate.exact(intensity_g_per_kwh)
    emb = embodied_g if isinstance(embodied_g, Estimate) else Estimate.exact(embodied_g)
    return SCIResult(energy_kwh * intensity, emb, functional_units, functional_unit)
