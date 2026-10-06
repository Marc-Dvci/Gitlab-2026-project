# The hands-off loop, replayed on a real week (generated)

Generated 2026-10-06T13:53:17+00:00 by `experiments/loop_replay.py`: `joulethief.loop.tick` every 30 minutes, unchanged (plus a webhook tick when an issue is filed), against an in-memory GitLab, on OMIE day-ahead prices for Mon 12 May 00:00 – Wed 21 May 00:00 (Madrid time; prices revealed only after each day's publication).

**15 issues, 15 finished, 0 late. 133 gCO₂e versus 226 g if each had run the moment it was filed (-41%).** 19 @grid notes, 9 Duo flows and 6 pipelines started by the loop; 432 scheduled ticks and 15 webhook ticks; the loop itself made 0 LLM calls.

| # | Issue | Priority | Kind | Filed | Started | Waited (h) | g | g if run on filing |
|---:|---|---|---|---|---|---:|---:|---:|
| 1 | Upgrade FastAPI and uvicorn to the latest patch releases | low | dependency_upgrade | Mon 12 May 09:40 | Mon 12 May 10:00 | 0.33 | 2.89 | 12.32 |
| 2 | Dashboard comparison is slow | low | agent_session | Mon 12 May 11:15 | Mon 12 May 11:15 | 0.0 | 2.57 | 2.57 |
| 3 | Run the full test matrix on Python 3.11–3.13 | normal | ci_pipeline | Mon 12 May 15:30 | Mon 12 May 15:30 | 0.0 | 0.18 | 0.18 |
| 4 | Nightly DAST scan of the control room | low | security_scan | Tue 13 May 10:05 | Tue 13 May 11:00 | 0.92 | 0.88 | 2.03 |
| 5 | Retry Open-Meteo with backoff | normal | agent_session | Tue 13 May 13:20 | Tue 13 May 13:20 | 0.0 | 2.57 | 2.57 |
| 6 | Bump ortools to 9.15.x | low | dependency_upgrade | Tue 13 May 17:45 | Wed 14 May 11:00 | 17.25 | 2.89 | 80.53 |
| 7 | Production: /api/grid returns 500 for europe-west2 | critical | agent_session | Wed 14 May 08:50 | Wed 14 May 08:50 | 0.0 | 108.19 | 108.19 |
| 8 | Fuzz the receipt verifier | low | security_scan | Wed 14 May 12:30 | Wed 14 May 12:30 | 0.0 | 0.88 | 0.88 |
| 9 | Rerun the autonomy experiment on September data | low | ci_pipeline | Wed 14 May 16:10 | Wed 14 May 16:10 | 0.0 | 0.18 | 0.18 |
| 10 | Cache region metadata between ticks | normal | agent_session | Thu 15 May 09:30 | Thu 15 May 10:00 | 0.5 | 2.57 | 7.48 |
| 11 | Container scan with the full vulnerability database | normal | security_scan | Thu 15 May 14:00 | Thu 15 May 14:00 | 0.0 | 0.88 | 0.88 |
| 12 | Upgrade mcp to 2.4 | normal | dependency_upgrade | Thu 15 May 17:30 | Thu 15 May 17:30 | 0.0 | 2.89 | 2.89 |
| 13 | Document the price-knee sensitivity | low | agent_session | Fri 16 May 10:20 | Fri 16 May 10:20 | 0.0 | 2.57 | 2.57 |
| 14 | Load-test the canary | high | ci_pipeline | Fri 16 May 15:45 | Fri 16 May 15:45 | 0.0 | 0.18 | 0.18 |
| 15 | Refresh pinned dev dependencies | low | dependency_upgrade | Fri 16 May 17:50 | Fri 16 May 17:50 | 0.0 | 2.89 | 2.89 |

## What the grid said (transcript)

Times in bold are Madrid local time; @grid writes UTC.

- **Mon 12 May 09:40** · #1 *Upgrade FastAPI and uvicorn to the latest patch releases* filed with `priority::low`, `energy::dependency_upgrade`, `surge::queued`
  - Mon 12 May 09:40 · on #1: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **83 gCO₂/kWh**. I'm holding this Surge Request until **Mon 08:10 UTC**, when I expect **11 gCO₂/kWh** (≈87% less). Deadline Thu 08:25 UTC is safe.
  - Mon 12 May 10:00 · #1: Surge Worker flow started (Flows API)
  - Mon 12 May 10:00 · on #1: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Mon 12 May 10:45 · #1 *Upgrade FastAPI and uvicorn to the latest patch releases* done: 2.89 g (if run on filing: 12.32 g)
- **Mon 12 May 11:15** · #2 *Dashboard comparison is slow* filed with `priority::low`, `energy::agent_session`, `surge::queued`
  - Mon 12 May 11:15 · #2: Surge Worker flow started (Flows API)
  - Mon 12 May 11:15 · on #2: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Mon 12 May 11:55 · #2 *Dashboard comparison is slow* done: 2.57 g (if run on filing: 2.57 g)
- **Mon 12 May 15:30** · #3 *Run the full test matrix on Python 3.11–3.13* filed with `priority::normal`, `energy::ci_pipeline`, `surge::queued`
  - Mon 12 May 15:30 · #3: pipeline `JOULE_TASK=heavy-tests` started
  - Mon 12 May 15:30 · on #3: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Mon 12 May 15:50 · #3 *Run the full test matrix on Python 3.11–3.13* done: 0.18 g (if run on filing: 0.18 g)
- **Tue 13 May 10:05** · #4 *Nightly DAST scan of the control room* filed with `priority::low`, `energy::security_scan`, `surge::queued`
  - Tue 13 May 10:05 · on #4: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **25 gCO₂/kWh**. I'm holding this Surge Request until **Tue 09:05 UTC**, when I expect **11 gCO₂/kWh** (≈57% less). Deadline Fri 09:05 UTC is safe.
  - Tue 13 May 11:00 · #4: pipeline `JOULE_TASK=heavy-scan` started
  - Tue 13 May 11:00 · on #4: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Tue 13 May 12:00 · #4 *Nightly DAST scan of the control room* done: 0.88 g (if run on filing: 2.03 g)
- **Tue 13 May 13:20** · #5 *Retry Open-Meteo with backoff* filed with `priority::normal`, `energy::agent_session`, `surge::queued`
  - Tue 13 May 13:20 · #5: Surge Worker flow started (Flows API)
  - Tue 13 May 13:20 · on #5: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Tue 13 May 14:00 · #5 *Retry Open-Meteo with backoff* done: 2.57 g (if run on filing: 2.57 g)
- **Tue 13 May 17:45** · #6 *Bump ortools to 9.15.x* filed with `priority::low`, `energy::dependency_upgrade`, `surge::queued`
  - Tue 13 May 17:45 · on #6: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **19 gCO₂/kWh**. I'm holding this Surge Request until **Wed 08:45 UTC**, when I expect **11 gCO₂/kWh** (≈41% less). Deadline Fri 16:30 UTC is safe.
- **Wed 14 May 08:50** · #7 *Production: /api/grid returns 500 for europe-west2* filed with `priority::critical`, `energy::agent_session`, `surge::queued`
  - Wed 14 May 08:50 · #7: Surge Worker flow started (Flows API)
  - Wed 14 May 08:50 · on #7: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — critical work never waits for me. Running now at **490 gCO₂/kWh**; waiting until Wed 08:50 UTC would have saved about 105.6 g. That's the price of urgency, and it's in the ledger.
  - Wed 14 May 09:30 · #7 *Production: /api/grid returns 500 for europe-west2* done: 108.19 g (if run on filing: 108.19 g)
  - Wed 14 May 11:00 · #6: Surge Worker flow started (Flows API)
  - Wed 14 May 11:00 · on #6: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Wed 14 May 11:45 · #6 *Bump ortools to 9.15.x* done: 2.89 g (if run on filing: 80.53 g)
- **Wed 14 May 12:30** · #8 *Fuzz the receipt verifier* filed with `priority::low`, `energy::security_scan`, `surge::queued`
  - Wed 14 May 12:30 · #8: pipeline `JOULE_TASK=heavy-scan` started
  - Wed 14 May 12:30 · on #8: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Wed 14 May 13:30 · #8 *Fuzz the receipt verifier* done: 0.88 g (if run on filing: 0.88 g)
- **Wed 14 May 16:10** · #9 *Rerun the autonomy experiment on September data* filed with `priority::low`, `energy::ci_pipeline`, `surge::queued`
  - Wed 14 May 16:10 · #9: pipeline `JOULE_TASK=heavy-tests` started
  - Wed 14 May 16:10 · on #9: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Wed 14 May 16:30 · #9 *Rerun the autonomy experiment on September data* done: 0.18 g (if run on filing: 0.18 g)
- **Thu 15 May 09:30** · #10 *Cache region metadata between ticks* filed with `priority::normal`, `energy::agent_session`, `surge::queued`
  - Thu 15 May 09:30 · on #10: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — one more kWh here right now would be answered at about **53 gCO₂/kWh**. I'm holding this Surge Request until **Thu 08:00 UTC**, when I expect **11 gCO₂/kWh** (≈79% less). Deadline Fri 08:10 UTC is safe.
  - Thu 15 May 10:00 · #10: Surge Worker flow started (Flows API)
  - Thu 15 May 10:00 · on #10: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Thu 15 May 10:40 · #10 *Cache region metadata between ticks* done: 2.57 g (if run on filing: 7.48 g)
- **Thu 15 May 14:00** · #11 *Container scan with the full vulnerability database* filed with `priority::normal`, `energy::security_scan`, `surge::queued`
  - Thu 15 May 14:00 · #11: pipeline `JOULE_TASK=heavy-scan` started
  - Thu 15 May 14:00 · on #11: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Thu 15 May 15:00 · #11 *Container scan with the full vulnerability database* done: 0.88 g (if run on filing: 0.88 g)
- **Thu 15 May 17:30** · #12 *Upgrade mcp to 2.4* filed with `priority::normal`, `energy::dependency_upgrade`, `surge::queued`
  - Thu 15 May 17:30 · #12: Surge Worker flow started (Flows API)
  - Thu 15 May 17:30 · on #12: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Thu 15 May 18:15 · #12 *Upgrade mcp to 2.4* done: 2.89 g (if run on filing: 2.89 g)
- **Fri 16 May 10:20** · #13 *Document the price-knee sensitivity* filed with `priority::low`, `energy::agent_session`, `surge::queued`
  - Fri 16 May 10:20 · #13: Surge Worker flow started (Flows API)
  - Fri 16 May 10:20 · on #13: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Fri 16 May 11:00 · #13 *Document the price-knee sensitivity* done: 2.57 g (if run on filing: 2.57 g)
- **Fri 16 May 15:45** · #14 *Load-test the canary* filed with `priority::high`, `energy::ci_pipeline`, `surge::queued`
  - Fri 16 May 15:45 · #14: pipeline `JOULE_TASK=heavy-tests` started
  - Fri 16 May 15:45 · on #14: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Fri 16 May 16:05 · #14 *Load-test the canary* done: 0.18 g (if run on filing: 0.18 g)
- **Fri 16 May 17:50** · #15 *Refresh pinned dev dependencies* filed with `priority::low`, `energy::dependency_upgrade`, `surge::queued`
  - Fri 16 May 17:50 · #15: Surge Worker flow started (Flows API)
  - Fri 16 May 17:50 · on #15: **@grid · Madrid (`europe-southwest1`, ES bidding zone)** — releasing this Surge Request now: one more kWh here is answered at about **11 gCO₂/kWh**, the best slot I can find before its deadline.
  - Fri 16 May 18:35 · #15 *Refresh pinned dev dependencies* done: 2.89 g (if run on filing: 2.89 g)

## The same backlog on other weeks

The week above was chosen before running it (the second-most surplus hours in the data, and not the week of the 28 April blackout). Here is the same backlog on the first full week of every month, so the spread is visible. The total moves mostly with where the one critical incident lands: it runs at once, whatever the grid.

| Week of | Surplus hours | @grid holds | Late | g | g if run on filing | Saving |
|---|---:|---:|---:|---:|---:|---:|
| 2025-03-03 | 0 | 7 | 0 | 822 | 1215 | -32% |
| 2025-04-07 | 42 | 7 | 0 | 122 | 331 | -63% |
| 2025-05-05 | 74 | 5 | 0 | 62 | 132 | -53% |
| 2025-06-02 | 39 | 9 | 0 | 139 | 411 | -66% |
| 2025-07-07 | 4 | 9 | 0 | 616 | 1011 | -39% |
| 2025-08-04 | 14 | 13 | 0 | 333 | 788 | -58% |
| 2025-09-01 | 25 | 9 | 0 | 84 | 577 | -85% |
