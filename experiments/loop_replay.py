"""The hands-off loop, replayed on a real week of the Spanish grid.

This is not a model of the loop: it *is* the loop. ``joulethief.loop.tick`` — the function the
Cloud Run service calls every 30 minutes and on every new Surge Request (GitLab webhook) — runs
unchanged against an in-memory GitLab, on the
day-ahead prices OMIE actually published for 12–18 May 2025 (only after each day's ~13:00 CET
publication, as live). Fifteen realistic issues are filed during working hours, already
labelled the way the Surge Request template and Surge Intake label them. Every @grid note,
label change, flow start and pipeline start the loop makes is recorded.

Emissions use the price→marginal heuristic of METHODOLOGY.md §3 (same parameters as the autonomy
experiment); "if run on filing" is the same work started the moment the issue was filed.

Run:  python experiments/loop_replay.py   (seconds; writes docs/results/loop_replay.{json,md})
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from autonomy_dividend import es_forecast_fn  # noqa: E402

from joulethief.dispatch.jobs import PRIORITY_SLA, priority_from_labels  # noqa: E402
from joulethief.loop import JOB_PROFILES, QUEUED, RUNNING, SCHEDULED, LoopConfig, kind_of, publish_plan, tick  # noqa: E402
from joulethief.signals.base import Series  # noqa: E402
from joulethief.signals.marginal import PriceMarginalModel, surplus_windows  # noqa: E402
from joulethief.signals.snapshots import es_prices  # noqa: E402

UTC = timezone.utc
MADRID = ZoneInfo("Europe/Madrid")
OUT = ROOT / "docs" / "results"
REGION = "europe-southwest1"
WEEK = datetime(2025, 5, 12, tzinfo=MADRID)  # Monday
DAYS = 9  # issues are filed Monday–Friday; the replay runs on until the last deadline
TICK = timedelta(minutes=30)

# (day offset, local time, title, priority, kind) — the kind of backlog this repository has.
ISSUES = [
    (0, "09:40", "Upgrade FastAPI and uvicorn to the latest patch releases", "low", "dependency_upgrade"),
    (0, "11:15", "Dashboard comparison is slow", "low", "agent_session"),
    (0, "15:30", "Run the full test matrix on Python 3.11–3.13", "normal", "ci_pipeline"),
    (1, "10:05", "Nightly DAST scan of the control room", "low", "security_scan"),
    (1, "13:20", "Retry Open-Meteo with backoff", "normal", "agent_session"),
    (1, "17:45", "Bump ortools to 9.15.x", "low", "dependency_upgrade"),
    (2, "08:50", "Production: /api/grid returns 500 for europe-west2", "critical", "agent_session"),
    (2, "12:30", "Fuzz the receipt verifier", "low", "security_scan"),
    (2, "16:10", "Rerun the autonomy experiment on September data", "low", "ci_pipeline"),
    (3, "09:30", "Cache region metadata between ticks", "normal", "agent_session"),
    (3, "14:00", "Container scan with the full vulnerability database", "normal", "security_scan"),
    (3, "17:30", "Upgrade mcp to 2.4", "normal", "dependency_upgrade"),
    (4, "10:20", "Document the price-knee sensitivity", "low", "agent_session"),
    (4, "15:45", "Load-test the canary", "high", "ci_pipeline"),
    (4, "17:50", "Refresh pinned dev dependencies", "low", "dependency_upgrade"),
]


class ReplayGitLab:
    """The slice of the GitLab API the loop uses, in memory, with a log of everything it is asked to do."""

    def __init__(self):
        self.issues_by_iid: dict[int, dict] = {}
        self.events: list[dict] = []
        self.now: datetime = WEEK.astimezone(UTC)
        self.plans: list[dict] = []

    def log(self, kind: str, iid: int | None, **data) -> None:
        self.events.append({"t": self.now.isoformat(), "kind": kind, "iid": iid, **data})

    def file(self, iid: int, title: str, labels: list[str]) -> None:
        self.issues_by_iid[iid] = {"iid": iid, "title": title, "labels": list(labels), "state": "opened",
                                   "created_at": self.now.isoformat()}
        self.log("filed", iid, title=title, labels=list(labels))

    # -- the API the loop calls ---------------------------------------------------------------
    def issues(self, labels: list[str], state: str = "opened") -> list[dict]:
        return [dict(i, labels=list(i["labels"])) for i in self.issues_by_iid.values()
                if i["state"] == state and all(label in i["labels"] for label in labels)]

    def issue_note(self, iid: int, body: str) -> dict:
        self.log("note", iid, body=body)
        return {}

    def set_labels(self, iid: int, add=(), remove=()) -> dict:
        labels = self.issues_by_iid[iid]["labels"]
        labels[:] = [label for label in labels if label not in remove] + [label for label in add if label not in labels]
        self.log("labels", iid, add=list(add), remove=list(remove))
        return {}

    def start_flow(self, goal: str, **kw) -> dict:
        self.log("flow", kw.get("issue_iid"), goal=goal)
        return {"id": len(self.events)}

    def run_pipeline(self, ref: str, variables: dict[str, str]) -> dict:
        self.log("pipeline", int(variables["JOULE_ISSUE"]), variables=variables)
        return {"id": len(self.events)}

    def create_issue(self, title: str, description: str, labels: list[str]) -> dict:
        self.plans.append({"t": self.now.isoformat(), "title": title, "body": description})
        self.log("plan", None, title=title)
        return {}

    def close(self, iid: int) -> None:
        issue = self.issues_by_iid[iid]
        issue["state"] = "closed"
        issue["labels"] = [label for label in issue["labels"] if label != RUNNING]


class ReplaySignals:
    def __init__(self, marginal: Series):
        self.forecast = es_forecast_fn(marginal)

    def decision_signal(self, region: str, now: datetime) -> Series:
        return self.forecast(region, now)


def grams(series: Series, start: datetime, duration: timedelta, power_kw: float) -> float:
    steps = max(1, int(duration / TICK + 0.999))
    per_slot = power_kw * duration.total_seconds() / 3600 / steps
    return sum(per_slot * (series.value_at(start + k * TICK + TICK / 2) or series.mean()) for k in range(steps))


def replay(week: datetime | None = None) -> dict:
    global WEEK
    WEEK = week or WEEK
    prices = es_prices()
    marginal = PriceMarginalModel(fossil_margin_g=490.0, fossil_price=40.0).series(prices)
    gl, signals = ReplayGitLab(), ReplaySignals(marginal)
    cfg = LoopConfig(regions=(REGION,), flow_consumer_id=1, tick=TICK)
    start, end = WEEK.astimezone(UTC), (WEEK + timedelta(days=DAYS)).astimezone(UTC)
    filing = sorted(((WEEK + timedelta(days=d)).replace(hour=int(hm[:2]), minute=int(hm[3:])).astimezone(UTC), title, prio, kind)
                    for d, hm, title, prio, kind in ISSUES)
    started: dict[int, datetime] = {}
    done: dict[int, dict] = {}
    ticks = []
    # Scheduled ticks every 30 minutes, plus a webhook tick the moment each issue is filed.
    moments = sorted([(start + k * TICK, None) for k in range(int((end - start) / TICK))] + [(f[0], f) for f in filing],
                     key=lambda m: (m[0], m[1] is None))
    for now, filed_issue in moments:
        gl.now = now
        if filed_issue:
            _, title, prio, kind = filed_issue
            gl.file(len(gl.issues_by_iid) + 1, title, [f"priority::{prio}", f"energy::{kind}", QUEUED])
            gl.log("webhook", len(gl.issues_by_iid))
        report = tick(gl, signals, cfg, now)
        local = now.astimezone(MADRID)
        if not filed_issue and local.hour == 13 and local.minute == 30:  # after the day-ahead publication
            publish_plan(gl, report)
        for job_id in report.started:
            started[int(job_id.lstrip("#"))] = now
        for iid, t0 in list(started.items()):
            issue = gl.issues_by_iid[iid]
            kind = kind_of(issue["labels"])
            duration, power = JOB_PROFILES[kind]
            if iid not in done and t0 + duration <= now + TICK:
                filed = datetime.fromisoformat(issue["created_at"])
                g, g_now = grams(marginal, t0, duration, power), grams(marginal, filed, duration, power)
                deadline = filed + PRIORITY_SLA[priority_from_labels(issue["labels"])] + duration
                done[iid] = {"finished": (t0 + duration).isoformat(), "g": round(g, 2), "g_if_run_on_filing": round(g_now, 2),
                             "late": t0 + duration > deadline + timedelta(minutes=1)}
                gl.now = t0 + duration
                gl.close(iid)
                gl.log("done", iid, g=round(g, 2), g_if_run_on_filing=round(g_now, 2))
                gl.now = now
        if filed_issue:
            continue
        open_issues = [i for i in gl.issues_by_iid.values() if i["state"] == "opened"]
        pending = [i for i in open_issues if QUEUED in i["labels"] or SCHEDULED in i["labels"]]
        ticks.append({"t": now.isoformat(), "g_per_kwh": marginal.value_at(now), "price": prices.value_at(now),
                      "pending_kwh": round(sum(JOB_PROFILES[kind_of(i["labels"])][0].total_seconds() / 3600
                                               * JOB_PROFILES[kind_of(i["labels"])][1] for i in pending), 3),
                      "queued": len(pending), "running": sum(1 for i in open_issues if RUNNING in i["labels"])})
    gl.events.sort(key=lambda e: e["t"])

    issues = []
    for iid, issue in sorted(gl.issues_by_iid.items()):
        kind = kind_of(issue["labels"])
        duration, power = JOB_PROFILES[kind]
        notes = [e["body"] for e in gl.events if e["iid"] == iid and e["kind"] == "note"]
        issues.append({"iid": iid, "title": issue["title"], "kind": kind, "priority": priority_from_labels(issue["labels"]),
                       "filed": issue["created_at"], "started": started[iid].isoformat() if iid in started else None,
                       "energy_kwh": round(duration.total_seconds() / 3600 * power, 3),
                       "wait_h": round((started[iid] - datetime.fromisoformat(issue["created_at"])).total_seconds() / 3600, 2)
                       if iid in started else None,
                       **done.get(iid, {}), "notes": notes,
                       "started_by": next((e["kind"] for e in gl.events if e["iid"] == iid and e["kind"] in ("flow", "pipeline")), None)})
    g = sum(i.get("g", 0.0) for i in issues)
    g0 = sum(i.get("g_if_run_on_filing", 0.0) for i in issues)
    window = prices.slice(start, end)
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "region": REGION, "start": start.isoformat(), "end": end.isoformat(),
        "signal": {"metric": marginal.metric, "unit": marginal.unit, "source": prices.source,
                   "model": marginal.notes},
        "surplus_windows": [{"start": s.isoformat(), "end": e.isoformat(), "min_price": m}
                            for s, e, m in surplus_windows(window)],
        "ticks": ticks, "issues": issues, "plans": gl.plans,
        "totals": {"issues": len(issues), "finished": len(done), "late": sum(1 for d in done.values() if d["late"]),
                   "g": round(g, 1), "g_if_run_on_filing": round(g0, 1), "saving": round(1 - g / g0, 4) if g0 else 0.0,
                   "notes": sum(1 for e in gl.events if e["kind"] == "note"),
                   "flows_started": sum(1 for e in gl.events if e["kind"] == "flow"),
                   "pipelines_started": sum(1 for e in gl.events if e["kind"] == "pipeline"),
                   "ticks": len(ticks), "webhook_ticks": sum(1 for e in gl.events if e["kind"] == "webhook"),
                   "llm_calls_by_loop": 0},
        "events": gl.events,
    }


def render(r: dict) -> str:
    t = r["totals"]
    local = lambda iso: datetime.fromisoformat(iso).astimezone(MADRID).strftime("%a %d %b %H:%M")  # noqa: E731
    lines = ["# The hands-off loop, replayed on a real week (generated)", "",
             f"Generated {r['generated']} by `experiments/loop_replay.py`: `joulethief.loop.tick` every 30 minutes, "
             f"unchanged (plus a webhook tick when an issue is filed), against an in-memory GitLab, on OMIE day-ahead prices for {local(r['start'])} – "
             f"{local(r['end'])} (Madrid time; prices revealed only after each day's publication).", "",
             f"**{t['issues']} issues, {t['finished']} finished, {t['late']} late. {t['g']:.0f} gCO₂e versus "
             f"{t['g_if_run_on_filing']:.0f} g if each had run the moment it was filed ({-t['saving']:+.0%}).** "
             f"{t['notes']} @grid notes, {t['flows_started']} Duo flows and {t['pipelines_started']} pipelines started "
             f"by the loop; {t['ticks']} scheduled ticks and {t['webhook_ticks']} webhook ticks; the loop itself made "
             f"{t['llm_calls_by_loop']} LLM calls.", "",
             "| # | Issue | Priority | Kind | Filed | Started | Waited (h) | g | g if run on filing |",
             "|---:|---|---|---|---|---|---:|---:|---:|"]
    for i in r["issues"]:
        lines.append(f"| {i['iid']} | {i['title']} | {i['priority']} | {i['kind']} | {local(i['filed'])} | "
                     f"{local(i['started']) if i['started'] else '—'} | {i['wait_h'] if i['wait_h'] is not None else '—'} | "
                     f"{i.get('g', '—')} | {i.get('g_if_run_on_filing', '—')} |")
    lines += ["", "## What the grid said (transcript)", "", "Times in bold are Madrid local time; @grid writes UTC.", ""]
    titles = {i["iid"]: i["title"] for i in r["issues"]}
    for e in r["events"]:
        when = local(e["t"])
        if e["kind"] == "filed":
            lines.append(f"- **{when}** · #{e['iid']} *{e['title']}* filed with " + ", ".join(f"`{x}`" for x in e["labels"]))
        elif e["kind"] == "note":
            lines.append(f"  - {when} · on #{e['iid']}: {e['body']}")
        elif e["kind"] in ("flow", "pipeline"):
            what = "Surge Worker flow started (Flows API)" if e["kind"] == "flow" else \
                f"pipeline `JOULE_TASK={e['variables']['JOULE_TASK']}` started"
            lines.append(f"  - {when} · #{e['iid']}: {what}")
        elif e["kind"] == "done":
            lines.append(f"  - {when} · #{e['iid']} *{titles[e['iid']]}* done: {e['g']} g "
                         f"(if run on filing: {e['g_if_run_on_filing']} g)")
        elif e["kind"] == "plan":
            lines.append(f"- **{when}** · dispatch plan published: *{e['title']}*")
    if r.get("other_weeks"):
        lines += ["", "## The same backlog on other weeks", "",
                  "The week above was chosen before running it (the second-most surplus hours in the data, and not the "
                  "week of the 28 April blackout). Here is the same backlog on the first full week of every month, so "
                  "the spread is visible. The total moves mostly with where the one critical incident lands: it runs "
                  "at once, whatever the grid.", "",
                  "| Week of | Surplus hours | @grid holds | Late | g | g if run on filing | Saving |", "|---|---:|---:|---:|---:|---:|---:|"]
        for w in r["other_weeks"]:
            lines.append(f"| {w['week']} | {w['surplus_hours']:.0f} | {w['holds']} | {w['late']} | {w['g']:.0f} | "
                         f"{w['g_if_run_on_filing']:.0f} | {-w['saving']:+.0%} |")
    return "\n".join(lines) + "\n"


def other_weeks() -> list[dict]:
    """The same backlog on the first full week of every month in the data: the spread, not a chosen number."""
    chosen, out = WEEK, []
    for month in range(3, 10):
        first = datetime(2025, month, 1, tzinfo=MADRID)
        monday = first + timedelta(days=(7 - first.weekday()) % 7)
        r = replay(monday)
        t = r["totals"]
        out.append({"week": monday.date().isoformat(), "saving": t["saving"], "late": t["late"], "g": t["g"],
                    "g_if_run_on_filing": t["g_if_run_on_filing"],
                    "holds": sum(1 for e in r["events"] if e["kind"] == "note" and "holding" in e["body"]),
                    "surplus_hours": sum(1 for k in r["ticks"] if (k["price"] if k["price"] is not None else 1) <= 0) / 2})
    replay(chosen)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    weeks = other_weeks()
    r = replay()
    r["other_weeks"] = weeks
    (OUT / "loop_replay.json").write_text(json.dumps(r, indent=1, default=str))
    (OUT / "loop_replay.md").write_text(render(r))
    print(render(r))


if __name__ == "__main__":
    main()
