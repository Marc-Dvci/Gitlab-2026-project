"""SCI for AI: the footprint of the agents themselves.

Agentic sessions are dominated by *input* tokens (every loop iteration re-sends the
growing context). LLM providers do not publish energy per request, so energy, carbon
and water are estimated with EcoLogits (bottom-up model, published methodology) and
always reported as ranges. Input and output tokens are tracked separately, as the
SCI for AI specification recommends.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterable

from ..estimate import Estimate, total

DEFAULT_OUTPUT_TOKENS_PER_SECOND = 50.0


@dataclass(frozen=True)
class AgentCall:
    provider: str  # EcoLogits provider id: "anthropic", "google_genai", "mistralai", ...
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float | None = None


@dataclass
class AgentFootprint:
    energy_kwh: Estimate
    gwp_g: Estimate
    water_l: Estimate
    calls: int
    input_tokens: int
    output_tokens: int
    models: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    method: str = "ecologits"

    def sci_for_ai(self, functional_units: float, unit: str = "resolved issue") -> dict:
        per_unit = self.gwp_g / functional_units
        out = {"functional_unit": unit, "functional_units": functional_units, "g_per_unit": per_unit.to_dict()}
        if self.output_tokens:
            out["g_per_million_output_tokens"] = (self.gwp_g / self.output_tokens * 1e6).to_dict()
        if self.input_tokens:
            out["g_per_million_input_tokens_blended"] = (self.gwp_g / self.input_tokens * 1e6).to_dict()
        return out

    def to_dict(self) -> dict:
        return {
            "energy_kwh": self.energy_kwh.to_dict(9),
            "gwp_g": self.gwp_g.to_dict(),
            "water_l": self.water_l.to_dict(),
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "models": self.models,
            "warnings": sorted(set(self.warnings)),
            "method": self.method,
        }


def _range(value) -> Estimate:
    v = value.value
    if hasattr(v, "min"):
        return Estimate.from_range(v.min, v.max)
    return Estimate.exact(v)


def call_footprint(call: AgentCall, electricity_zone: str | None = None) -> tuple[Estimate, Estimate, Estimate, list[str]]:
    """(energy kWh, GWP g incl. embodied, water L, warnings) for one LLM call."""
    from ecologits.tracers.utils import llm_impacts  # optional dependency

    latency = call.latency_s or max(call.output_tokens / DEFAULT_OUTPUT_TOKENS_PER_SECOND, 0.5)
    logging.getLogger("ecologits").setLevel(logging.ERROR)
    impacts = llm_impacts(call.provider, call.model, call.output_tokens, latency, electricity_zone)
    if impacts is None or getattr(impacts, "errors", None):
        raise ValueError(f"EcoLogits cannot model {call.provider}/{call.model}: {getattr(impacts, 'errors', None)}")
    warnings = [w.code for w in (impacts.warnings or [])]
    return _range(impacts.energy), _range(impacts.gwp) * 1000.0, _range(impacts.wcf), warnings


def agent_footprint(calls: Iterable[AgentCall], electricity_zone: str | None = None) -> AgentFootprint:
    energies, gwps, waters, warnings = [], [], [], []
    models: dict[str, int] = {}
    n = inp = out = 0
    for call in calls:
        e, g, w, warn = call_footprint(call, electricity_zone)
        energies.append(e), gwps.append(g), waters.append(w), warnings.extend(warn)
        models[call.model] = models.get(call.model, 0) + 1
        n, inp, out = n + 1, inp + call.input_tokens, out + call.output_tokens
    return AgentFootprint(total(energies), total(gwps), total(waters), n, inp, out, models, warnings)


def calls_from_trace(jsonl: str, provider: str, model: str, chars_per_token: float = 4.0) -> list[AgentCall]:
    """Reconstruct LLM calls from a GitLab Duo session trace (``GET /ai/duo_workflows/workflows/:id/trace.jsonl``).

    The trace has messages, not token counts. Each ``ai`` message is one model call whose
    input is the whole conversation so far — the quadratic "state snowball" of agent loops.
    This is an estimate and is labelled as such in the ledger.
    """
    context_chars = 0
    calls = []
    for line in jsonl.splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        content = entry.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content)
        if entry.get("message_type") == "ai":
            calls.append(AgentCall(provider, model, int(context_chars / chars_per_token), max(int(len(content) / chars_per_token), 1)))
        context_chars += len(content)
    return calls
