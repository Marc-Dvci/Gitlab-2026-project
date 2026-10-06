# Net impact: does Joule Thief pay back its own footprint? (generated)

Generated 2026-10-06T14:03:42+00:00 by `experiments/net_impact.py`. Every gram Joule Thief *adds* is charged at the annual **marginal** intensity of where it runs (Finland 785, South Carolina 728 g/kWh), so it is comparable with the consequential savings. Values are likely (low–high).

## What Joule Thief adds

| Layer | Component | How it was obtained | v1 | now |
|---|---|---|---:|---:|
| scheduling, per Surge Request | Dispatcher ticks (Cloud Run, every 30 min) | **measured** on this machine: cold start 1.96 (1.79–2.00) CPU-s, CP-SAT solve 0.030 (0.007–0.722) CPU-s; CCF power model; idle memory after each tick | 0.130 (0.004–4.012) | 0.130 (0.004–4.012) |
| scheduling, per Surge Request | Surge Intake triage | EcoLogits, claude-haiku-4-5 (upper bound claude-sonnet-4-6) | 0.049 (0.008–2.291) | 0.022 (0.001–2.291) |
| measurement, per code change | Accounting CI jobs | CCF model, e2-standard-2 hosted runner in `us-east1`: 9.8 (6.9–25.5) → 8.1 (5.8–18.6) runner-minutes | 1.492 (0.683–6.290) | 1.233 (0.574–4.588) |
| measurement, per code change | carbon-reviewer (every MR) | EcoLogits | 0.117 (0.017–6.873) | — |
| measurement, per code change | release-captain (every delivery) | EcoLogits | 0.059 (0.011–3.818) | — |
| measurement, per code change | carbon-reviewer (on regression) | EcoLogits | — | 0.029 (0.000–6.873) |
| | **Scheduling layer** | | **0.179 (0.012–6.303)** | **0.152 (0.005–6.303)** |
| | **Measurement layer** | | **1.668 (0.711–16.981)** | **1.262 (0.574–11.461)** |

What changed between v1 and now: carbon receipts and the receipt gate run only for images that can be deployed (default branch); the Release Captain LLM flow became `joule shipped`, a script that copies the numbers from the pipeline's artifacts; the Carbon Reviewer agent is started by CI only when an MR regresses joules/request or edits a hot line (every MR still gets a deterministic energy table); issues filed from the Surge Request template carry their labels, so triage takes one call. LLM calls per code change, likely: 19 → 5.

Cross-check on the agents: at Google's published median of 0.24 Wh per Gemini prompt, 5 calls would use 1.20 Wh. EcoLogits models output tokens only, so long agent contexts are under-counted; the upper bound uses a mid-size model to cover that.

Heartbeat choice: the Cloud Run tick costs 1.12 (0.03–34.39) g/day; the same heartbeat as a GitLab scheduled pipeline would cost 7.3 (2.4–17.8) g/day.

## The balance (now)

Saved = hands-off versus run-now on the same backlog and grids as the autonomy experiment. Overhead = the scheduling layer for every Surge Request + the measurement layer for the share that becomes code changes. *Provider-hosted*: LLM inference runs wherever the provider runs it, so only CI work (pipelines, scans) is credited.

| Grid | Scenario | Run-now g/SR | Saved g/SR | Overhead g/SR | Payback, scheduling only | Payback, everything (v1 → now) |
|---|---|---:|---:|---:|---:|---:|
| GB, NESO average, Sep–Oct 2026 | self-hosted model | 15.9 | 3.94 | 0.79 (0.30–12.12) | 26× (worst 0.6×) | 3.8× → **5.0×** (worst 0.3×) |
| GB, NESO average, Sep–Oct 2026 | provider-hosted | 15.9 | 0.57 | 0.79 (0.30–12.12) | 4× (worst 0.1×) | 0.6× → **0.7×** (worst 0.1×) |
| ES spring 2025, marginal heuristic | self-hosted model | 18.1 | 6.19 | 0.78 (0.29–12.02) | 41× (worst 1.0×) | 6.1× → **7.9×** (worst 0.5×) |
| ES spring 2025, marginal heuristic | provider-hosted | 18.1 | 0.99 | 0.78 (0.29–12.02) | 6× (worst 0.2×) | 1.0× → **1.3×** (worst 0.1×) |
| ES summer 2025, marginal heuristic | self-hosted model | 44.5 | 13.63 | 0.78 (0.29–12.03) | 89× (worst 2.2×) | 13.4× → **17.4×** (worst 1.1×) |
| ES summer 2025, marginal heuristic | provider-hosted | 44.5 | 2.07 | 0.78 (0.29–12.03) | 14× (worst 0.3×) | 2.0× → **2.6×** (worst 0.2×) |

## SCI per Surge Request, net of everything Joule Thief adds

SCI = (E × I + M) / R with R = 1 Surge Request, consequential intensity; hands-off includes the full overhead (scheduling + measurement), likely (low–high).

| Grid | Scenario | Run-now (g/SR) | Hands-off, net (g/SR) | Change (likely) |
|---|---|---:|---:|---:|
| GB, NESO average, Sep–Oct 2026 | self-hosted model | 15.9 | 12.7 (12.2–24.0) | -20% |
| GB, NESO average, Sep–Oct 2026 | provider-hosted | 15.9 | 16.1 (15.6–27.4) | +1% |
| ES spring 2025, marginal heuristic | self-hosted model | 18.1 | 12.7 (12.2–23.9) | -30% |
| ES spring 2025, marginal heuristic | provider-hosted | 18.1 | 17.9 (17.4–29.1) | -1% |
| ES summer 2025, marginal heuristic | self-hosted model | 44.5 | 31.6 (31.1–42.9) | -29% |
| ES summer 2025, marginal heuristic | provider-hosted | 44.5 | 43.2 (42.7–54.4) | -3% |

With provider-hosted inference, Joule Thief can move only CI work, so its net effect on a Surge Request's total is small; the lever is to put inference where it can be scheduled (self-hosted or region-pinned models, e.g. GitLab Duo Self-Hosted).

## Break-even: how much energy must a Surge Request move?

Each kWh the dispatcher moves saves the grams below; dividing what Joule Thief adds by that gives the deferrable energy per Surge Request at which it pays for itself (likely values). Work below the threshold is cheaper to run now.

| Grid | Saved per kWh moved (g) | Break-even, scheduling only (Wh) | Break-even, everything (Wh) |
|---|---:|---:|---:|
| GB, NESO average, Sep–Oct 2026 | 26 | 5.8 | 30.3 |
| ES spring 2025, marginal heuristic | 41 | 3.7 | 19.1 |
| ES summer 2025, marginal heuristic | 90 | 1.7 | 8.7 |

For scale: a 4-vCPU hosted runner draws ≈ 15–20 W, so 20 Wh is about an hour of CI; one GPU inference worker (≈ 350 W in the backlog model) moves that much in four minutes.

## Savings by kind of work (hands-off vs run-now)

| Grid | Kind | Jobs | Energy (kWh) | Saved (g) | Saved per job (g) |
|---|---|---:|---:|---:|---:|
| GB, NESO average, Sep–Oct 2026 | agent_session | 66 | 15.89 | 398 | 6.03 |
| GB, NESO average, Sep–Oct 2026 | ci_pipeline | 75 | 1.32 | 22 | 0.30 |
| GB, NESO average, Sep–Oct 2026 | dependency_upgrade | 74 | 19.09 | 532 | 7.18 |
| GB, NESO average, Sep–Oct 2026 | security_scan | 61 | 5.27 | 136 | 2.23 |
| ES spring 2025, marginal heuristic | agent_session | 190 | 47.29 | 1716 | 9.03 |
| ES spring 2025, marginal heuristic | ci_pipeline | 201 | 3.44 | 146 | 0.73 |
| ES spring 2025, marginal heuristic | dependency_upgrade | 187 | 48.59 | 2214 | 11.84 |
| ES spring 2025, marginal heuristic | security_scan | 178 | 15.09 | 601 | 3.38 |
| ES summer 2025, marginal heuristic | agent_session | 196 | 48.74 | 4257 | 21.72 |
| ES summer 2025, marginal heuristic | ci_pipeline | 204 | 3.48 | 283 | 1.39 |
| ES summer 2025, marginal heuristic | dependency_upgrade | 188 | 48.89 | 4619 | 24.57 |
| ES summer 2025, marginal heuristic | security_scan | 180 | 15.31 | 1310 | 7.28 |

## Reading

- Payback = grams avoided ÷ grams added; above 1× Joule Thief removes more than it emits. *Worst* divides the likely saving by the upper bound of every overhead (largest model, every loop at its cap, idle vCPU charged at its minimum power): it is a bound, not a forecast.
- Likely case: scheduling repays itself 4–89× in every grid and scenario. With the measurement layer (receipts, benchmarks, ledgers, reviewers) included, Joule Thief repays itself 5–17× when inference is self-hosted and 0.7–2.6× when only CI work can move: below break-even on the GB average signal, above it on the Spanish marginal signal.
- Measurement is what makes the claims verifiable, and it is now the largest overhead: runner minutes of accounting jobs on hosted runners in South Carolina. Where only small CI jobs can move, it is close to break-even; the break-even table says which work is worth scheduling at all.
- GB rows use NESO *average* intensity (no free marginal signal for GB): indicative, not consequential. Spain uses the price→marginal heuristic of METHODOLOGY.md §3.
- The backlog is synthetic and seeded; grids are real. Runner minutes are modelled until a real `govern:footprint` ledger exists, which records every job's actual duration.
