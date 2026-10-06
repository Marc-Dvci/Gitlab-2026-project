"""Carbon blame: ``git blame`` for grams of CO2.

Turns profiler samples into joules per request per source line, scales them by real
traffic and the grid's intensity into grams per day, and ties each line to the commit
and merge request that introduced it. The same arithmetic projects a merge request's
production impact from a benchmark: Δ joules/request × requests/day × intensity.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..carbon.power import CloudPowerModel

J_PER_KWH = 3.6e6


@dataclass
class LineCost:
    endpoint: str
    file: str
    line: int
    function: str
    share: float  # of the endpoint's sampled CPU time
    joules_per_request: float
    g_per_day: float
    commit: str = ""
    author: str = ""
    summary: str = ""


def joules_per_cpu_second(power: CloudPowerModel | None = None) -> float:
    power = power or CloudPowerModel()
    return power.watts_per_vcpu(1.0).likely * power.pue.likely


def attribute(snapshot: dict, requests_per_day: dict[str, float], intensity_g_per_kwh: float,
              power: CloudPowerModel | None = None, min_share: float = 0.01) -> list[LineCost]:
    jps = joules_per_cpu_second(power)
    totals: dict[str, int] = {}
    for s in snapshot["samples"]:
        totals[s["endpoint"]] = totals.get(s["endpoint"], 0) + s["count"]
    out = []
    for s in snapshot["samples"]:
        ep = snapshot["endpoints"].get(s["endpoint"])
        if not ep or not ep["requests"] or not totals.get(s["endpoint"]):
            continue
        share = s["count"] / totals[s["endpoint"]]
        if share < min_share:
            continue
        j_req = share * ep["cpu_seconds"] / ep["requests"] * jps
        g_day = j_req / J_PER_KWH * intensity_g_per_kwh * requests_per_day.get(s["endpoint"], 0.0)
        out.append(LineCost(s["endpoint"], s["file"], s["line"], s["function"], share, j_req, g_day))
    out.sort(key=lambda c: c.g_per_day, reverse=True)
    return out


def git_blame(repo: Path, file: str, line: int) -> tuple[str, str, str]:
    """(short commit, author, summary) for one line, or empty strings outside a git checkout."""
    try:
        raw = subprocess.run(["git", "-C", str(repo), "blame", "-L", f"{line},{line}", "--porcelain", "--", file],
                             capture_output=True, text=True, check=True, timeout=10).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return "", "", ""
    lines = raw.splitlines()
    if not lines:
        return "", "", ""
    commit = lines[0].split()[0][:8]
    meta = dict(entry.split(" ", 1) for entry in lines[1:] if " " in entry and not entry.startswith("\t"))
    return commit, meta.get("author", ""), meta.get("summary", "")


def with_blame(costs: list[LineCost], repo: Path) -> list[LineCost]:
    for c in costs:
        c.commit, c.author, c.summary = git_blame(repo, c.file, c.line)
    return costs


def mr_delta_g_per_day(base_j_per_request: float, head_j_per_request: float, requests_per_day: float,
                       intensity_g_per_kwh: float) -> float:
    return (head_j_per_request - base_j_per_request) / J_PER_KWH * intensity_g_per_kwh * requests_per_day


def render_markdown(costs: list[LineCost], top: int = 10, intensity_label: str = "") -> str:
    rows = ["| gCO2e/day | J/request | Endpoint | Line | Function | Commit | Author |",
            "|---:|---:|---|---|---|---|---|"]
    for c in costs[:top]:
        rows.append(f"| {c.g_per_day:.3f} | {c.joules_per_request:.4f} | `{c.endpoint}` | `{c.file}:{c.line}` | "
                    f"`{c.function}` | {c.commit or '—'} | {c.author or '—'} |")
    head = "### Carbon blame — where this service's emissions come from\n\n"
    if intensity_label:
        head += f"Scaled by current traffic and {intensity_label}.\n\n"
    return head + "\n".join(rows) + "\n"
