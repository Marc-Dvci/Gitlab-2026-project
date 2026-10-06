"""Carbon receipts: signed, verifiable environmental claims attached to every artifact.

A receipt is an in-toto Statement v1 whose predicate records the build's energy, both
carbon ledgers, water, the agents' own footprint (SCI for AI), the grid signals used
(with content hashes) and the budget verdict. The CI pipeline signs it keylessly with
Sigstore (GitLab OIDC → Fulcio, logged in Rekor):

    cosign attest --yes --type "$JOULE_PREDICATE_TYPE" --predicate receipt.predicate.json "$IMAGE@$DIGEST"

and the deploy job refuses images whose receipt is missing, unsigned or over budget.
Anyone can check a claim with ``cosign verify-attestation``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
# A URN avoids pointing at a domain we do not control; override with the project's
# GitLab Pages URL for the spec once published (JOULE_PREDICATE_TYPE).
PREDICATE_TYPE = "urn:joulethief:carbon-receipt:v1"
METHODOLOGY = {
    "sci": "ISO/IEC 21031:2024 (Software Carbon Intensity)",
    "sci_for_ai": "Green Software Foundation SCI for AI (ratified 2025-12)",
    "ledgers": ["attributional: location-based average intensity (GHG Protocol Scope 2)",
                "consequential: marginal intensity of the responding generator"],
    "llm_estimates": "EcoLogits (ranges)",
    "power_model": "Cloud Carbon Footprint coefficients (ranges)",
}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Budget:
    period: str  # e.g. "2026-10"
    cap_g: float
    spent_g: float  # consequential, including this artifact

    @property
    def remaining_g(self) -> float:
        return self.cap_g - self.spent_g

    @property
    def within(self) -> bool:
        return self.spent_g <= self.cap_g


@dataclass
class Receipt:
    subject_name: str
    subject_digest: str  # sha256 hex of the artifact / image manifest
    build: dict  # energy_kwh, attributional_g, consequential_g, water_l (each low/likely/high), region, window
    agents: dict  # AgentFootprint.to_dict() + sci_for_ai
    runtime: dict  # sci per functional unit for the deployed service, if measured
    signals: list[dict]  # {source, zone, metric, fetched_at, sha256}
    budget: Budget
    pipeline: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def predicate(self) -> dict:
        return {
            "version": "1",
            "generatedAt": self.generated_at,
            "methodology": METHODOLOGY,
            "pipeline": self.pipeline,
            "build": self.build,
            "agents": self.agents,
            "runtime": self.runtime,
            "signals": self.signals,
            "budget": {"period": self.budget.period, "capG": self.budget.cap_g, "spentG": round(self.budget.spent_g, 3),
                       "remainingG": round(self.budget.remaining_g, 3)},
            "verdict": "within-budget" if self.budget.within else "over-budget",
        }

    def statement(self, predicate_type: str = PREDICATE_TYPE) -> dict:
        return {
            "_type": STATEMENT_TYPE,
            "subject": [{"name": self.subject_name, "digest": {"sha256": self.subject_digest}}],
            "predicateType": predicate_type,
            "predicate": self.predicate(),
        }


@dataclass
class Policy:
    predicate_type: str = PREDICATE_TYPE
    require_within_budget: bool = True
    require_ranges: bool = True
    max_signal_age_hours: float = 36.0
    max_build_consequential_g: float | None = None


def verify(statement: dict, expected_digest: str | None = None, policy: Policy | None = None,
           now: datetime | None = None) -> list[str]:
    """Return the list of policy violations (empty means the receipt is acceptable).

    Signature verification is cosign's job; this checks the *content* of a verified statement.
    """
    policy = policy or Policy()
    now = now or datetime.now(timezone.utc)
    problems = []
    if statement.get("_type") != STATEMENT_TYPE:
        problems.append("not an in-toto v1 statement")
    if statement.get("predicateType") != policy.predicate_type:
        problems.append(f"unexpected predicateType {statement.get('predicateType')!r}")
    subjects = statement.get("subject") or []
    if expected_digest and not any(s.get("digest", {}).get("sha256") == expected_digest for s in subjects):
        problems.append("subject digest does not match the artifact")
    pred = statement.get("predicate") or {}
    if policy.require_within_budget and pred.get("verdict") != "within-budget":
        problems.append("carbon budget exceeded")
    build = pred.get("build") or {}
    if policy.require_ranges:
        for key in ("energy_kwh", "attributional_g", "consequential_g"):
            value = build.get(key)
            if not (isinstance(value, dict) and {"low", "likely", "high"} <= set(value)):
                problems.append(f"build.{key} must be a low/likely/high range")
    if policy.max_build_consequential_g is not None:
        likely = (build.get("consequential_g") or {}).get("likely")
        if likely is not None and likely > policy.max_build_consequential_g:
            problems.append(f"build emitted {likely:.1f} g > limit {policy.max_build_consequential_g:.1f} g")
    for sig in pred.get("signals") or []:
        fetched = sig.get("fetched_at")
        if fetched:
            age = (now - datetime.fromisoformat(fetched)).total_seconds() / 3600
            if age > policy.max_signal_age_hours:
                problems.append(f"signal {sig.get('source')} is {age:.0f} h old")
    return problems


def write_predicate(receipt: Receipt, path: str) -> None:
    with open(path, "w") as fh:
        json.dump(receipt.predicate(), fh, indent=2, sort_keys=True)
