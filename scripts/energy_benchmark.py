"""Verify-stage energy benchmark: joules per request per endpoint, and carbon blame per line.

Writes:
  metrics.txt        GitLab metrics report (the MR widget diffs it against the target branch)
  carbon-blame.md    top source lines by projected gCO2e/day, with commit and author
  benchmark.json     raw numbers for the ledger and the carbon reviewer agent
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, profiler  # noqa: E402
from joulethief.blame import attribute, render_markdown, with_blame  # noqa: E402
from joulethief.blame.attribution import joules_per_cpu_second  # noqa: E402

# Representative traffic (requests/day) — replace with production numbers from monitoring.
TRAFFIC = {"/api/compare": float(os.environ.get("JOULE_TRAFFIC_COMPARE", 2000)),
           "/api/grid": float(os.environ.get("JOULE_TRAFFIC_GRID", 20000))}
INTENSITY = float(os.environ.get("JOULE_BENCH_INTENSITY", 40))  # europe-north1 location-based ≈ 39 g/kWh
REQUESTS = int(os.environ.get("JOULE_BENCH_REQUESTS", 5))


def main() -> None:
    with TestClient(app) as client:
        for _ in range(REQUESTS):
            client.get("/api/compare")
            client.get("/api/grid/europe-southwest1")
        time.sleep(0.05)
    snap = profiler.snapshot()
    jps = joules_per_cpu_second()
    endpoints = {ep: {"requests": v["requests"], "cpu_s_per_request": v["cpu_seconds"] / max(v["requests"], 1),
                      "joules_per_request": v["cpu_seconds"] / max(v["requests"], 1) * jps}
                 for ep, v in snap["endpoints"].items()}
    costs = with_blame(attribute(snap, TRAFFIC, INTENSITY), ROOT)
    metrics = [f"energy_joules_per_request{{endpoint=\"{ep}\"}} {v['joules_per_request']:.4f}" for ep, v in endpoints.items()]
    projected = sum(v["joules_per_request"] * TRAFFIC.get(ep, 0) for ep, v in endpoints.items()) / 3.6e6 * INTENSITY
    metrics.append(f"projected_gco2e_per_day {projected:.3f}")
    Path("metrics.txt").write_text("\n".join(metrics) + "\n")
    Path("carbon-blame.md").write_text(render_markdown(costs, intensity_label=f"{INTENSITY:.0f} gCO₂/kWh"))
    Path("benchmark.json").write_text(json.dumps({"endpoints": endpoints, "projected_gco2e_per_day": projected,
                                                  "traffic": TRAFFIC, "intensity_g_per_kwh": INTENSITY,
                                                  "lines": [c.__dict__ for c in costs[:20]]}, indent=2))
    print(Path("metrics.txt").read_text())
    print(Path("carbon-blame.md").read_text())


if __name__ == "__main__":
    main()
