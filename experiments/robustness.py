"""How robust is the carbon dividend of autonomy? Backlog seeds and price-model assumptions.

The headline experiment (``autonomy_dividend.py``) uses one seeded backlog and one price→marginal
mapping. Here the same protocol is repeated
  * over several independently seeded backlogs (same grids, same policies), and
  * for Spain, over the price knee at which the marginal kWh is assumed fossil (20–80 €/MWh;
    40 €/MWh is the default), since that mapping is a heuristic.

Run:  python experiments/robustness.py   (~15 min; writes docs/results/robustness.{json,md})
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autonomy_dividend import run_case  # noqa: E402

from joulethief.replay import es_forecast_fn, gb_forecast_fn  # noqa: E402
from joulethief.signals.marginal import PriceMarginalModel  # noqa: E402
from joulethief.signals.snapshots import es_prices, gb_intensity  # noqa: E402

UTC = timezone.utc
SEEDS = (7, 11, 23, 42, 101)
KNEES = (20.0, 40.0, 60.0, 80.0)
ES_PERIODS = (("ES spring (Mar–May 2025)", datetime(2025, 3, 1, tzinfo=UTC), datetime(2025, 6, 1, tzinfo=UTC)),
              ("ES summer (Jul–Sep 2025)", datetime(2025, 7, 1, tzinfo=UTC), datetime(2025, 9, 30, tzinfo=UTC)))


def _row(case: dict) -> dict:
    r = case["results"]
    return {"jobs": case["jobs"], "hands_off": r["hands_off"]["reduction_vs_run_now"],
            "supervised": r["supervised"]["reduction_vs_run_now"], "dividend": r["carbon_dividend_of_autonomy"],
            "late_supervised": r["supervised"]["late_jobs"], "late_hands_off": r["hands_off"]["late_jobs"],
            "surplus_share_hands_off": r["hands_off"]["surplus_share"]}


def _es(knee: float, seed: int, label: str, start: datetime, end: datetime) -> dict:
    prices = es_prices()
    marginal = PriceMarginalModel(fossil_margin_g=490.0, fossil_price=knee).series(prices)
    surplus = lambda region, t: (prices.value_at(t) or 1.0) <= 0  # noqa: E731
    return _row(run_case(label, "europe-southwest1", marginal, es_forecast_fn(marginal), start, end, "Europe/Madrid",
                         surplus, seed=seed))


def main() -> None:
    report = {"generated": datetime.now(UTC).isoformat(timespec="seconds"), "seeds": list(SEEDS),
              "knees_eur_mwh": list(KNEES), "by_seed": {}, "by_knee": {}}
    gb = gb_intensity()
    for seed in SEEDS:
        rows = {"GB (NESO, Sep–Oct 2026)": _row(run_case(
            "GB", "europe-west2", gb, gb_forecast_fn(), datetime(2026, 9, 1, tzinfo=UTC),
            datetime(2026, 10, 5, tzinfo=UTC), "Europe/London", seed=seed))}
        for label, s, e in ES_PERIODS:
            rows[label] = _es(40.0, seed, label, s, e)
        report["by_seed"][seed] = rows
        print(f"seed {seed}: " + ", ".join(f"{k}: {v['dividend']:.1%}" for k, v in rows.items()), flush=True)
    for knee in KNEES:
        report["by_knee"][knee] = ({label: report["by_seed"][7][label] for label, _, _ in ES_PERIODS} if knee == 40.0
                                   else {label: _es(knee, 7, label, s, e) for label, s, e in ES_PERIODS})
        print(f"knee {knee:.0f} €/MWh done", flush=True)

    out = ROOT / "docs" / "results"
    (out / "robustness.json").write_text(json.dumps(report, indent=2))
    cases = list(report["by_seed"][SEEDS[0]])
    lines = ["# Robustness of the carbon dividend of autonomy (generated)", "",
             f"Generated {report['generated']} by `experiments/robustness.py`. Same protocol as "
             "[`autonomy_dividend.md`](autonomy_dividend.md): receding-horizon dispatch on real grids, no look-ahead.", "",
             f"## Across {len(SEEDS)} independently seeded backlogs", "",
             "Median and range (min–max) over seeds " + ", ".join(map(str, SEEDS)) + ".", "",
             "| Grid | Hands-off vs run-now | Supervised vs run-now | Dividend of autonomy | Late jobs, supervised | Late jobs, hands-off |",
             "|---|---:|---:|---:|---:|---:|"]

    def span(case: str, key: str, kind: str) -> str:
        vals = sorted(report["by_seed"][seed][case][key] for seed in SEEDS)
        med, lo, hi = statistics.median(vals), vals[0], vals[-1]
        if kind == "reduction":
            return f"−{med:.1%} (−{lo:.1%} to −{hi:.1%})"
        if kind == "share":
            return f"{med:.1%} ({lo:.1%} to {hi:.1%})"
        return f"{med:.0f} ({lo:.0f} to {hi:.0f})"

    for case in cases:
        lines.append(f"| {case} | {span(case, 'hands_off', 'reduction')} | {span(case, 'supervised', 'reduction')} | "
                     f"**{span(case, 'dividend', 'share')}** | {span(case, 'late_supervised', 'count')} | "
                     f"{span(case, 'late_hands_off', 'count')} |")
    lines += ["", "## Spain: sensitivity to the price knee of the marginal model", "",
              "The knee is the day-ahead price above which the marginal kWh is assumed to come from gas "
              "(490 g/kWh); at or below 0 €/MWh it is curtailed renewable (11 g/kWh); linear in between. "
              "Each row re-scores on its own mapping (seed 7).", "",
              "| Knee (€/MWh) | " + " | ".join(f"{label}: hands-off vs run-now / dividend" for label, _, _ in ES_PERIODS) + " |",
              "|---:|" + "---:|" * len(ES_PERIODS)]
    for knee in KNEES:
        cells = [f"−{report['by_knee'][knee][label]['hands_off']:.1%} / {report['by_knee'][knee][label]['dividend']:.1%}"
                 for label, _, _ in ES_PERIODS]
        lines.append(f"| {knee:.0f}{' (default)' if knee == 40.0 else ''} | " + " | ".join(cells) + " |")
    (out / "robustness.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
