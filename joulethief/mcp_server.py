"""Joule Thief MCP server: grid signals, dispatch planning and footprint tools for any agent.

GitLab Duo (via ``.gitlab/duo/mcp.json``), Claude Code and other MCP clients can call it
over streamable HTTP. Tools are deterministic and cheap; the LLM decides, the tools count.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .carbon.llm import AgentCall, agent_footprint
from .dispatch.jobs import PRIORITY_SLA, Job
from .dispatch.optimizer import plan
from .live import LiveSignals
from .receipts.intoto import verify
from .signals.marginal import surplus_windows
from .signals.regions import REGIONS, google_region_carbon

RESULTS = Path(__file__).resolve().parents[1] / "docs" / "results" / "autonomy_dividend.json"

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]

server = _Server(
    name="joule-thief",
    instructions=(
        "Grid-aware tools for the post-code lifecycle. Before scheduling deferrable work, call grid_signal or "
        "plan_work; never assume the cleanest hour from averages. Report footprints as ranges."
    ),
)
_signals = LiveSignals()


def _summary(series, hours: int) -> dict:
    now = datetime.now(timezone.utc)
    window = series.slice(now - timedelta(hours=1), now + timedelta(hours=hours))
    pts = list(window)
    if not pts:
        return {"error": "no data in window"}
    best = min(pts, key=lambda p: p.value)
    return {
        "metric": series.metric, "unit": series.unit, "source": series.source,
        "now": series.value_at(now), "min": best.value, "cleanest_start": best.start.isoformat(),
        "max": max(p.value for p in pts), "points": len(pts),
    }


@server.tool()
def grid_signal(region: str, hours: int = 24) -> dict:
    """Decision signal (gCO2/kWh of one more kWh) for a Google Cloud region over the next hours, with the
    cleanest slot and any surplus (price <= 0) windows."""
    if region not in REGIONS:
        return {"error": f"unknown region {region}", "known": sorted(REGIONS)}
    series = _signals.decision_signal(region, datetime.now(timezone.utc))
    out = {"region": region, **_summary(series, hours)}
    zone = REGIONS[region].price_zone
    if zone:
        prices = _signals.prices(zone, datetime.now(timezone.utc))
        out["surplus_windows"] = [{"start": s.isoformat(), "end": e.isoformat(), "min_price": m}
                                  for s, e, m in surplus_windows(prices)]
    return out


@server.tool()
def plan_work(jobs: list[dict], regions: list[str], horizon_hours: int = 36, capacity: int = 3) -> dict:
    """Plan deferrable jobs. Each job: {id, minutes, power_kw, priority (critical|high|normal|low)}.
    Returns start time and region per job, expected grams and the run-now baseline."""
    now = datetime.now(timezone.utc)
    js = [Job(str(j["id"]), timedelta(minutes=float(j.get("minutes", 30))), float(j.get("power_kw", 0.3)), now,
              now + PRIORITY_SLA.get(j.get("priority", "normal"), PRIORITY_SLA["normal"]) +
              timedelta(minutes=float(j.get("minutes", 30))), tuple(regions), priority=j.get("priority", "normal"))
          for j in jobs]
    signals = {r: _signals.decision_signal(r, now) for r in regions}
    return plan(js, signals, now, timedelta(hours=horizon_hours), capacity=capacity).to_dict()


@server.tool()
def estimate_agent_footprint(provider: str, model: str, input_tokens: int, output_tokens: int,
                             latency_s: float | None = None, electricity_zone: str | None = None,
                             functional_units: float = 1.0) -> dict:
    """Energy, carbon and water of LLM calls (EcoLogits ranges), with SCI-for-AI per functional unit."""
    fp = agent_footprint([AgentCall(provider, model, input_tokens, output_tokens, latency_s)], electricity_zone)
    return {**fp.to_dict(), "sci_for_ai": fp.sci_for_ai(functional_units)}


@server.tool()
def explain_region(region: str) -> dict:
    """Average (attributional) vs marginal (consequential) view of a region, and why it matters."""
    rc = google_region_carbon().get(region)
    info = REGIONS.get(region)
    return {
        "region": region,
        "google_cfe": rc.google_cfe if rc else None,
        "grid_intensity_avg_g_per_kwh": rc.grid_intensity_avg if rc else None,
        "signal_used_for_decisions": info.intensity_source if info else "annual",
        "notes": info.notes if info else "",
        "why": ("Average intensity says how clean the electricity *is*; marginal intensity says what one more kWh "
                "*causes*. Decisions use the marginal view; reports show both."),
    }


@server.tool()
def check_carbon_receipt(statement_json: str, expected_digest: str | None = None) -> dict:
    """Content checks for a (cosign-verified) carbon receipt: budget, ranges, freshness, subject digest."""
    problems = verify(json.loads(statement_json), expected_digest)
    return {"ok": not problems, "problems": problems}


@server.tool()
def autonomy_dividend() -> dict:
    """Measured carbon dividend of hands-off vs supervised autonomy on real grid data."""
    if not RESULTS.exists():
        return {"error": "run experiments/autonomy_dividend.py first"}
    return json.loads(RESULTS.read_text())


def http_app():
    """Streamable-HTTP ASGI app (stateless, JSON responses) for mounting under /mcp."""
    try:
        from mcp.server.transport_security import TransportSecuritySettings

        return server.streamable_http_app(
            streamable_http_path="/mcp", stateless_http=True, json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    except TypeError:  # mcp 1.x signature
        return server.streamable_http_app()


if __name__ == "__main__":
    server.run("stdio")
