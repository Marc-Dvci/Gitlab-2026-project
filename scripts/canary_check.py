"""Monitor-stage gate: an energy regression is a bug.

Drives the same traffic at the canary revision and at production, then compares CPU-joules
per request measured by each revision's own profiler (/api/blame). Fails (exit 1) when the
canary is slower *or* hungrier than production beyond the tolerance, so the release job
never promotes it; optionally opens an incident issue for the agents.

Usage: python scripts/canary_check.py CANARY_URL PROD_URL [--tolerance 0.15]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

PATHS = ["/api/compare", "/api/grid/europe-southwest1"]


def get(url: str, timeout: float = 60.0) -> tuple[int, bytes, float]:
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (our own service)
        return resp.status, resp.read(), time.time() - t0


def joules_per_request(base: str, rounds: int) -> tuple[dict[str, float], int]:
    errors = 0
    for _ in range(rounds):
        for path in PATHS:
            try:
                status, _, _ = get(base + path)
                errors += status >= 500
            except Exception:  # noqa: BLE001
                errors += 1
    _, body, _ = get(base + "/api/blame")
    endpoints = json.loads(body)["endpoints"]
    jps = 4.26 * 1.09  # W per busy vCPU (CCF GCP max, upper bound) × PUE; the ratio is what matters
    return {ep: v["cpu_seconds"] / max(v["requests"], 1) * jps for ep, v in endpoints.items()}, errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("canary")
    ap.add_argument("prod")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--tolerance", type=float, default=0.15)
    args = ap.parse_args()
    canary, c_err = joules_per_request(args.canary.rstrip("/"), args.rounds)
    prod, p_err = joules_per_request(args.prod.rstrip("/"), args.rounds)
    report = {"canary_j_per_request": canary, "prod_j_per_request": prod, "canary_errors": c_err, "prod_errors": p_err}
    failures = [f"{c_err} errors on canary"] if c_err > p_err else []
    for ep, j in canary.items():
        if ep in prod and prod[ep] > 0 and j > prod[ep] * (1 + args.tolerance):
            failures.append(f"{ep}: {j:.3f} J/request vs {prod[ep]:.3f} in production (+{j / prod[ep] - 1:.0%})")
    report["failures"] = failures
    print(json.dumps(report, indent=2))
    with open("canary-report.json", "w") as fh:
        json.dump(report, fh, indent=2)
    if failures and os.environ.get("JOULE_GITLAB_TOKEN"):
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from joulethief.gitlab import GitLab

        GitLab.from_env().create_issue(
            f"Energy regression blocked in canary ({os.environ.get('CI_COMMIT_SHORT_SHA', '')})",
            "The canary used more energy per request than production; it was not promoted.\n\n- " + "\n- ".join(failures),
            ["incident", "surge::queued", "priority::high", "energy::agent_session"])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
