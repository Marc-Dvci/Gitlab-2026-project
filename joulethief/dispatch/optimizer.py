"""Carbon-aware dispatch of deferrable work, solved with OR-Tools CP-SAT.

Decision: for every pending job, a region and a start slot inside its service window —
or "defer", when the job's deadline lies beyond the horizon and no slot in view beats
the zone's typical emissions. Objective: minimise expected emissions under the decision
signal (marginal where available). Constraints: release times, deadlines, an optional
allowed-start mask (e.g. office hours for supervised autonomy) and per-region
concurrency limits (virtual capacity curves).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from ..signals.base import Series, utc
from .jobs import Job

AllowedStart = Callable[[str, datetime], bool]


@dataclass(frozen=True)
class Assignment:
    job_id: str
    region: str
    start: datetime
    end: datetime
    expected_g: float
    forced: bool = False  # no feasible slot honoured the constraints; scheduled as early as possible
    late: bool = False  # finishes after the job's deadline


@dataclass
class Plan:
    start: datetime
    slot: timedelta
    assignments: list[Assignment]
    deferred: list[str]
    expected_g: float
    baseline_g: float
    solver: str
    status: str
    capacity: dict[str, list[int]] = field(default_factory=dict)

    def assignment(self, job_id: str) -> Assignment | None:
        return next((a for a in self.assignments if a.job_id == job_id), None)

    def starting_before(self, t: datetime) -> list[Assignment]:
        return [a for a in self.assignments if a.start < utc(t)]

    @property
    def saving_fraction(self) -> float:
        return 1 - self.expected_g / self.baseline_g if self.baseline_g else 0.0

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "slot_minutes": self.slot.total_seconds() / 60,
            "solver": self.solver,
            "status": self.status,
            "expected_g": round(self.expected_g, 3),
            "baseline_g": round(self.baseline_g, 3),
            "saving_fraction": round(self.saving_fraction, 4),
            "deferred": self.deferred,
            "assignments": [
                {**asdict(a), "start": a.start.isoformat(), "end": a.end.isoformat(), "expected_g": round(a.expected_g, 3)}
                for a in self.assignments
            ],
        }


@dataclass
class _Candidate:
    region: str
    slot: int
    cost_mg: int


def _grid(series: Series, start: datetime, n: int, slot: timedelta, unknown: float) -> list[float]:
    return [v if v is not None else unknown for v in series.on_grid(start, n, slot)]


def plan(
    jobs: list[Job],
    signals: dict[str, Series],
    start: datetime,
    horizon: timedelta = timedelta(hours=48),
    slot: timedelta = timedelta(minutes=30),
    capacity: int | dict[str, list[int]] = 4,
    allowed_start: AllowedStart | None = None,
    mask_is_hard: bool = False,
    unknown_signal: dict[str, float] | None = None,
    defer_value: dict[str, float] | None = None,
    time_limit_s: float = 5.0,
    use_solver: bool = True,
) -> Plan:
    start = utc(start)
    n = max(1, int(horizon / slot))
    slot_h = slot.total_seconds() / 3600.0
    regions = sorted({r for j in jobs for r in j.regions if r in signals})
    known = {r: [v for v in signals[r].on_grid(start, n, slot) if v is not None] for r in regions}
    unknown = {r: (unknown_signal or {}).get(r, max(signals[r].values()) if len(signals[r]) else 1000.0) for r in regions}
    sig = {r: _grid(signals[r], start, n, slot, unknown[r]) for r in regions}
    typical = {r: (defer_value or {}).get(r, statistics.median(known[r]) if known[r] else unknown[r]) for r in regions}
    if isinstance(capacity, int):
        cap = {r: [capacity] * n for r in regions}
    else:
        cap = {r: list(capacity.get(r, [0] * n))[:n] + [0] * max(0, n - len(capacity.get(r, []))) for r in regions}

    def cost_mg(job: Job, region: str, s: int) -> int:
        d = job.slots(slot)
        window = sig[region][s:s + d]
        if len(window) < d:  # runs past the horizon: assume the unknown (pessimistic) value
            window = window + [unknown[region]] * (d - len(window))
        return int(round(job.power_kw * slot_h * sum(window) * 1000))

    def start_time(s: int) -> datetime:
        return start + s * slot

    forced: list[Assignment] = []
    candidates: dict[str, list[_Candidate]] = {}
    deferrable: dict[str, int] = {}
    job_by_id = {j.id: j for j in jobs}
    for job in jobs:
        d = job.slots(slot)
        earliest = max(0, math.ceil((job.release - start) / slot))
        latest = math.floor((job.deadline - job.duration - start) / slot)  # last start that still finishes on time
        job_regions = [r for r in job.regions if r in signals]
        if not job_regions:
            raise ValueError(f"no signal for any region of job {job.id}")
        if earliest >= n:
            continue  # not yet released within this horizon
        beyond = latest > n - d
        hi = min(latest, n - d)
        opts = []
        for s in range(earliest, hi + 1):
            for r in job_regions:
                if allowed_start and not job.urgent and not allowed_start(r, start_time(s)):
                    continue
                opts.append(_Candidate(r, s, cost_mg(job, r, s) + s))
        if opts:
            candidates[job.id] = opts
            if beyond:
                deferrable[job.id] = int(round(job.energy_kwh * typical[job_regions[0]] * 1000))
            continue
        if beyond:
            continue  # nothing allowed inside this horizon; the job waits for a later plan
        # Constraints cannot all be honoured: run as early as possible (mask permitting, if hard).
        s = earliest
        if allowed_start and mask_is_hard and not job.urgent:
            while s < n and not allowed_start(job_regions[0], start_time(s)):
                s += 1
            s = min(s, n - 1)
        r = min(job_regions, key=lambda reg: cost_mg(job, reg, s))
        end = start_time(s) + d * slot
        forced.append(Assignment(job.id, r, start_time(s), end, cost_mg(job, r, s) / 1000.0, forced=True,
                                 late=start_time(s) + job.duration > job.deadline))

    # Capacity already taken by forced jobs.
    for a in forced:
        s0 = int((a.start - start) / slot)
        for t in range(s0, min(n, s0 + job_by_id[a.job_id].slots(slot))):
            cap[a.region][t] = max(0, cap[a.region][t] - 1)

    chosen: dict[str, _Candidate] = {}
    solver_name, status = "greedy", "FEASIBLE"
    if use_solver and candidates:
        try:
            chosen, status = _solve_cp_sat(candidates, deferrable, job_by_id, cap, slot, n, time_limit_s)
            solver_name = "cp-sat"
        except ImportError:
            pass
    if solver_name == "greedy" or status not in ("OPTIMAL", "FEASIBLE"):
        chosen = _greedy(candidates, deferrable, job_by_id, cap, slot, n)
        solver_name, status = "greedy", "FEASIBLE"

    assignments = list(forced)
    for job_id, c in chosen.items():
        job = job_by_id[job_id]
        end = start_time(c.slot) + job.slots(slot) * slot
        assignments.append(Assignment(job_id, c.region, start_time(c.slot), end, (c.cost_mg - c.slot) / 1000.0,
                                      late=start_time(c.slot) + job.duration > job.deadline))
    deferred = sorted(j for j in candidates if j not in chosen)
    deferred += sorted(j.id for j in jobs if j.id not in candidates and j.id not in {a.job_id for a in forced}
                       and math.ceil((j.release - start) / slot) < n)

    baseline = 0.0
    for job in jobs:
        s = max(0, math.ceil((job.release - start) / slot))
        if s < n:
            r = next(r for r in job.regions if r in signals)
            baseline += cost_mg(job, r, s) / 1000.0
    expected = sum(a.expected_g for a in assignments) + sum(
        deferrable[j] / 1000.0 for j in deferred if j in deferrable)
    assignments.sort(key=lambda a: (a.start, a.job_id))
    return Plan(start, slot, assignments, deferred, expected, baseline, solver_name, status, cap)


def _solve_cp_sat(candidates, deferrable, job_by_id, cap, slot, n, time_limit_s):
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    x: dict[tuple[str, int], tuple[object, _Candidate]] = {}
    objective = []
    load: dict[tuple[str, int], list] = {}
    for job_id, opts in candidates.items():
        d = job_by_id[job_id].slots(slot)
        vars_ = []
        for k, c in enumerate(opts):
            v = model.NewBoolVar(f"x_{job_id}_{c.region}_{c.slot}")
            x[(job_id, k)] = (v, c)
            vars_.append(v)
            objective.append(c.cost_mg * v)
            for t in range(c.slot, min(n, c.slot + d)):
                load.setdefault((c.region, t), []).append(v)
        if job_id in deferrable:
            defer = model.NewBoolVar(f"defer_{job_id}")
            objective.append(deferrable[job_id] * defer)
            model.AddExactlyOne(vars_ + [defer])
        else:
            model.AddExactlyOne(vars_)
    for (region, t), vs in load.items():
        model.Add(sum(vs) <= cap[region][t])
    model.Minimize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 4
    result = solver.Solve(model)
    status = solver.StatusName(result)
    chosen = {}
    if status in ("OPTIMAL", "FEASIBLE"):
        for (job_id, _), (v, c) in x.items():
            if solver.Value(v):
                chosen[job_id] = c
    return chosen, status


def _greedy(candidates, deferrable, job_by_id, cap, slot, n):
    used = {(r, t): 0 for r in cap for t in range(n)}
    chosen = {}
    order = sorted(candidates, key=lambda j: (job_by_id[j].deadline, -job_by_id[j].energy_kwh))
    for job_id in order:
        d = job_by_id[job_id].slots(slot)
        for c in sorted(candidates[job_id], key=lambda c: c.cost_mg):
            if job_id in deferrable and c.cost_mg > deferrable[job_id]:
                break
            span = range(c.slot, min(n, c.slot + d))
            if all(used[(c.region, t)] < cap[c.region][t] for t in span):
                for t in span:
                    used[(c.region, t)] += 1
                chosen[job_id] = c
                break
    return chosen
