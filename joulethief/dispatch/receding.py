"""Receding-horizon simulation on historical data — honest evaluation of a dispatch policy.

At every tick the dispatcher sees only what it would have seen live (forecasts at the
right lead time, day-ahead prices only after publication), plans, commits the jobs that
start before the next tick, and moves on. Emissions are then scored against what the grid
actually did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from ..signals.base import Series, utc
from .jobs import Job
from .optimizer import AllowedStart, Assignment, plan

ForecastFn = Callable[[str, datetime], Series]  # (region, now) -> signal known at ``now``


@dataclass
class OfficeHours:
    """When a human is around to approve (supervised autonomy)."""

    tz: str = "Europe/London"
    start_hour: int = 9
    end_hour: int = 18
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)

    def __call__(self, region: str, t: datetime) -> bool:
        local = t.astimezone(ZoneInfo(self.tz))
        return local.weekday() in self.weekdays and self.start_hour <= local.hour < self.end_hour


@dataclass
class SimResult:
    policy: str
    jobs: int
    energy_kwh: float
    realized_g: float
    surplus_kwh: float
    late_jobs: int
    mean_wait_h: float
    assignments: list[Assignment] = field(default_factory=list)

    @property
    def surplus_share(self) -> float:
        return self.surplus_kwh / self.energy_kwh if self.energy_kwh else 0.0

    def to_dict(self) -> dict:
        return {"policy": self.policy, "jobs": self.jobs, "energy_kwh": round(self.energy_kwh, 4),
                "realized_g": round(self.realized_g, 2), "surplus_share": round(self.surplus_share, 4),
                "late_jobs": self.late_jobs, "mean_wait_h": round(self.mean_wait_h, 2)}


def _score(assignments: list[Assignment], jobs: dict[str, Job], actual: dict[str, Series], slot: timedelta,
           surplus: Callable[[str, datetime], bool] | None) -> tuple[float, float, float]:
    grams = energy = surplus_kwh = 0.0
    for a in assignments:
        job = jobs[a.job_id]
        steps = job.slots(slot)
        per_slot = job.energy_kwh / steps
        for k in range(steps):
            t = a.start + k * slot + slot / 2
            v = actual[a.region].value_at(t)
            if v is None:
                v = actual[a.region].mean()
            grams += per_slot * v
            energy += per_slot
            if surplus and surplus(a.region, t):
                surplus_kwh += per_slot
    return grams, energy, surplus_kwh


def simulate(jobs: list[Job], actual: dict[str, Series], forecast: ForecastFn, policy: str, start: datetime,
             end: datetime, tick: timedelta = timedelta(hours=1), slot: timedelta = timedelta(minutes=30),
             capacity: int = 4, horizon: timedelta = timedelta(hours=48), office_hours: AllowedStart | None = None,
             surplus: Callable[[str, datetime], bool] | None = None, time_limit_s: float = 2.0) -> SimResult:
    """Policies: ``run_now`` (baseline), ``supervised`` (carbon-aware, starts only in office hours),
    ``hands_off`` (carbon-aware, 24/7)."""
    start, end = utc(start), utc(end)
    by_id = {j.id: j for j in jobs}
    committed: list[Assignment] = []
    if policy == "run_now":
        for j in jobs:
            region = j.regions[0]
            committed.append(Assignment(j.id, region, j.release, j.release + j.slots(slot) * slot, 0.0))
    else:
        mask = office_hours if policy == "supervised" else None
        started: set[str] = set()
        now = start
        # Critical work never waits for the grid (or for a human): it starts the moment it is filed.
        for j in jobs:
            if j.urgent:
                committed.append(Assignment(j.id, j.regions[0], j.release, j.release + j.slots(slot) * slot, 0.0))
                started.add(j.id)
        while now < end:
            pending = [j for j in jobs if j.id not in started and j.release < now + tick]
            if pending:
                signals = {r: forecast(r, now) for r in {r for j in pending for r in j.regions}}
                # capacity left after jobs already running
                n = int(horizon / slot)
                cap = {r: [capacity] * n for r in signals}
                for a in committed:
                    s0 = int((a.start - now) / slot)
                    for t in range(max(0, s0), min(n, s0 + by_id[a.job_id].slots(slot))):
                        if a.region in cap:
                            cap[a.region][t] = max(0, cap[a.region][t] - 1)
                p = plan(pending, signals, now, horizon, slot, cap, allowed_start=mask, mask_is_hard=True,
                         time_limit_s=time_limit_s)
                for a in p.starting_before(now + tick):
                    committed.append(a)
                    started.add(a.job_id)
            now += tick
        # anything never started (end of data): run at the end
        for j in jobs:
            if j.id not in started:
                committed.append(Assignment(j.id, j.regions[0], max(j.release, end), max(j.release, end) + j.slots(slot) * slot, 0.0, forced=True))
    grams, energy, surplus_kwh = _score(committed, by_id, actual, slot, surplus)
    late = sum(1 for a in committed if a.start + by_id[a.job_id].duration > by_id[a.job_id].deadline + timedelta(minutes=1))
    waits = [(a.start - by_id[a.job_id].release).total_seconds() / 3600 for a in committed]
    return SimResult(policy, len(jobs), energy, grams, surplus_kwh, late, sum(waits) / len(waits) if waits else 0.0, committed)


def synthetic_backlog(start: datetime, days: int, per_weekday: int = 12, seed: int = 7, region: str = "europe-north1",
                      tz: str = "Europe/London") -> list[Job]:
    """A reproducible stream of post-code work filed by humans during working days.

    Mix (energy at the compute site, including PUE): agent sessions on a self-hosted model,
    CI pipelines, full security scans and dependency-upgrade runs. Priorities follow
    PRIORITY_SLA: 10 % critical, 30 % high, 40 % normal, 20 % low.
    """
    import random

    from .jobs import PRIORITY_SLA

    rng = random.Random(seed)
    kinds = [  # (kind, duration minutes range, power kW range)
        ("agent_session", (20, 60), (0.25, 0.45)),  # one GPU-backed inference worker
        ("ci_pipeline", (10, 30), (0.03, 0.08)),
        ("security_scan", (30, 90), (0.05, 0.12)),
        ("dependency_upgrade", (30, 60), (0.25, 0.45)),
    ]
    priorities = ["critical"] * 1 + ["high"] * 3 + ["normal"] * 4 + ["low"] * 2
    local = ZoneInfo(tz)
    jobs = []
    day0 = utc(start).astimezone(local).replace(hour=0, minute=0, second=0, microsecond=0)
    for d in range(days):
        day = day0 + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        for k in range(per_weekday):
            kind, (dmin, dmax), (pmin, pmax) = rng.choice(kinds)
            created = day.replace(hour=9) + timedelta(minutes=rng.randint(0, 9 * 60 - 1))
            prio = rng.choice(priorities)
            duration = timedelta(minutes=rng.randint(dmin, dmax))
            jobs.append(Job(f"{day:%m%d}-{k:02d}", duration, rng.uniform(pmin, pmax), created.astimezone(timezone.utc),
                            created.astimezone(timezone.utc) + PRIORITY_SLA[prio] + duration, (region,), kind, prio))
    return jobs
