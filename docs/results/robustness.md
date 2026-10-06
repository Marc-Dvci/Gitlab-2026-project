# Robustness of the carbon dividend of autonomy (generated)

Generated 2026-10-06T17:18:16+00:00 by `experiments/robustness.py`. Same protocol as [`autonomy_dividend.md`](autonomy_dividend.md): receding-horizon dispatch on real grids, no look-ahead.

## Across 5 independently seeded backlogs

Median and range (min–max) over seeds 7, 11, 23, 42, 101.

| Grid | Hands-off vs run-now | Supervised vs run-now | Dividend of autonomy | Late jobs, supervised | Late jobs, hands-off |
|---|---:|---:|---:|---:|---:|
| GB (NESO, Sep–Oct 2026) | −23.6% (−22.5% to −24.8%) | −18.7% (−18.2% to −20.0%) | **4.9% (3.1% to 5.3%)** | 7 (5 to 10) | 0 (0 to 0) |
| ES spring (Mar–May 2025) | −31.6% (−29.9% to −33.2%) | −24.9% (−24.4% to −31.2%) | **6.8% (1.7% to 8.7%)** | 16 (12 to 22) | 0 (0 to 0) |
| ES summer (Jul–Sep 2025) | −28.5% (−25.6% to −30.7%) | −20.2% (−18.3% to −22.5%) | **8.3% (6.3% to 8.6%)** | 16 (12 to 24) | 0 (0 to 0) |

## Spain: sensitivity to the price knee of the marginal model

The knee is the day-ahead price above which the marginal kWh is assumed to come from gas (490 g/kWh); at or below 0 €/MWh it is curtailed renewable (11 g/kWh); linear in between. Each row re-scores on its own mapping (seed 7).

| Knee (€/MWh) | ES spring (Mar–May 2025): hands-off vs run-now / dividend | ES summer (Jul–Sep 2025): hands-off vs run-now / dividend |
|---:|---:|---:|
| 20 | −34.9% / 9.0% | −22.1% / 5.0% |
| 40 (default) | −31.6% / 6.8% | −28.8% / 6.3% |
| 60 | −34.7% / 5.8% | −31.8% / 6.7% |
| 80 | −36.4% / 5.2% | −37.8% / 9.0% |
