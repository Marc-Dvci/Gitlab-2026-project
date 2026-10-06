# Robustness of the carbon dividend of autonomy (generated)

Generated 2026-10-06T14:02:14+00:00 by `experiments/robustness.py` (9 min).

## 1. Five backlogs (seeds 7, 11, 23, 42, 101)

Reduction versus run-now on the decision signal; mean (min–max) over seeds.

| Grid | Supervised | Hands-off | Dividend of autonomy | Late jobs, hands-off (max) | Late jobs, supervised |
|---|---:|---:|---:|---:|---:|
| GB (NESO average, Sep–Oct 2026) | 17.0% (15.2%–17.9%) | 23.6% (22.6%–24.9%) | 6.6% (4.8%–8.5%) | 0 | 9 (5–14) |
| ES spring (Mar–May 2025), marginal heuristic | 27.4% (24.9%–31.4%) | 33.6% (30.1%–36.8%) | 6.3% (3.3%–9.5%) | 0 | 17 (12–22) |
| ES summer (Jul–Sep 2025), marginal heuristic | 21.3% (20.5%–22.3%) | 31.2% (28.4%–33.2%) | 9.9% (7.9%–11.0%) | 0 | 20 (14–29) |

## 2. Decide with one price knee, score with another (Spain)

The knee is the day-ahead price above which a fossil unit is assumed to be on the margin. Rows: the knee the dispatcher believed; columns: the knee used to score it. Cells: hands-off reduction versus run-now under the scoring model. Off-diagonal cells are what a wrong model costs.

### ES spring (Mar–May 2025)

| Decided with ↓ / scored with → | 20 €/MWh | 40 €/MWh | 60 €/MWh | 80 €/MWh |
|---|---:|---:|---:|---:|
| 20 €/MWh | 35.7% | 31.8% | 28.4% | 25.9% |
| 40 €/MWh | 37.1% | 34.2% | 32.4% | 30.3% |
| 60 €/MWh | 38.3% | 35.8% | 36.2% | 36.0% |
| 80 €/MWh | 38.3% | 35.8% | 36.2% | 37.6% |

No emission model at all — what the energy cost on the day-ahead market, and how much of it was drawn in hours with a price at or below zero:

| Policy | Mean price paid (€/MWh) | Energy in surplus hours |
|---|---:|---:|
| run now | 14.5 | 42.6% |
| hands off knee 20 | 10.3 | 46.5% |
| hands off knee 40 | 9.5 | 46.6% |
| hands off knee 60 | 8.4 | 46.5% |
| hands off knee 80 | 8.0 | 46.5% |

### ES summer (Jul–Sep 2025)

| Decided with ↓ / scored with → | 20 €/MWh | 40 €/MWh | 60 €/MWh | 80 €/MWh |
|---|---:|---:|---:|---:|
| 20 €/MWh | 24.3% | 24.1% | 23.1% | 21.7% |
| 40 €/MWh | 27.6% | 30.6% | 31.2% | 30.3% |
| 60 €/MWh | 29.7% | 33.3% | 35.1% | 35.5% |
| 80 €/MWh | 30.8% | 34.7% | 36.9% | 38.6% |

No emission model at all — what the energy cost on the day-ahead market, and how much of it was drawn in hours with a price at or below zero:

| Policy | Mean price paid (€/MWh) | Energy in surplus hours |
|---|---:|---:|
| run now | 34.0 | 2.5% |
| hands off knee 20 | 26.4 | 4.2% |
| hands off knee 40 | 23.3 | 4.5% |
| hands off knee 60 | 21.2 | 4.5% |
| hands off knee 80 | 19.8 | 4.4% |

## Reading

- The dividend of autonomy is positive for every grid and every backlog (3.3%–11.0% of baseline emissions). Hands-off missed 0 deadlines in all 15 runs; supervised missed 5–29 per run.
- Whatever knee the dispatcher believes and whatever knee is true, hands-off cuts emissions by 22%–39%. Deciding with the default 40 €/MWh costs at most 8.3% of baseline emissions against the best knee for the scoring model; higher decision knees (smoother price→carbon mappings) did as well or better under every scoring model, so the default is conservative.
- The market columns need no carbon model: hands-off buys its energy at a lower day-ahead price under every knee, and draws more of it in hours with a price at or below zero, when inflexible renewable output exceeds demand.
