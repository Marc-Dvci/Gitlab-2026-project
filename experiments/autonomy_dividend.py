"""The carbon dividend of autonomy — measured on real grid data.

Same backlog, same deadlines, three policies:
  run_now     the work starts the moment it is filed (today's default),
  supervised  carbon-aware, but a human must be awake to approve: starts only in office hours,
  hands_off   carbon-aware, 24/7: the agents follow the wind and the sun.

Two grids:
  GB, Sep–Oct 2026 — NESO average intensity; decisions use the forecast available at the
                     time (conformal-calibrated history shows ~24 g mean error), scored on actuals.
  ES, 2025         — OMIE day-ahead prices, known only after daily publication (~13:00 CET);
                     decisions and scoring use the price→marginal heuristic, and we report the
                     share of energy consumed in surplus (price ≤ 0) hours.

Run:  python experiments/autonomy_dividend.py  (writes docs/results/autonomy_dividend.{json,md})
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from joulethief.dispatch.receding import OfficeHours, simulate, synthetic_backlog  # noqa: E402
from joulethief.dispatch.uncertainty import ConformalIntervals, chronological_split, rolling_coverage  # noqa: E402
from joulethief.replay import es_forecast_fn, gb_forecast_fn  # noqa: E402
from joulethief.signals.marginal import PriceMarginalModel  # noqa: E402
from joulethief.signals.snapshots import es_prices, gb_forecast_errors, gb_intensity  # noqa: E402

UTC = timezone.utc


def run_case(name, region, actual, forecast, start, end, tz, surplus=None, seed=7):
    jobs = synthetic_backlog(start, (end - start).days - 3, region=region, tz=tz, seed=seed)
    office = OfficeHours(tz=tz)
    results = {}
    for policy in ("run_now", "supervised", "hands_off"):
        t0 = time.time()
        res = simulate(jobs, {region: actual}, forecast, policy, start, end, office_hours=office, surplus=surplus)
        results[policy] = {**res.to_dict(), "runtime_s": round(time.time() - t0, 1)}
    base = results["run_now"]["realized_g"]
    for policy in ("supervised", "hands_off"):
        results[policy]["reduction_vs_run_now"] = round(1 - results[policy]["realized_g"] / base, 4)
    results["carbon_dividend_of_autonomy"] = round(
        (results["supervised"]["realized_g"] - results["hands_off"]["realized_g"]) / base, 4)
    return {"case": name, "region": region, "start": start.isoformat(), "end": end.isoformat(), "jobs": len(jobs),
            "results": results}


def main() -> None:
    out_dir = ROOT / "docs" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"generated": datetime.now(UTC).isoformat(timespec="seconds"), "cases": []}

    # Conformal calibration of NESO forecasts (real forecast archive).
    calib, test = chronological_split(gb_forecast_errors(), 0.6)
    ci = ConformalIntervals.fit(calib, alpha=0.1)
    rolling = rolling_coverage(gb_forecast_errors(), alpha=0.1, window_days=14)
    report["neso_conformal"] = {"alpha": 0.1, "q_by_lead_g": ci.q_by_lead,
                                "held_out_coverage": {k: round(v, 3) for k, v in ci.coverage(test).items()},
                                "rolling_14d_coverage": {k: round(v, 3) for k, v in rolling.items()}}

    gb = gb_intensity()
    report["cases"].append(run_case(
        "GB (NESO average intensity, Sep–Oct 2026)", "europe-west2", gb, gb_forecast_fn(),
        datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC), "Europe/London"))

    prices = es_prices()
    model = PriceMarginalModel(fossil_margin_g=490.0, fossil_price=40.0)
    marginal = model.series(prices)
    surplus = lambda region, t: (prices.value_at(t) or 1.0) <= 0  # noqa: E731
    for label, s, e in (("ES spring (Mar–May 2025)", datetime(2025, 3, 1), datetime(2025, 6, 1)),
                        ("ES summer (Jul–Sep 2025)", datetime(2025, 7, 1), datetime(2025, 9, 30))):
        report["cases"].append(run_case(
            f"{label}, OMIE day-ahead → marginal heuristic", "europe-southwest1", marginal, es_forecast_fn(marginal),
            s.replace(tzinfo=UTC), e.replace(tzinfo=UTC), "Europe/Madrid", surplus))

    (out_dir / "autonomy_dividend.json").write_text(json.dumps(report, indent=2, default=str))
    lines = ["# Carbon dividend of autonomy (generated)", "",
             f"Generated {report['generated']} by `experiments/autonomy_dividend.py` on real grid data.", ""]
    for case in report["cases"]:
        r = case["results"]
        lines += [f"## {case['case']}", "", f"{case['jobs']} jobs, region `{case['region']}`.", "",
                  "| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |",
                  "|---|---:|---:|---:|---:|---:|"]
        for p in ("run_now", "supervised", "hands_off"):
            x = r[p]
            share = f"{x['surplus_share']:.1%}" if case["region"] != "europe-west2" else "n/a"
            lines.append(f"| {p} | {x['realized_g']:.0f} | {-x.get('reduction_vs_run_now', 0):+.1%} | "
                         f"{share} | {x['late_jobs']} | {x['mean_wait_h']:.1f} |")
        lines += ["", f"**Carbon dividend of autonomy** (supervised → hands-off): {r['carbon_dividend_of_autonomy']:.1%} of baseline emissions.", ""]
    q = report["neso_conformal"]
    lines += ["## NESO forecast intervals (split conformal, α = 0.1)", "",
              "| Lead (h) | Half-width, static calibration (g/kWh) | Coverage, static | Coverage, rolling 14-day recalibration |",
              "|---:|---:|---:|---:|"]
    for lead in sorted(q["q_by_lead_g"]):
        lines.append(f"| {lead} | {q['q_by_lead_g'][lead]:.0f} | {q['held_out_coverage'].get(lead, float('nan')):.1%} | "
                     f"{q['rolling_14d_coverage'].get(lead, float('nan')):.1%} |")
    (out_dir / "autonomy_dividend.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
