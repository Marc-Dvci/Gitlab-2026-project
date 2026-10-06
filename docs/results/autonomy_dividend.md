# Carbon dividend of autonomy (generated)

Generated 2026-10-06T12:42:05+00:00 by `experiments/autonomy_dividend.py` on real grid data.

## GB (NESO average intensity, Sep–Oct 2026)

276 jobs, region `europe-west2`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 4377 | +0.0% | n/a | 0 | 0.0 |
| supervised | 3562 | -18.6% | n/a | 9 | 13.2 |
| hands_off | 3286 | -24.9% | n/a | 0 | 15.1 |

**Carbon dividend of autonomy** (supervised → hands-off): 6.3% of baseline emissions.

## ES spring (Mar–May 2025), OMIE day-ahead → marginal heuristic

756 jobs, region `europe-southwest1`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 13673 | +0.0% | 42.6% | 0 | 0.0 |
| supervised | 10208 | -25.3% | 46.1% | 22 | 4.5 |
| hands_off | 9022 | -34.0% | 46.8% | 0 | 4.0 |

**Carbon dividend of autonomy** (supervised → hands-off): 8.7% of baseline emissions.

## ES summer (Jul–Sep 2025), OMIE day-ahead → marginal heuristic

768 jobs, region `europe-southwest1`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 34153 | +0.0% | 2.5% | 0 | 0.0 |
| supervised | 26082 | -23.6% | 3.7% | 27 | 8.5 |
| hands_off | 23540 | -31.1% | 4.1% | 0 | 9.0 |

**Carbon dividend of autonomy** (supervised → hands-off): 7.4% of baseline emissions.

## NESO forecast intervals (split conformal, α = 0.1)

| Lead (h) | Half-width, static calibration (g/kWh) | Coverage, static | Coverage, rolling 14-day recalibration |
|---:|---:|---:|---:|
| 1 | 45 | 92.1% | 91.5% |
| 6 | 51 | 90.8% | 91.7% |
| 12 | 50 | 88.3% | 90.1% |
| 24 | 47 | 84.3% | 88.3% |
| 36 | 50 | 82.3% | 87.0% |
| 47 | 49 | 81.2% | 87.3% |
