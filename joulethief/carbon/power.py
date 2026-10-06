"""Cloud power and embodied-carbon model (Cloud Carbon Footprint coefficients, Apache-2.0).

Cloud VMs do not expose RAPL, so CPU power is estimated from utilisation:
    W = vCPUs × (Wmin + u × (Wmax − Wmin))  +  memory_GB × 0.392 W
then multiplied by the data-centre PUE. Embodied emissions are amortised over a
4-year server life and over the share of the host's vCPUs that the workload reserves.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..estimate import Estimate

REFERENCE = Path(__file__).resolve().parents[2] / "data" / "reference"
MEMORY_W_PER_GB = 0.392  # CCF
DEFAULT_PUE = Estimate(1.07, 1.09, 1.12)  # Google fleet-wide trailing PUE is ~1.09
SERVER_LIFESPAN_HOURS = 4 * 365 * 24
# vCPUs of the largest machine in each family, used as the "host" size for embodied amortisation.
HOST_VCPUS = {"e2": 32, "n1": 96, "n2": 128, "n2d": 224, "n4": 80, "c2": 60, "c2d": 112, "c3": 176, "c3d": 360,
              "c4": 192, "c4a": 72, "t2a": 48, "t2d": 60, "m1": 160, "a2": 96, "g2": 96}


@lru_cache(maxsize=1)
def cpu_coefficients() -> dict[str, tuple[float, float]]:
    with (REFERENCE / "ccf_coefficients_gcp_use.csv").open() as fh:
        return {row["Architecture"]: (float(row["Min Watts"]), float(row["Max Watts"])) for row in csv.DictReader(fh)}


@lru_cache(maxsize=1)
def embodied_coefficients() -> dict[str, float]:
    """Embodied kgCO2e of the host server per machine type (max over microarchitectures)."""
    out: dict[str, float] = {}
    with (REFERENCE / "ccf_coefficients_gcp_embodied.csv").open() as fh:
        for row in csv.DictReader(fh):
            out[row["type"]] = max(out.get(row["type"], 0.0), float(row["total"]))
    return out


@dataclass(frozen=True)
class CloudPowerModel:
    pue: Estimate = DEFAULT_PUE

    def watts_per_vcpu(self, utilisation: float) -> Estimate:
        """Range across microarchitectures for a given average utilisation (0–1)."""
        u = min(max(utilisation, 0.0), 1.0)
        per_arch = [lo + u * (hi - lo) for lo, hi in cpu_coefficients().values()]
        mean = sum(per_arch) / len(per_arch)
        return Estimate(min(per_arch), mean, max(per_arch))

    def energy_kwh(self, vcpus: float, hours: float, utilisation: float, memory_gb: float = 0.0) -> Estimate:
        it_watts = self.watts_per_vcpu(utilisation) * vcpus + MEMORY_W_PER_GB * memory_gb
        return it_watts * self.pue * hours / 1000.0

    def energy_from_cpu_seconds(self, cpu_seconds: float, memory_gb_hours: float = 0.0) -> Estimate:
        """Energy for *busy* CPU time (e.g. billed Cloud Run vCPU-seconds or per-request CPU time)."""
        busy = self.watts_per_vcpu(1.0) * (cpu_seconds / 3600.0) + MEMORY_W_PER_GB * memory_gb_hours
        return busy * self.pue / 1000.0

    @staticmethod
    def embodied_g(machine_type: str, vcpus: float, hours: float) -> float:
        family = machine_type.split("-")[0]
        host_total_kg = embodied_coefficients().get(machine_type) or max(
            v for k, v in embodied_coefficients().items() if k.startswith(family + "-"))
        host_vcpus = HOST_VCPUS.get(family, 64)
        share = min(vcpus / host_vcpus, 1.0)
        return host_total_kg * 1000.0 * share * hours / SERVER_LIFESPAN_HOURS
