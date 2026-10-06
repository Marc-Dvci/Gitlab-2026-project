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


def releasing(region: str, now_g: float, price: float | None, count: int) -> str:
    price_text = f" Day-ahead price is **{round(price, 1) or 0.0:.1f} €/MWh**" if price is not None else ""  # no "-0.0"
    surplus = " — clean power is in surplus." if price is not None and price <= 0 else "."
    return (f"**@grid · {region_label(region)}** — releasing {count} queued Surge Request(s) now: marginal ≈ "
            f"**{now_g:.0f} gCO₂/kWh**.{price_text}{surplus}")


def urgent(region: str, now_g: float, extra_g: float, cleanest_start: datetime | None = None) -> str:
    if extra_g >= 0.05 and cleanest_start is not None:
        cost = (f"waiting until {_hhmm(cleanest_start)} would have saved about **{extra_g:.1f} g**. "
                f"Logged in the ledger as the price of urgency.")
    else:
        cost = "nothing cleaner is in my forecast, so waiting would have saved nothing."
    return (f"**@grid · {region_label(region)}** — critical work never waits for me. Running now at "
            f"**{now_g:.0f} gCO₂/kWh**; {cost}")


def deferring(region: str, now_g: float, typical_g: float, horizon_h: float, deadline: datetime) -> str:
    return (f"**@grid · {region_label(region)}** — one more kWh here right now would be answered at about "
            f"**{now_g:.0f} gCO₂/kWh**, and nothing in my next {horizon_h:.0f} h beats this zone's typical "
            f"**{typical_g:.0f} gCO₂/kWh**. I'm keeping this Surge Request in the battery and will look again "
            f"every tick. Deadline {_hhmm(deadline)} is safe.")


def daily_plan(rows: list[dict], horizon_label: str) -> str:
    lines = [f"## Dispatch plan ({horizon_label})", "", "| Work | Region | Start | Expected gCO₂ |", "|---|---|---|---:|"]
    for r in rows:
        lines.append(f"| {r['job']} | {region_label(r['region'])} | {r['start']} | {r['expected_g']:.1f} |")
    return "\n".join(lines)
