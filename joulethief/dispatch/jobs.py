"""Deferrable work: issues, Surge Requests, pipelines and agent sessions waiting for clean power."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..signals.base import utc

# Service levels attached to GitLab priority labels. "critical" never waits.
PRIORITY_SLA = {
    "critical": timedelta(0),
    "high": timedelta(hours=4),
    "normal": timedelta(hours=24),
    "low": timedelta(hours=72),
}
DEFAULT_PRIORITY = "normal"


@dataclass(frozen=True)
class Job:
    id: str
    duration: timedelta
    power_kw: float  # average facility power while running (IT × PUE)
    release: datetime
    deadline: datetime  # latest *finish* time
    regions: tuple[str, ...] = ("europe-north1",)
    kind: str = "agent_session"
    priority: str = DEFAULT_PRIORITY
    meta: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "release", utc(self.release))
        object.__setattr__(self, "deadline", utc(self.deadline))
        if self.deadline < self.release + self.duration:
            object.__setattr__(self, "deadline", self.release + self.duration)

    @property
    def energy_kwh(self) -> float:
        return self.power_kw * self.duration.total_seconds() / 3600.0

    def slots(self, slot: timedelta) -> int:
        return max(1, math.ceil(self.duration / slot))

    @property
    def urgent(self) -> bool:
        return self.priority == "critical"


def priority_from_labels(labels: list[str]) -> str:
    """Read ``priority::<level>`` (or ``surge::now``) labels; default to normal."""
    for label in labels:
        if label in ("surge::now", "priority::critical", "severity::critical", "incident"):
            return "critical"
    for label in labels:
        if label.startswith("priority::") and label.split("::", 1)[1] in PRIORITY_SLA:
            return label.split("::", 1)[1]
    return DEFAULT_PRIORITY


def job_from_issue(iid: int, labels: list[str], created_at: datetime, duration: timedelta, power_kw: float,
                   regions: tuple[str, ...] = ("europe-north1",), kind: str = "agent_session") -> Job:
    priority = priority_from_labels(labels)
    release = utc(created_at)
    return Job(id=f"#{iid}", duration=duration, power_kw=power_kw, release=release,
               deadline=release + PRIORITY_SLA[priority] + duration, regions=regions, kind=kind, priority=priority,
               meta={"labels": labels})
