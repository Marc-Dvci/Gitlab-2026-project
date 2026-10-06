# Methodology — how Joule Thief counts

This document is the basis of the "Most Environmentally Impactful" write-up. Every number the
system emits follows the rules below and carries a low / likely / high range.

## 1. Standards

| Scope | Standard | Functional unit (R) |
|---|---|---|
| The deployed service | **SCI**, ISO/IEC 21031:2024: `SCI = ((E × I) + M) / R` | 1,000 requests |
| The agents (LLM inference) | **GSF SCI for AI** (ratified Dec 2025), consumer boundary | 1 resolved issue; also gCO₂e per million input / output tokens, reported separately |
| CI/CD | SCI per pipeline, consistent with Eco CI's definition | 1 pipeline |
| Reporting | GHG Protocol Scope 2, location-based | — |
| Decisions and avoided-emission claims | Consequential (marginal) accounting | — |

## 2. Energy (E)

- **CPU & memory** (CI jobs, Cloud Run): Cloud Carbon Footprint coefficients. Watts per vCPU =
  `Wmin + u × (Wmax − Wmin)`, with the range taken across microarchitectures; memory 0.392 W/GB;
  × PUE (1.07 / 1.09 / 1.12). Utilisation defaults to 0.6 for CI jobs.
- **Per request**: exact CPU time per request (`time.thread_time()`), × busy-vCPU watts × PUE.
- **LLM calls**: EcoLogits (bottom-up model from parameters, output tokens and latency; provider PUE
  and WUE ranges). For GitLab Duo sessions without exposed token counts, calls are reconstructed from
  the session trace (`trace.jsonl`): each AI message is one call whose input is the conversation so
  far, which reproduces the quadratic context growth of agent loops. Labelled *estimated*.
- **Measured vs modelled**: every ledger entry has `measured: true|false`. Today all cloud energy is
  modelled; a self-hosted GPU path (NVML counters) is designed but needs credits.

## 3. Intensity (I): two ledgers

| Ledger | Intensity | Purpose |
|---|---|---|
| **Attributional** | Location-based average (Google 2024 per region; NESO for GB) | Reporting, budgets |
| **Consequential** | Marginal: WattTime MOER if configured; else the price model below; else the region's annual marginal (GSF) | Decisions; the only basis for "avoided" |

**Price → marginal model** (European bidding zones). Day-ahead price p (EUR/MWh):
`p ≤ 0` → surplus: the marginal kWh is renewable that would be curtailed or exported at a loss
(11 g/kWh, IPCC AR5 onshore wind median); `p ≥ 40` → a thermal unit or an import displacing one is
on the margin (the zone's annual marginal from GSF/WattTime, e.g. 785 g/kWh for Finland; 490 g/kWh
gas CCGT by default); linear in between. This is a transparent heuristic, not a dispatch model, and
is replaced by WattTime MOER wherever available. A sensitivity analysis on the 40 €/MWh knee is on
the roadmap.

**Avoided emissions** = consequential(counterfactual: run immediately, default region) −
consequential(actual). Attributional differences are never called "avoided".

## 4. Embodied (M)

CCF embodied kgCO₂e of the host server, amortised over 4 years and over the share of host vCPUs
reserved. Spot/preemptible capacity is used for deferrable work where possible (it reuses capacity
that already exists).

## 5. Water

`water = E_IT × WUE_onsite(T) + E_IT × PUE × EWIF(grid)`. Onsite WUE ranges come from provider
disclosures used by EcoLogits (0.13–0.999 L/kWh), scaled by outside temperature (illustrative
sensitivity, to be calibrated); Hamina is seawater-cooled (~0 freshwater onsite). EWIF per country
comes from EcoLogits' electricity mixes.

## 6. Uncertainty

- Ranges propagate with interval arithmetic (`joulethief/estimate.py`).
- Grid forecasts: split-conformal intervals per lead time from NESO's archived forecasts, with
  rolling 14-day recalibration (coverage 87–92 % at α = 0.1 on held-out data).
- Day-ahead prices have no forecast error once published; beyond the published horizon the
  dispatcher treats slots as unknown (pessimistic) and may defer.

## 7. Evaluation protocol

`experiments/autonomy_dividend.py` replays real grids with a receding-horizon dispatcher that sees
only information available at decision time; emissions are scored on what the grid actually did.
Policies: run-now, supervised (starts only in office hours), hands-off (24/7). Critical work always
starts immediately. Reported: emissions, share of energy in surplus hours, deadline misses, mean wait.

## 8. Reproduce

```bash
python scripts/build_snapshots.py          # rebuild the real-data snapshots
python experiments/autonomy_dividend.py    # policies × grids, conformal intervals
python experiments/region_ledgers.py       # average vs marginal per region
python scripts/energy_benchmark.py         # joules/request and carbon blame for this service
```
