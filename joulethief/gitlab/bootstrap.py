"""``joule bootstrap`` — prepare a GitLab project for Joule Thief in one idempotent command.

Creates what the hands-off loop relies on, and skips whatever already exists:
  * the scoped labels (``surge::*``, ``priority::*`` with their service levels, ``energy::*``);
  * the ``eco-mode`` feature flag (off; the ``eco`` schedule flips it from the grid signal);
  * pipeline schedules for the dispatcher tick, the daily plan and eco-mode;
  * with ``--service-url``, an issue-events webhook to ``/api/webhook/gitlab``, so a new or
    critical Surge Request is planned within seconds instead of at the next 30-minute heartbeat.

Run it once with a Maintainer token (webhooks need Maintainer); the loop itself needs only Developer.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..dispatch.jobs import PRIORITY_SLA
from .client import GitLab

SURGE_LABELS = (
    ("surge::queued", "#6699cc", "Deferrable work waiting for a clean-power window (set by Surge Intake)."),
    ("surge::scheduled", "#5843ad", "Held by @grid: a cleaner window is planned or awaited."),
    ("surge::running", "#1f7a4d", "Released by the dispatcher: an agent flow or pipeline is working on it."),
    ("surge::plan", "#8fbc8f", "A dispatch plan published by the grid."),
    ("surge::now", "#cc0033", "Run now, whatever the grid says."),
)
PRIORITY_COLORS = {"critical": "#cc0033", "high": "#ed9121", "normal": "#6699cc", "low": "#a8d695"}
ENERGY_LABELS = (
    ("energy::agent_session", "Code change by an agent (Surge Worker flow)."),
    ("energy::ci_pipeline", "Heavy test runs (deferred pipeline, JOULE_TASK=heavy-tests)."),
    ("energy::security_scan", "DAST, fuzzing and full scans (deferred pipeline, JOULE_TASK=heavy-scan)."),
    ("energy::dependency_upgrade", "Dependency upgrades by an agent."),
)
SCHEDULES = (  # (description, cron UTC, JOULE_TASK)
    ("Joule Thief: dispatcher tick", "*/30 * * * *", "tick"),
    ("Joule Thief: daily dispatch plan", "0 13 * * *", "plan"),  # after European day-ahead publication
    ("Joule Thief: eco-mode", "15 * * * *", "eco"),
)
WEBHOOK_PATH = "/api/webhook/gitlab"


def labels() -> list[tuple[str, str, str]]:
    out = list(SURGE_LABELS)
    for level, sla in PRIORITY_SLA.items():
        hours = sla.total_seconds() / 3600
        when = "runs immediately; the grid never delays it" if not hours else f"starts within {hours:.0f} h, in the cleanest window"
        out.append((f"priority::{level}", PRIORITY_COLORS[level], f"Service level: {when}."))
    out += [(name, "#1f7a4d", description) for name, description in ENERGY_LABELS]
    return out


@dataclass
class Bootstrap:
    gitlab: GitLab
    ref: str = "main"
    tick_schedule: bool = True  # off when Cloud Scheduler already ticks /api/tick
    service_url: str = ""
    tick_key: str = ""
    dry_run: bool = False

    def run(self) -> list[str]:
        """Return one line per action: ``create …`` or ``exists …`` (``would create …`` in a dry run)."""
        log: list[str] = []
        p = self.gitlab._project_path

        have = set() if self.dry_run else {x["name"] for x in self._all(f"{p}/labels", include_ancestor_groups="true")}
        for name, color, description in labels():
            self._ensure(log, "label", name, name in have,
                         lambda n=name, c=color, d=description: self.gitlab.request(
                             "POST", f"{p}/labels", {"name": n, "color": c, "description": d}))

        flags = set() if self.dry_run else {x["name"] for x in self._all(f"{p}/feature_flags")}
        self._ensure(log, "feature flag", "eco-mode", "eco-mode" in flags, lambda: self.gitlab.request(
            "POST", f"{p}/feature_flags",
            {"name": "eco-mode", "version": "new_version_flag", "active": False,
             "description": "Demand shaping: on when the grid is dirty (longer caches, profiler off).",
             "strategies": [{"name": "default", "parameters": {}, "scopes": [{"environment_scope": "*"}]}]}))

        schedules = set() if self.dry_run else {x["description"] for x in self._all(f"{p}/pipeline_schedules")}
        for description, cron, task in SCHEDULES:
            if task == "tick" and not self.tick_schedule:
                continue
            self._ensure(log, "schedule", f"{description} ({cron} UTC)", description in schedules,
                         lambda d=description, c=cron, t=task: self._schedule(d, c, t))

        if self.service_url:
            url = self.service_url.rstrip("/") + WEBHOOK_PATH
            hooks = set() if self.dry_run else {x["url"] for x in self._all(f"{p}/hooks")}
            self._ensure(log, "webhook", f"issue events → {url}", url in hooks, lambda: self.gitlab.request(
                "POST", f"{p}/hooks", {"url": url, "token": self.tick_key, "issues_events": True,
                                       "push_events": False, "enable_ssl_verification": True}))
        return log

    def _ensure(self, log: list[str], kind: str, name: str, exists: bool, create) -> None:
        if exists:
            log.append(f"exists  {kind}: {name}")
        elif self.dry_run:
            log.append(f"would create  {kind}: {name}")
        else:
            create()
            log.append(f"create  {kind}: {name}")

    def _schedule(self, description: str, cron: str, task: str) -> None:
        p = self.gitlab._project_path
        sched = self.gitlab.request("POST", f"{p}/pipeline_schedules", {
            "description": description, "ref": self.ref, "cron": cron, "cron_timezone": "UTC", "active": True})
        self.gitlab.request("POST", f"{p}/pipeline_schedules/{sched['id']}/variables", {"key": "JOULE_TASK", "value": task})

    def _all(self, path: str, **query: str) -> list[dict]:
        out, page = [], 1
        while True:
            batch = self.gitlab.request("GET", path, query={"per_page": 100, "page": page, **query}) or []
            out += batch
            if len(batch) < 100:
                return out
            page += 1
