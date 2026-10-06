"""The hands-off loop: one dispatcher tick.

Every tick (Cloud Scheduler → Cloud Run, or a scheduled GitLab pipeline):
  1. read the Surge Requests: issues labelled ``surge::queued`` / ``surge::scheduled``;
  2. fetch the grid's decision signal for every candidate region;
  3. plan with the CP-SAT dispatcher under each issue's service level;
  4. start the work whose window has opened — a GitLab Duo flow through the Flows API
     (bots cannot trigger flows by mention) — and relabel the issue ``surge::running``;
  5. let @grid explain every hold, deferral and release on the issue itself.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from . import voice
from .dispatch.jobs import Job, job_from_issue
from .dispatch.optimizer import Plan, plan
from .signals.base import Series, parse_time, utc
from .signals.regions import REGIONS

QUEUED, SCHEDULED, RUNNING = "surge::queued", "surge::scheduled", "surge::running"

# Typical duration and facility power of each kind of work (overridable per issue with
# ``energy::<kind>`` labels). Agent sessions assume a self-hosted model in the chosen region;
# for provider-hosted models only the CI side is shiftable and the ledger says so.
PIPELINE_KINDS = {"ci_pipeline": "heavy-tests", "security_scan": "heavy-scan"}

JOB_PROFILES = {
    "agent_session": (timedelta(minutes=40), 0.35),
    "ci_pipeline": (timedelta(minutes=20), 0.05),
    "security_scan": (timedelta(minutes=60), 0.08),
    "dependency_upgrade": (timedelta(minutes=45), 0.35),
}


class SignalProvider(Protocol):
    def decision_signal(self, region: str, now: datetime) -> Series: ...


@dataclass
class LoopConfig:
    regions: tuple[str, ...] = ("europe-north1", "europe-southwest1")
    capacity: int = 3
    horizon: timedelta = timedelta(hours=36)
    tick: timedelta = timedelta(minutes=30)
    flow_consumer_id: int | None = None  # AI Catalog consumer of the "surge-worker" flow
    workflow_definition: str | None = "developer/v1"  # fallback: GitLab's foundational developer flow
    ref: str = "main"
    dry_run: bool = False


@dataclass
class TickReport:
    plan: Plan
    started: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)


def webhook_wants_tick(event: dict) -> bool:
    """Should a GitLab issue event tick now instead of waiting for the 30-minute heartbeat?

    Yes when an open issue just became a Surge Request or critical: critical work then starts
    within seconds, and a new hold is explained while the author is still looking. The loop's
    own relabelling (queued → scheduled → running) never matches, so ticks cannot feed back.
    """
    if event.get("object_kind") not in ("issue", "work_item"):
        return False
    attrs = event.get("object_attributes") or {}
    if attrs.get("state", "opened") != "opened":
        return False
    labels = {label.get("title") for label in event.get("labels") or []}
    change = (event.get("changes") or {}).get("labels")
    if change:
        before = {label.get("title") for label in change.get("previous") or []}
    else:
        before = set() if attrs.get("action") in ("open", "reopen") else labels
    return bool((labels - before) & {QUEUED, "priority::critical", "surge::now"})


def kind_of(labels: list[str]) -> str:
    for label in labels:
        if label.startswith("energy::") and label.split("::", 1)[1] in JOB_PROFILES:
            return label.split("::", 1)[1]
    return "agent_session"


def issue_to_job(issue: dict, regions: tuple[str, ...]) -> Job:
    labels = issue.get("labels", [])
    kind = kind_of(labels)
    duration, power = JOB_PROFILES[kind]
    return job_from_issue(issue["iid"], labels, parse_time(issue["created_at"]), duration, power, regions, kind)


def cost_of_not_waiting(series: Series, job: Job, now: datetime, horizon: timedelta,
                        slot: timedelta = timedelta(minutes=30)) -> tuple[float, datetime | None]:
    """Grams that waiting for the cleanest start in view would have saved, and that start.

    Critical work runs anyway; the number is the honest price of urgency, for the ledger.
    """
    d, n = job.slots(slot), max(1, int(horizon / slot))
    vals = series.on_grid(now, n + d, slot)
    kwh_per_slot = job.energy_kwh / d

    def cost(s: int) -> float | None:
        window = vals[s:s + d]
        return None if len(window) < d or None in window else kwh_per_slot * sum(window)

    now_cost = cost(0)
    if now_cost is None:
        return 0.0, None
    best_cost, best_slot = min(((c, s) for s in range(n) if (c := cost(s)) is not None), default=(now_cost, 0))
    return max(0.0, now_cost - best_cost), now + best_slot * slot


def _price_now(signals, region: str, now: datetime) -> float | None:
    """Day-ahead price for the region's bidding zone, when the provider has prices (cached upstream)."""
    zone = REGIONS[region].price_zone if region in REGIONS else None
    if not zone or not hasattr(signals, "prices"):
        return None
    try:
        return signals.prices(zone, now).value_at(now)
    except Exception:  # noqa: BLE001 — a missing price only shortens the note
        return None


def tick(gitlab, signals: SignalProvider, cfg: LoopConfig, now: datetime) -> TickReport:
    now = utc(now)
    issues = {i["iid"]: i for label in (QUEUED, SCHEDULED) for i in gitlab.issues([label])}
    jobs = [issue_to_job(i, cfg.regions) for i in issues.values()]
    if not jobs:  # an empty battery costs nothing: no signal fetch, no solver
        return TickReport(plan([], {}, now, cfg.horizon))
    sig = {r: signals.decision_signal(r, now) for r in cfg.regions}
    p = plan(jobs, sig, now, cfg.horizon, capacity=cfg.capacity)
    report = TickReport(p)
    for a in p.assignments:
        iid = int(a.job_id.lstrip("#"))
        issue = issues[iid]
        job = next(j for j in jobs if j.id == a.job_id)
        now_g = sig[a.region].value_at(now) or a.expected_g / max(job.energy_kwh, 1e-9)
        # Release only work whose slot starts now (plans start at ``now``); the next tick, at most one
        # tick away, re-plans the rest. Starting a later slot early would run it in a dirtier one.
        # Critical work always starts, even if clock skew put its release a moment after ``now``.
        if a.start <= now or job.urgent:
            if job.urgent:
                extra_g, cleanest = cost_of_not_waiting(sig[a.region], job, now, cfg.horizon)
                note = voice.urgent(a.region, now_g, extra_g, cleanest)
            else:
                note = voice.releasing(a.region, now_g, _price_now(signals, a.region, now), 1)
            report.started.append(a.job_id)
            report.notes[a.job_id] = note
            if not cfg.dry_run:
                if job.kind in PIPELINE_KINDS:
                    # CI work moves too: run the deferred heavy pipeline now, on the green runner if configured.
                    gitlab.run_pipeline(cfg.ref, {"JOULE_TASK": PIPELINE_KINDS[job.kind], "JOULE_ISSUE": str(iid),
                                                  "JOULE_REGION": a.region})
                else:
                    goal = (f"Resolve issue #{iid}: {issue.get('title', '')}. Follow AGENTS.md. Run the tests, keep "
                            f"the change minimal, open a merge request that closes #{iid}.")
                    gitlab.start_flow(goal, consumer_id=cfg.flow_consumer_id,
                                      workflow_definition=None if cfg.flow_consumer_id else cfg.workflow_definition,
                                      issue_iid=iid)
                gitlab.set_labels(iid, add=[RUNNING], remove=[QUEUED, SCHEDULED])
                gitlab.issue_note(iid, note)
        else:
            planned = a.expected_g / max(job.energy_kwh, 1e-9)
            saving = 1 - planned / now_g if now_g else 0.0
            note = voice.holding(a.region, now_g, a.start, planned, saving, job.deadline)
            report.held.append(a.job_id)
            first_hold = QUEUED in issue.get("labels", [])
            report.notes[a.job_id] = note
            if not cfg.dry_run and first_hold:
                gitlab.set_labels(iid, add=[SCHEDULED], remove=[QUEUED])
                gitlab.issue_note(iid, note)
    for job_id in p.deferred:  # no slot in view beats the zone's typical hour: keep charging the battery
        iid = int(job_id.lstrip("#"))
        job = next(j for j in jobs if j.id == job_id)
        region = next(r for r in job.regions if r in sig)
        ahead = [pt.value for pt in sig[region].slice(now, now + cfg.horizon)]
        now_g = sig[region].value_at(now) or (ahead[0] if ahead else 0.0)
        note = voice.deferring(region, now_g, statistics.median(ahead) if ahead else now_g,
                               cfg.horizon.total_seconds() / 3600, job.deadline)
        report.deferred.append(job_id)
        report.notes[job_id] = note
        if not cfg.dry_run and QUEUED in issues[iid].get("labels", []):
            gitlab.set_labels(iid, add=[SCHEDULED], remove=[QUEUED])
            gitlab.issue_note(iid, note)
    return report


def publish_plan(gitlab, report: TickReport, title_prefix: str = "Dispatch plan") -> dict | None:
    """Post the plan as an issue — the Plan stage, written by the grid."""
    p = report.plan
    rows = [{"job": a.job_id, "region": a.region, "start": a.start.strftime("%a %H:%M UTC"), "expected_g": a.expected_g}
            for a in p.assignments]
    if not rows:
        return None
    body = voice.daily_plan(rows, f"from {p.start:%Y-%m-%d %H:%M} UTC")
    body += (f"\n\nExpected **{p.expected_g:.1f} g** vs {p.baseline_g:.1f} g if everything ran now "
             f"({p.saving_fraction:.0%} less). Solver: {p.solver} ({p.status}).")
    return gitlab.create_issue(f"{title_prefix} — {p.start:%Y-%m-%d %H:%M} UTC", body, ["surge::plan"])
