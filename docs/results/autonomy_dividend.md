# Carbon dividend of autonomy (generated)

Generated 2026-10-06T13:50:37+00:00 by `experiments/autonomy_dividend.py` on real grid data.

## GB (NESO average intensity, Sep–Oct 2026)

276 jobs, region `europe-west2`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 4377 | +0.0% | n/a | 0 | 0.0 |
| supervised | 3593 | -17.9% | n/a | 10 | 13.5 |
| hands_off | 3289 | -24.9% | n/a | 0 | 14.7 |

**Carbon dividend of autonomy** (supervised → hands-off): 6.9% of baseline emissions.

## ES spring (Mar–May 2025), OMIE day-ahead → marginal heuristic

756 jobs, region `europe-southwest1`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 13673 | +0.0% | 42.6% | 0 | 0.0 |
| supervised | 10055 | -26.5% | 45.5% | 22 | 4.2 |
| hands_off | 8996 | -34.2% | 46.4% | 0 | 3.5 |

**Carbon dividend of autonomy** (supervised → hands-off): 7.8% of baseline emissions.

## ES summer (Jul–Sep 2025), OMIE day-ahead → marginal heuristic

768 jobs, region `europe-southwest1`.

| Policy | Emissions (g, decision signal) | vs run-now | Energy in surplus hours | Late jobs | Mean wait (h) |
|---|---:|---:|---:|---:|---:|
| run_now | 34153 | +0.0% | 2.5% | 0 | 0.0 |
| supervised | 27155 | -20.5% | 3.9% | 29 | 11.4 |
| hands_off | 23685 | -30.6% | 4.4% | 0 | 10.4 |

**Carbon dividend of autonomy** (supervised → hands-off): 10.2% of baseline emissions.

## NESO forecast intervals (split conformal, α = 0.1)

| Lead (h) | Half-width, static calibration (g/kWh) | Coverage, static | Coverage, rolling 14-day recalibration |
|---:|---:|---:|---:|
| 1 | 45 | 92.1% | 91.5% |
| 6 | 51 | 90.8% | 91.7% |
| 12 | 50 | 88.3% | 90.1% |
| 24 | 47 | 84.3% | 88.3% |
| 36 | 50 | 82.3% | 87.0% |
| 47 | 49 | 81.2% | 87.3% |
