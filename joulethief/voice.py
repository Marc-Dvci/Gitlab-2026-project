"""@grid — the electricity grid gets a seat at code review.

Messages are generated deterministically from data (no LLM): it is cheaper, greener,
reproducible, and the numbers in a comment are exactly the numbers in the ledger.
"""

from __future__ import annotations

from datetime import datetime

from .signals.regions import REGIONS


def _hhmm(t: datetime) -> str:
    return t.strftime("%a %H:%M UTC")


def region_label(region: str) -> str:
    r = REGIONS.get(region)
    if not r:
        return region
    zone = f", {r.price_zone} bidding zone" if r.price_zone else ""
    return f"{r.city} (`{region}`{zone})"


def holding(region: str, now_g: float, start: datetime, planned_g_per_kwh: float, saving: float, deadline: datetime,
            reason: str = "") -> str:
    why = f" {reason}" if reason else ""
    return (f"**@grid · {region_label(region)}** — one more kWh here right now would be answered at about "
            f"**{now_g:.0f} gCO₂/kWh**.{why} I'm holding this Surge Request until **{_hhmm(start)}**, when I expect "
            f"**{planned_g_per_kwh:.0f} gCO₂/kWh** (≈{saving:.0%} less). Deadline {_hhmm(deadline)} is safe.")


def releasing(region: str, now_g: float, price: float | None, count: int = 1) -> str:
    what = "this Surge Request" if count == 1 else f"{count} Surge Requests"
    price_text = ""
    if price is not None:
        price_text = f" Day-ahead price is **{price:.1f} €/MWh**" + (": clean power is in surplus." if price <= 0 else ".")
    return (f"**@grid · {region_label(region)}** — releasing {what} now: one more kWh here is answered at about "
            f"**{now_g:.0f} gCO₂/kWh**, the best slot I can find before its deadline.{price_text}")


def urgent(region: str, now_g: float, extra_g: float, best_at: datetime | None = None) -> str:
    if extra_g >= 0.05 and best_at is not None:
        cost = f"waiting until {_hhmm(best_at)} would have saved about {extra_g:.1f} g. That's the price of urgency"
    else:
        cost = "waiting would not have been cleaner"
    return (f"**@grid · {region_label(region)}** — critical work never waits for me. Running now at "
            f"**{now_g:.0f} gCO₂/kWh**; {cost}, and it's in the ledger.")


def deferring(region: str, now_g: float, typical_g: float, deadline: datetime) -> str:
    return (f"**@grid · {region_label(region)}** — one more kWh here right now would be answered at about "
            f"**{now_g:.0f} gCO₂/kWh**, and none of the hours I can see yet comes close to a good hour here "
            f"(≈{typical_g:.0f}, the cleanest tenth of the past week). I'm holding this Surge Request until I can see further ahead (the next day-ahead "
            f"prices or forecast). Deadline {_hhmm(deadline)} is safe.")


def daily_plan(rows: list[dict], horizon_label: str) -> str:
    lines = [f"## Dispatch plan ({horizon_label})", "", "| Work | Region | Start | Expected gCO₂ |", "|---|---|---|---:|"]
    for r in rows:
        lines.append(f"| {r['job']} | {region_label(r['region'])} | {r['start']} | {r['expected_g']:.1f} |")
    return "\n".join(lines)


ENERGY_CHECK_MARKER = "<!-- joule:energy-check -->"


def _range(d: dict | None, digits: int = 2) -> str:
    if not d:
        return "—"
    return f"{d['likely']:.{digits}f} ({d['low']:.{digits}f}–{d['high']:.{digits}f})"


def energy_check(gate, target_branch: str, reviewer: str) -> str:
    """MR note from the energy gate: a table always, an LLM reviewer only when the numbers call for one."""
    lines = [ENERGY_CHECK_MARKER, f"**@grid · energy check** — joules per request, this merge request vs `{target_branch}`:", "",
             "| Endpoint | " + f"`{target_branch}`" + " | This MR | Change | Projected gCO₂e/day |", "|---|---:|---:|---:|---:|"]
    for d in gate.deltas:
        base = f"{d.base_j:.4f}" if d.base_j is not None else "new"
        change = f"{d.change:+.0%}" if d.change is not None else "—"
        lines.append(f"| `{d.endpoint}` | {base} | {d.head_j:.4f} | {change} | {d.g_per_day:+.3f} |")
    if gate.hot_lines:
        hot = ", ".join(f"`{h['file']}:{h['line']}` ({h['g_per_day']:.3f} g/day)" for h in gate.hot_lines)
        lines += ["", f"This MR edits the service's hottest lines: {hot}."]
    lines.append("")
    if gate.needs_reviewer:
        lines.append(f"Worth a closer look: {'; '.join(gate.reasons)}. {reviewer}")
    else:
        lines.append("No material energy change: no LLM review needed for this one.")
    return "\n".join(lines)


def shipped_marker(sha: str) -> str:
    return f"<!-- joule:shipped:{sha} -->"


def shipped(mr_ref: str, sha: str, region: str, deployed: bool, footprint: dict, receipt: dict | None,
            canary: dict | None, tag: str = "") -> str:
    """The closing note on an issue, from the pipeline's own artifacts (numbers verbatim, ranges kept)."""
    where = f"is live in {region_label(region)}" + (f" as `{tag}`" if tag else "") if deployed else "is merged (not deployed)"
    lines = [shipped_marker(sha), f"**@grid · Shipped** — {mr_ref} (`{sha[:8]}`) {where}. What it cost, likely (low–high):", "",
             "| | Value |", "|---|---:|",
             f"| Pipeline energy (kWh) | {_range(footprint.get('energy_kwh'), 4)} |",
             f"| Attributional gCO₂e (location-based) | {_range(footprint.get('attributional_g'))} |",
             f"| Consequential gCO₂e (marginal) | {_range(footprint.get('consequential_g'))} |"]
    agents = (receipt or {}).get("agents") or {}
    if agents.get("gwp_g"):
        lines.append(f"| Agents' own gCO₂e (SCI for AI) | {_range(agents['gwp_g'], 3)} |")
    lines.append(f"| Jobs accounted (retries included) | {footprint.get('entries', 0)} |")
    if canary and canary.get("canary_j_per_request"):
        prod = canary.get("prod_j_per_request", {})
        parts = [f"`{ep}` {j:.4f} J vs {prod[ep]:.4f} in production ({j / prod[ep] - 1:+.0%})"
                 for ep, j in sorted(canary["canary_j_per_request"].items()) if prod.get(ep)]
        if parts:
            lines += ["", "Canary energy per request: " + "; ".join(parts) + "."]
    if receipt:
        b = receipt.get("budget", {})
        lines += ["", f"Carbon receipt: **{receipt.get('verdict', '?')}** ({b.get('spentG', 0):.1f} of {b.get('capG', 0):.0f} g "
                  f"used in {b.get('period', 'this period')}); signed with Sigstore, check it with `cosign verify-attestation`."]
    return "\n".join(lines)
