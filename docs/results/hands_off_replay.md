# Hands-off replay — replay: OMIE day-ahead 2025 → marginal heuristic

`joule demo --grid es` · region `europe-southwest1` · 5 days from 2025-05-05 · production dispatcher (`joulethief.loop.tick`) every 30 min against an in-memory GitLab. Issues arrive already triaged, with the labels the Surge Intake flow sets.

| Issues | Shipped | Deadlines missed | Hands-off gCO₂e | Run-now gCO₂e | Reduction | Energy in surplus hours | Mean wait |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 30 | 0 | 179 | 446 | 59.9% | 91% | 1.5 h |

19 Duo flows and 11 pipelines started by the dispatcher; 38 @grid notes posted. No human touched anything after filing.

## #1 Upgrade FastAPI, uvicorn and mcp to the latest minor versions

- **Mon 07:12 UTC** — filed and triaged: priority::low, energy::dependency_upgrade, surge::queued
- **Mon 07:12 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **206 gCO₂/kWh**. I'm holding this Surge Request until **Mon 09:12 UTC**, when I expect **11 gCO₂/kWh** (≈95% less). Deadline Thu 07:57 UTC is safe.
- **Mon 09:00 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing 1 queued Surge Request(s) now: marginal ≈ **11 gCO₂/kWh**. Day-ahead price is **0.0 €/MWh** — clean power is in surplus.
- **Mon 09:00 UTC** — Surge Worker flow started through the Flows API (hands-off, no user prompts)
- **Mon 09:45 UTC** — **Shipped** · 0.262 kWh in `europe-southwest1`, **2.9 gCO₂e** on the decision signal vs 54.1 g had it run when filed (-95%). 100% of it in surplus hours. Waited 1.8 h; deadline met.

## #10 Dashboard comparison is slow

- **Mon 19:10 UTC** — filed and triaged: priority::normal, energy::agent_session, surge::queued
- **Mon 19:10 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **347 gCO₂/kWh**. I'm holding this Surge Request until **Tue 08:10 UTC**, when I expect **11 gCO₂/kWh** (≈97% less). Deadline Tue 19:50 UTC is safe.
- **Tue 08:00 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing 1 queued Surge Request(s) now: marginal ≈ **11 gCO₂/kWh**. Day-ahead price is **-0.5 €/MWh** — clean power is in surplus.
- **Tue 08:00 UTC** — Surge Worker flow started through the Flows API (hands-off, no user prompts)
- **Tue 08:40 UTC** — **Shipped** · 0.233 kWh in `europe-southwest1`, **2.6 gCO₂e** on the decision signal vs 81.1 g had it run when filed (-97%). 100% of it in surplus hours. Waited 12.8 h; deadline met.

## #11 Run the full Python 3.11–3.13 test matrix

- **Mon 20:05 UTC** — filed and triaged: priority::normal, energy::ci_pipeline, surge::queued
- **Mon 20:05 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **233 gCO₂/kWh**. I'm holding this Surge Request until **Tue 08:05 UTC**, when I expect **11 gCO₂/kWh** (≈95% less). Deadline Tue 20:25 UTC is safe.
- **Tue 08:00 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing 1 queued Surge Request(s) now: marginal ≈ **11 gCO₂/kWh**. Day-ahead price is **-0.5 €/MWh** — clean power is in surplus.
- **Tue 08:00 UTC** — pipeline started on `main` with JOULE_TASK=heavy-tests
- **Tue 08:20 UTC** — **Shipped** · 0.017 kWh in `europe-southwest1`, **0.2 gCO₂e** on the decision signal vs 3.9 g had it run when filed (-95%). 100% of it in surplus hours. Waited 11.9 h; deadline met.

## #20 Full DAST and fuzzing scan before the release

- **Tue 17:30 UTC** — filed and triaged: priority::low, energy::security_scan, surge::queued
- **Tue 17:30 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **19 gCO₂/kWh**. I'm holding this Surge Request until **Wed 08:00 UTC**, when I expect **11 gCO₂/kWh** (≈41% less). Deadline Fri 18:30 UTC is safe.
- **Wed 08:00 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing 1 queued Surge Request(s) now: marginal ≈ **11 gCO₂/kWh**. Day-ahead price is **0.0 €/MWh** — clean power is in surplus.
- **Wed 08:00 UTC** — pipeline started on `main` with JOULE_TASK=heavy-scan
- **Wed 09:00 UTC** — **Shipped** · 0.080 kWh in `europe-southwest1`, **0.9 gCO₂e** on the decision signal vs 20.3 g had it run when filed (-96%). 100% of it in surplus hours. Waited 14.5 h; deadline met.

## #21 Production returns 500 on /api/grid

- **Tue 18:20 UTC** — filed and triaged: priority::critical, energy::agent_session, surge::queued
- **Tue 18:20 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — critical work never waits for me. Running now at **490 gCO₂/kWh**; waiting until Wed 07:50 UTC would have saved about **111.8 g**. Logged in the ledger as the price of urgency.
- **Tue 18:20 UTC** — Surge Worker flow started through the Flows API (hands-off, no user prompts)
- **Tue 19:00 UTC** — **Shipped** · 0.233 kWh in `europe-southwest1`, **114.3 gCO₂e** on the decision signal vs 114.3 g had it run when filed (no difference). 0% of it in surplus hours. Waited 0.0 h; deadline met.

## #22 Add a retry budget to the Energy-Charts adapter

- **Wed 05:50 UTC** — filed and triaged: priority::high, energy::agent_session, surge::queued
- **Wed 05:50 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **490 gCO₂/kWh**. I'm holding this Surge Request until **Wed 07:50 UTC**, when I expect **11 gCO₂/kWh** (≈98% less). Deadline Wed 10:30 UTC is safe.
- **Wed 08:00 UTC** — **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing 1 queued Surge Request(s) now: marginal ≈ **11 gCO₂/kWh**. Day-ahead price is **0.0 €/MWh** — clean power is in surplus.
- **Wed 08:00 UTC** — Surge Worker flow started through the Flows API (hands-off, no user prompts)
- **Wed 08:40 UTC** — **Shipped** · 0.233 kWh in `europe-southwest1`, **2.6 gCO₂e** on the decision signal vs 114.3 g had it run when filed (-98%). 100% of it in surplus hours. Waited 2.2 h; deadline met.

