# Carbon dividend of autonomy (generated)

Generated 2026-10-06T17:15:26+00:00 by `experiments/autonomy_dividend.py` on real grid data.

## GB (NESO average intensity, Sep–Oct 2026)

276 jobs, region `europe-west2`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 4377 | +0.0% | n/a | 0 | 0.0 |
| supervised | 3503 | -20.0% | n/a | 8 | 11.3 |
| hands_off | 3289 | -24.9% | n/a | 0 | 14.7 |

**Carbon dividend of autonomy** (supervised → hands-off): 4.9% of baseline emissions.

## ES spring (Mar–May 2025), OMIE day-ahead → marginal heuristic

756 jobs, region `europe-southwest1`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 13673 | +0.0% | 42.6% | 0 | 0.0 |
| supervised | 10271 | -24.9% | 45.7% | 22 | 3.6 |
| hands_off | 9349 | -31.6% | 46.5% | 0 | 3.0 |

**Carbon dividend of autonomy** (supervised → hands-off): 6.8% of baseline emissions.

## ES summer (Jul–Sep 2025), OMIE day-ahead → marginal heuristic

768 jobs, region `europe-southwest1`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 34153 | +0.0% | 2.5% | 0 | 0.0 |
| supervised | 26469 | -22.5% | 3.9% | 24 | 6.2 |
| hands_off | 24331 | -28.8% | 4.2% | 0 | 7.5 |

**Carbon dividend of autonomy** (supervised → hands-off): 6.3% of baseline emissions.

## NESO forecast intervals (split conformal, α = 0.1)

| Lead (h) | Half-width, static calibration (g/kWh) | Coverage, static | Coverage, rolling 14-day recalibration |
|---:|---:|---:|---:|
| 1 | 45 | 92.1% | 91.5% |
| 6 | 51 | 90.8% | 91.7% |
| 12 | 50 | 88.3% | 90.1% |
| 24 | 47 | 84.3% | 88.3% |
| 36 | 50 | 82.3% | 87.0% |
| 47 | 49 | 81.2% | 87.3% |
