"""``joule demo`` — the hands-off loop end to end, offline, on a replayed real grid.

No GitLab account, no cloud: an in-memory GitLab (issues, labels, notes, flow starts,
pipelines) is driven by the production dispatcher (``loop.tick``) every 30 minutes, and at
each filing as the GitLab issue webhook would, across a real week of grid data. The dispatcher sees only what it would have seen live (day-ahead
prices after publication, NESO forecasts at the right lead). Work ships when its flow or
pipeline finishes, and every issue closes with its carbon balance, scored on what the grid
actually did against running the work the moment it was filed.

    joule demo                       # Spain, Mon 5 – Fri 9 May 2025: midday solar surplus
    joule demo --grid gb             # Great Britain, NESO, Mon 21 – Fri 25 Sep 2026
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import loop
from .replay import ReplaySignals, great_britain_2026, spain_2025
from .signals.base import Series

UTC = timezone.utc
SLOT = timedelta(minutes=30)

# (day offset, local time, title, labels as the Surge Intake flow would set them)
STORY = (
    (0, "09:12", "Upgrade FastAPI, uvicorn and mcp to the latest minor versions", ["priority::low", "energy::dependency_upgrade"]),
    (0, "21:10", "Dashboard comparison is slow", ["priority::normal", "energy::agent_session"]),
    (0, "22:05", "Run the full Python 3.11–3.13 test matrix", ["priority::normal", "energy::ci_pipeline"]),
    (1, "19:30", "Full DAST and fuzzing scan before the release", ["priority::low", "energy::security_scan"]),
    (1, "20:20", "Production returns 500 on /api/grid", ["priority::critical", "energy::agent_session"]),
    (2, "07:50", "Add a retry budget to the Energy-Charts adapter", ["priority::high", "energy::agent_session"]),
)
EVENT_ORDER = {"filed": 0, "note": 1, "flow": 2, "pipeline": 2, "shipped": 3}
BACKGROUND_KINDS = {
    "agent_session": ("Refactor", ["the ledger summary", "the receipt builder", "region metadata", "the CLI help"]),
    "ci_pipeline": ("Nightly test matrix", ["main", "release/0.2", "the MCP server", "the dashboard"]),
    "security_scan": ("Full dependency audit", ["runtime image", "dev requirements", "the Terraform module"]),
    "dependency_upgrade": ("Bump", ["ortools", "ecologits", "fastapi", "pytest"]),
}
BACKGROUND_PRIORITIES = ["high"] * 3 + ["normal"] * 4 + ["low"] * 3

GRIDS = {
    "es": (spain_2025, date(2025, 5, 5), "Europe/Madrid"),
    "gb": (great_britain_2026, date(2026, 9, 21), "Europe/London"),
}


@dataclass
class Event:
    t: datetime
    iid: int
    kind: str  # filed | note | flow | pipeline | shipped
    text: str

    def to_dict(self) -> dict:
        return {"t": self.t.isoformat(), "iid": self.iid, "kind": self.kind, "text": self.text}


@dataclass
class SandboxGitLab:
    """The slice of the GitLab API the hands-off loop uses, in memory, on a replay clock."""

    clock: datetime
    region: str
    store: dict[int, dict] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    runs: dict[int, tuple[datetime, datetime]] = field(default_factory=dict)  # iid -> (start, end)

    def file(self, title: str, labels: list[str], created_at: datetime, story: bool = False) -> int:
        iid = len(self.store) + 1
        self.store[iid] = {"iid": iid, "title": title, "labels": [*labels, loop.QUEUED], "state": "opened",
                           "created_at": created_at.isoformat(), "story": story}
        self.events.append(Event(created_at, iid, "filed", f"filed and triaged: {', '.join(self.store[iid]['labels'])}"))
        return iid

    # -- the GitLab client surface used by loop.tick ---------------------------------------
    def issues(self, labels: list[str], state: str = "opened") -> list[dict]:
        return [dict(i) for i in self.store.values()
                if i["state"] == state and set(labels) <= set(i["labels"]) and i["created_at"] <= self.clock.isoformat()]

    def issue_note(self, iid: int, body: str) -> dict:
        self.events.append(Event(self.clock, iid, "note", body))
        return {"id": len(self.events)}

    def set_labels(self, iid: int, add=(), remove=()) -> dict:
        labels = [x for x in self.store[iid]["labels"] if x not in remove]
        self.store[iid]["labels"] = labels + [x for x in add if x not in labels]
        return self.store[iid]

    def start_flow(self, goal: str, *, issue_iid: int | None = None, **_kw) -> dict:
        self._run(issue_iid, "flow", "Surge Worker flow started through the Flows API (hands-off, no user prompts)")
        return {"id": issue_iid}

    def run_pipeline(self, ref: str, variables: dict[str, str]) -> dict:
        iid = int(variables["JOULE_ISSUE"])
        self._run(iid, "pipeline", f"pipeline started on `{ref}` with JOULE_TASK={variables['JOULE_TASK']}")
        return {"id": iid}

    def _run(self, iid: int | None, kind: str, text: str) -> None:
        if iid is None:
            return
        duration = loop.JOB_PROFILES[loop.kind_of(self.store[iid]["labels"])][0]
        self.runs[iid] = (self.clock, self.clock + duration)
        self.events.append(Event(self.clock, iid, kind, text))


def realized_g(actual: Series, start: datetime, duration: timedelta, power_kw: float) -> float:
    """Emissions of a run, scored per 30-minute slot on what the grid actually did (as the experiments do)."""
    steps = max(1, -(-duration // SLOT))
    kwh = power_kw * duration.total_seconds() / 3600 / steps
    total = 0.0
    for k in range(steps):
        v = actual.value_at(start + k * SLOT + SLOT / 2)
        total += kwh * (v if v is not None else actual.mean())
    return total


def _background(day0: datetime, days: int, per_day: int, seed: int) -> list[tuple[datetime, str, list[str]]]:
    rng = random.Random(seed)
    out = []
    for d in range(days):
        for _ in range(per_day):
            kind = rng.choice(sorted(BACKGROUND_KINDS))
            verb, objects = BACKGROUND_KINDS[kind]
            t = day0 + timedelta(days=d, hours=9, minutes=rng.randint(0, 9 * 60 - 1))
            out.append((t, f"{verb} {rng.choice(objects)}", [f"priority::{rng.choice(BACKGROUND_PRIORITIES)}", f"energy::{kind}"]))
    return out


def run(grid: str = "es", start: date | None = None, days: int = 5, filing_days: int = 3, per_day: int = 8,
        seed: int = 7, replay: ReplaySignals | None = None) -> dict:
    """Replay ``days`` of hands-off operation; work is filed on the first ``filing_days`` days."""
    make, default_start, tz = GRIDS[grid]
    replay = replay or make()
    local = ZoneInfo(tz)
    day0 = datetime.combine(start or default_start, datetime.min.time(), tzinfo=local)
    t, end = day0.astimezone(UTC), (day0 + timedelta(days=days)).astimezone(UTC)
    gl = SandboxGitLab(t, replay.region)
    filings = [(day0 + timedelta(days=d, hours=int(hm[:2]), minutes=int(hm[3:])), title, labels, True)
               for d, hm, title, labels in STORY if d < filing_days]
    filings += [(*b, False) for b in _background(day0, filing_days, per_day, seed)]
    for when, title, labels, story in sorted(filings, key=lambda f: f[0]):
        gl.file(title, labels, when.astimezone(UTC), story)

    cfg = loop.LoopConfig(regions=(replay.region,), flow_consumer_id=1)
    # The 30-minute heartbeat, plus a webhook tick whenever a filing is a new or critical Surge Request.
    ticks = [(t + k * cfg.tick, "heartbeat") for k in range(int((end - t) / cfg.tick))]
    ticks += [(i_created, "webhook") for i_created, labels in
              ((datetime.fromisoformat(i["created_at"]), i["labels"]) for i in gl.store.values())
              if loop.webhook_wants_tick({"object_kind": "issue", "object_attributes": {"action": "open"},
                                          "labels": [{"title": x} for x in labels]})]
    timeline, shipped = [], {}
    for t, why in sorted(ticks):
        gl.clock = t
        for iid, (s, e) in list(gl.runs.items()):  # work whose flow or pipeline has finished ships
            if e <= t and iid not in shipped:
                shipped[iid] = _ship(gl, replay, iid, s, e)
        report = loop.tick(gl, replay, cfg, t)
        if why == "webhook":
            continue
        queued = [i for i in gl.store.values() if i["state"] == "opened" and i["created_at"] <= t.isoformat()
                  and {loop.QUEUED, loop.SCHEDULED} & set(i["labels"])]
        running = [iid for iid, (s, e) in gl.runs.items() if s <= t < e]
        price = replay.price_series.value_at(t) if replay.price_series is not None else None
        timeline.append({"t": t.isoformat(), "signal": replay.actual.value_at(t), "price": price,
                         "surplus": replay.surplus(t),
                         "queued_kwh": round(sum(_energy(i) for i in queued), 4),
                         "running_kwh": round(sum(_energy(gl.store[i]) for i in running), 4),
                         "queued": len(queued), "running": len(running), "released": report.started})
    gl.clock = end
    for iid, (s, e) in gl.runs.items():
        if iid not in shipped and e <= end:
            shipped[iid] = _ship(gl, replay, iid, s, e)
    return _report(grid, replay, gl, timeline, shipped, day0, days)


def _energy(issue: dict) -> float:
    duration, power = loop.JOB_PROFILES[loop.kind_of(issue["labels"])]
    return power * duration.total_seconds() / 3600


def _ship(gl: SandboxGitLab, replay: ReplaySignals, iid: int, start: datetime, end: datetime) -> dict:
    issue = gl.store[iid]
    job = loop.issue_to_job(issue, (replay.region,))
    filed = job.release
    actual_g = realized_g(replay.actual, start, job.duration, job.power_kw)
    run_now_g = realized_g(replay.actual, filed, job.duration, job.power_kw)
    surplus_kwh = sum(job.energy_kwh / job.slots(SLOT) for k in range(job.slots(SLOT))
                      if replay.surplus(start + k * SLOT + SLOT / 2))
    on_time = start + job.duration <= job.deadline + timedelta(minutes=1)
    saving = 1 - actual_g / run_now_g if run_now_g else 0.0
    versus = f"{-saving:+.0%}" if abs(saving) >= 0.005 else "no difference"
    surplus_text = f" {surplus_kwh / job.energy_kwh:.0%} of it in surplus hours." if replay.price_series is not None else ""
    body = (f"**Shipped** · {job.energy_kwh:.3f} kWh in `{replay.region}`, **{actual_g:.1f} gCO₂e** on the decision "
            f"signal vs {run_now_g:.1f} g had it run when filed ({versus})."
            f"{surplus_text} Waited {(start - filed).total_seconds() / 3600:.1f} h; deadline "
            f"{'met' if on_time else 'MISSED'}.")
    gl.set_labels(iid, remove=[loop.RUNNING])
    issue["state"] = "closed"
    gl.events.append(Event(end, iid, "shipped", body))
    return {"iid": iid, "title": issue["title"], "priority": job.priority, "kind": job.kind, "filed": filed.isoformat(),
            "start": start.isoformat(), "energy_kwh": round(job.energy_kwh, 4), "g": round(actual_g, 2),
            "run_now_g": round(run_now_g, 2), "surplus_kwh": round(surplus_kwh, 4), "on_time": on_time,
            "wait_h": round((start - filed).total_seconds() / 3600, 2), "story": issue["story"]}


def _report(grid, replay, gl, timeline, shipped, day0, days) -> dict:
    runs = list(shipped.values())
    g, base = sum(r["g"] for r in runs), sum(r["run_now_g"] for r in runs)
    kwh = sum(r["energy_kwh"] for r in runs)
    surplus = sum(r["surplus_kwh"] for r in runs)
    summary = {"issues": len(gl.store), "shipped": len(runs), "late": sum(not r["on_time"] for r in runs),
               "hands_off_g": round(g, 1), "run_now_g": round(base, 1),
               "reduction": round(1 - g / base, 4) if base else 0.0,
               "surplus_share": round(surplus / kwh, 4) if kwh and replay.price_series is not None else None,
               "mean_wait_h": round(sum(r["wait_h"] for r in runs) / len(runs), 2) if runs else 0.0,
               "flows_started": sum(e.kind == "flow" for e in gl.events),
               "pipelines_started": sum(e.kind == "pipeline" for e in gl.events),
               "notes_posted": sum(e.kind == "note" for e in gl.events)}
    return {"grid": grid, "region": replay.region, "label": replay.label, "start": day0.isoformat(), "days": days,
            "signal": {"metric": replay.actual.metric, "unit": replay.actual.unit}, "summary": summary,
            "issues": [{"iid": i["iid"], "title": i["title"], "labels": i["labels"], "state": i["state"],
                        "story": i["story"]} for i in gl.store.values()],
            "runs": sorted(runs, key=lambda r: r["iid"]), "timeline": timeline,
            "events": [e.to_dict() for e in sorted(gl.events, key=lambda e: (e.t, e.iid, EVENT_ORDER[e.kind]))]}


def _hhmm(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%a %H:%M UTC")


def markdown(result: dict, story_only: bool = True) -> str:
    """The replay as a human reads it: each story issue's timeline, then the whole week's balance."""
    s = result["summary"]
    out = [f"# Hands-off replay — {result['label']}", "",
           f"`joule demo --grid {result['grid']}` · region `{result['region']}` · {result['days']} days from "
           f"{result['start'][:10]} · production dispatcher (`joulethief.loop.tick`) every 30 min against an "
           "in-memory GitLab. Issues arrive already triaged, with the labels the Surge Intake flow sets.", "",
           "| Issues | Shipped | Deadlines missed | Hands-off gCO₂e | Run-now gCO₂e | Reduction | Energy in surplus hours | Mean wait |",
           "|---:|---:|---:|---:|---:|---:|---:|---:|",
           f"| {s['issues']} | {s['shipped']} | {s['late']} | {s['hands_off_g']:.0f} | {s['run_now_g']:.0f} | "
           f"{s['reduction']:.1%} | {'n/a' if s['surplus_share'] is None else format(s['surplus_share'], '.0%')} | "
           f"{s['mean_wait_h']:.1f} h |", "",
           f"{s['flows_started']} Duo flows and {s['pipelines_started']} pipelines started by the dispatcher; "
           f"{s['notes_posted']} @grid notes posted. No human touched anything after filing.", ""]
    for issue in result["issues"]:
        if story_only and not issue["story"]:
            continue
        out += [f"## #{issue['iid']} {issue['title']}", ""]
        for e in result["events"]:
            if e["iid"] == issue["iid"]:
                out.append(f"- **{_hhmm(e['t'])}** — {e['text']}")
        out.append("")
    return "\n".join(out)
