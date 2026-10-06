"""Grid window for any GitLab pipeline: run deferrable jobs at the cleanest start before a deadline.

This is Joule Thief without Joule Thief's infrastructure — no Cloud Run, no agents — for projects
that only want their nightly matrix, fuzzing or full scans to follow the wind. A planning job
computes the cleanest start inside the deadline from the live decision signal and writes a child
pipeline: the project's own deferrable jobs, preceded by a ``.pre`` job with ``when: delayed`` and
``start_in`` set to the wait. GitLab holds the child pipeline until then; nothing else runs meanwhile.
Shipped as a CI/CD Catalog component (``templates/grid-window``).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timedelta

from .dispatch.jobs import Job
from .loop import cheapest_start
from .signals.base import Series, utc

WAIT_JOB = "grid-window:wait"
MAX_START_IN = timedelta(days=7)  # GitLab's limit for start_in


def parse_duration(text: str) -> timedelta:
    """'90m', '2h', '1h30m', '1d', or a number of minutes."""
    text = text.strip().lower().replace(" ", "")
    if text.isdigit():
        return timedelta(minutes=int(text))
    parts = re.findall(r"(\d+(?:\.\d+)?)([dhm])", text)
    if not parts or "".join(n + u for n, u in parts) != text:
        raise ValueError(f"cannot read duration {text!r}: use e.g. 45m, 2h, 1h30m or 1d")
    unit = {"d": "days", "h": "hours", "m": "minutes"}
    return sum((timedelta(**{unit[u]: float(n)}) for n, u in parts), timedelta())


@dataclass(frozen=True)
class Window:
    region: str
    now: datetime
    start: datetime
    now_g_per_kwh: float | None
    start_g_per_kwh: float
    source: str

    @property
    def wait(self) -> timedelta:
        return max(self.start - self.now, timedelta())

    @property
    def saving(self) -> float:
        if not self.now_g_per_kwh:
            return 0.0
        return max(0.0, 1 - self.start_g_per_kwh / self.now_g_per_kwh)

    def to_dict(self) -> dict:
        return {"region": self.region, "now": self.now.isoformat(), "start": self.start.isoformat(),
                "wait_minutes": round(self.wait.total_seconds() / 60),
                "now_g_per_kwh": round(self.now_g_per_kwh, 1) if self.now_g_per_kwh is not None else None,
                "start_g_per_kwh": round(self.start_g_per_kwh, 1), "saving": round(self.saving, 3), "source": self.source}


def choose(signal: Series, region: str, now: datetime, duration: timedelta, deadline: timedelta) -> Window:
    """The cleanest start that still finishes within ``deadline`` (only hours the signal already covers)."""
    now = utc(now)
    latest = min(deadline - duration, MAX_START_IN)
    job = Job("window", duration, 1.0, now, now + deadline, (region,))
    best = cheapest_start(signal, job, now, latest + duration) if latest >= timedelta() else None
    now_g = signal.value_at(now)
    if best is None:  # nothing known ahead, or no slack: run now
        return Window(region, now, now, now_g, now_g or 0.0, signal.source)
    grams, start = best
    return Window(region, now, start, now_g, grams / job.energy_kwh, signal.source)


def start_in(wait: timedelta) -> str:
    minutes = max(1, round(wait.total_seconds() / 60))
    return f"{minutes} minutes"


def child_pipeline(jobs_yaml: str, window: Window, region_label: str) -> str:
    """The project's deferrable jobs, held by a delayed ``.pre`` job until the window opens."""
    if re.search(rf"^['\"]?{re.escape(WAIT_JOB)}['\"]?\s*:", jobs_yaml, re.MULTILINE):
        raise ValueError(f"the jobs file already defines {WAIT_JOB}")
    if window.wait >= timedelta(minutes=1):
        note = (f"@grid · {region_label}: now {window.now_g_per_kwh or 0:.0f} gCO2/kWh; holding these jobs until "
                f"{window.start:%a %H:%M} UTC, {window.start_g_per_kwh:.0f} gCO2/kWh ({window.saving:.0%} less).")
    elif window.source.startswith("annual"):
        note = f"@grid · {region_label}: no live grid signal here, so these jobs run now."
    else:
        note = (f"@grid · {region_label}: running now at {window.now_g_per_kwh or 0:.0f} gCO2/kWh; nothing "
                "cleaner before the deadline.")
    lines = [f"{WAIT_JOB}:", "  stage: .pre", "  image: busybox:stable", "  variables:", "    GIT_STRATEGY: none"]
    if window.wait >= timedelta(minutes=1):
        lines += ["  when: delayed", f"  start_in: {start_in(window.wait)}"]
    lines += ["  script:", f"    - {_quote('echo ' + shlex.quote(note))}"]
    return jobs_yaml.rstrip() + "\n\n# Added by joule window: hold this pipeline until the grid window opens.\n" + "\n".join(lines) + "\n"


def _quote(text: str) -> str:
    """A YAML single-quoted scalar."""
    return "'" + text.replace("'", "''") + "'"
