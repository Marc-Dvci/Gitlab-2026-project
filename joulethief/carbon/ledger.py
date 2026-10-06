"""Two ledgers, because one number lies.

* Attributional (GHG Protocol Scope 2, location-based): energy × average grid intensity.
  This is what a sustainability report needs.
* Consequential (marginal): energy × emissions of the generator that answered the extra
  demand. This is what a *decision* needs — and the only basis for "avoided emissions".

Avoided emissions are only ever claimed consequentially, against an explicit
counterfactual (the same work run immediately, in the default region).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ..estimate import Estimate, total


@dataclass
class LedgerEntry:
    activity: str  # issue/MR/pipeline/session reference
    kind: str  # "ci_job" | "agent_session" | "deploy" | "runtime"
    region: str
    start: datetime
    end: datetime
    energy_kwh: Estimate
    attributional_g: Estimate
    consequential_g: Estimate
    water_l: Estimate = field(default_factory=Estimate.zero)
    baseline_consequential_g: Estimate | None = None  # counterfactual: run now, default region
    surplus_energy_kwh: float = 0.0  # energy drawn during surplus (curtailment / negative price) hours
    measured: bool = False  # True for metered energy, False for modelled
    signals: list[str] = field(default_factory=list)

    @property
    def avoided_g(self) -> Estimate | None:
        if self.baseline_consequential_g is None:
            return None
        return self.baseline_consequential_g - self.consequential_g

    def to_json(self) -> str:
        d = asdict(self)
        d["start"], d["end"] = self.start.isoformat(), self.end.isoformat()
        for key in ("energy_kwh", "attributional_g", "consequential_g", "water_l", "baseline_consequential_g"):
            value = getattr(self, key)
            d[key] = value.to_dict(9) if isinstance(value, Estimate) else None
        return json.dumps(d, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "LedgerEntry":
        d = json.loads(line)
        for key in ("energy_kwh", "attributional_g", "consequential_g", "water_l", "baseline_consequential_g"):
            if d.get(key) is not None:
                d[key] = Estimate(**d[key])
        d["start"], d["end"] = datetime.fromisoformat(d["start"]), datetime.fromisoformat(d["end"])
        return cls(**d)


class Ledger:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.entries: list[LedgerEntry] = []
        if path and path.exists():
            self.entries = [LedgerEntry.from_json(line) for line in path.read_text().splitlines() if line.strip()]

    def record(self, entry: LedgerEntry) -> None:
        self.entries.append(entry)
        if self.path:
            with self.path.open("a") as fh:
                fh.write(entry.to_json() + "\n")

    def summary(self) -> dict:
        es = self.entries
        energy = total([e.energy_kwh for e in es])
        avoided = [e.avoided_g for e in es if e.avoided_g is not None]
        surplus = sum(e.surplus_energy_kwh for e in es)
        by_kind: dict[str, Estimate] = {}
        for e in es:
            by_kind[e.kind] = by_kind.get(e.kind, Estimate.zero()) + e.consequential_g
        return {
            "entries": len(es),
            "energy_kwh": energy.to_dict(9),
            "attributional_g": total([e.attributional_g for e in es]).to_dict(),
            "consequential_g": total([e.consequential_g for e in es]).to_dict(),
            "avoided_consequential_g": total(avoided).to_dict() if avoided else None,
            "water_l": total([e.water_l for e in es]).to_dict(),
            "surplus_energy_share": (surplus / energy.likely) if energy.likely else 0.0,
            "consequential_g_by_kind": {k: v.to_dict() for k, v in by_kind.items()},
            "measured_share": sum(1 for e in es if e.measured) / len(es) if es else 0.0,
        }
