"""Energy gate for merge requests: deterministic first, LLM last.

Every MR pipeline measures joules per request (``scripts/energy_benchmark.py``). This module
compares the MR's benchmark with the target branch's and decides whether an LLM reviewer is
worth waking up: only when energy per request regresses beyond a tolerance, or when the MR
edits one of the service's hottest lines. Everything else is a table, not a conversation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .attribution import mr_delta_g_per_day

DEFAULT_TRAFFIC = {"/api/compare": 2000.0, "/api/grid": 20000.0}  # requests/day, as in the benchmark
DEFAULT_INTENSITY = 40.0  # gCO2/kWh, europe-north1 location-based


@dataclass(frozen=True)
class EnergyDelta:
    endpoint: str
    base_j: float | None  # None: the endpoint is new in this MR
    head_j: float
    g_per_day: float  # projected production impact of the change

    @property
    def change(self) -> float | None:
        if not self.base_j:
            return None
        return self.head_j / self.base_j - 1


@dataclass
class GateResult:
    deltas: list[EnergyDelta]
    hot_lines: list[dict]  # top carbon-blame lines that live in files this MR changes
    reasons: list[str]  # why an LLM reviewer is needed; empty means it is not

    @property
    def needs_reviewer(self) -> bool:
        return bool(self.reasons)


def compare(base: dict | None, head: dict, changed_files: list[str], tolerance: float = 0.2, top: int = 5) -> GateResult:
    traffic = head.get("traffic") or DEFAULT_TRAFFIC
    intensity = head.get("intensity_g_per_kwh") or DEFAULT_INTENSITY
    base_eps = (base or {}).get("endpoints", {})
    deltas = []
    for ep, v in sorted(head.get("endpoints", {}).items()):
        b = base_eps.get(ep, {}).get("joules_per_request")
        h = v["joules_per_request"]
        deltas.append(EnergyDelta(ep, b, h, mr_delta_g_per_day(b or 0.0, h, traffic.get(ep, 0.0), intensity)))
    changed = set(changed_files)
    hot = [line for line in head.get("lines", [])[:top] if line.get("file") in changed]
    reasons = [f"{d.endpoint}: {d.change:+.0%} J/request" for d in deltas
               if d.change is not None and d.change > tolerance]
    reasons += [f"edits hot line {h['file']}:{h['line']} ({h['g_per_day']:.3f} g/day)" for h in hot]
    return GateResult(deltas, hot, reasons)
