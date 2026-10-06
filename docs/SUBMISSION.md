# Devpost submission — draft

Paste-ready text for the GitLab Transcend *Life After Code* entry. Every number links back to a
generated result in this repository; regenerate them before submitting if the code changes.

- **Title:** Joule Thief — the backlog is a battery
- **Tagline:** Hands-off GitLab Duo agents that run the post-code lifecycle on the energy the grid throws
  away. Critical work never waits.
- **Path:** A (start fresh) · autonomy level: hands-off
- **Prizes entered:** Best hands-off agent · Most Environmentally Impactful · Most Creative · Most Stages Covered · Google Cloud
- **Links:** GitLab project `<url>` · live control room `<cloud run url>` · video `<youtube url>`
- **Cover image:** [`img/cover.png`](img/cover.png) (3:2) · gallery: [`img/battery-replay.png`](img/battery-replay.png) and stills from `python scripts/video/make_video.py --stills-only --still <scene>`
- **Video:** `python scripts/video/make_video.py` (edge-tts narration, burned-in captions, `.srt` for YouTube); see [DEMO.md](DEMO.md)
- **Built with:** python, fastapi, or-tools (CP-SAT), ecologits, model-context-protocol, gitlab-duo-agent-platform,
  gitlab-ci, gitlab-feature-flags, google-cloud-run, cloud-scheduler, workload-identity-federation, opentofu,
  sigstore, cosign, in-toto, playwright

---

## Inspiration

"Life After Code" puts an agent in every stage of delivery, and every agent burns energy: the Green
Software Foundation measures agentic coding at up to 1000× the tokens of a chat. At the same time,
grids are throwing clean power away. Spain's day-ahead price was at or below zero for 760 hours between
January and September 2025; Britain curtailed a record 10 TWh of renewables in 2025.

Most of an agent's post-code work is not urgent: dependency upgrades, test matrices, full scans,
refactors. A human-supervised workflow has to happen while someone is awake to approve it. A hands-off
one can follow the wind. So we asked: **is autonomy a climate feature?** And can we measure it?

## What it does

Joule Thief treats the backlog of deferrable post-code work as a battery. It charges while the grid
is dirty and discharges when clean power is in surplus. Critical work never waits.

1. **Surge Intake** (Duo flow, *work item created* trigger) triages each new issue: priority, kind of
   work, whether it can wait. It becomes a *Surge Request*.
2. **The dispatcher** (every 30 minutes, and within seconds of a GitLab issue webhook) plans the backlog
   with OR-Tools CP-SAT on marginal and surplus signals (day-ahead prices, NESO, WattTime), under each
   issue's deadline, using Google's virtual-capacity-curve method to avoid herding.
3. **@grid**, the electricity grid with a seat at code review, explains every hold and release on the
   issue with numbers, deterministically and with no LLM: *"I'm holding this Surge Request until Tue
   08:10, when I expect 11 gCO₂/kWh (≈97 % less). Deadline Tue 19:50 is safe."* For critical work it logs
   the price of urgency: what waiting would have saved.
4. When the window opens, the dispatcher **starts the Surge Worker Duo flow through the Flows API**
   (bots cannot trigger flows by mention). A small model explores and a large model implements, with
   loop caps as a token budget. Deferred CI work (test matrices, DAST) runs as API pipelines.
5. Every merge request is measured: **joules per request as a GitLab metrics report** and **carbon blame**,
   `git blame` for grams of CO₂ per source line. **Carbon Reviewer** (Duo flow) reads both.
6. Every image gets a **Sigstore-signed in-toto carbon receipt** (energy, attributional and consequential
   carbon, water, the agents' own footprint). No valid receipt inside the budget means no deploy. A Cloud
   Run canary that is hungrier per request than production is not promoted.
7. **Release Captain** closes the issue with its carbon balance. **Retry Guard** stops blind retries. The
   carbon budget is a **compliance-centre external control**.

The pipeline covers all nine stages: plan, create, verify, package, secure, release, configure,
monitor and govern.

## How we built it

Python 3.11+ with the standard library first. FastAPI serves the control room and mounts an **MCP
server** with six tools (grid signal, plan work, agent footprint, region explainer, receipt check, the
dividend) that Duo agents call. OR-Tools CP-SAT does the dispatch. EcoLogits supplies the LLM footprint.
OpenTofu builds a $0 Google Cloud footprint: Cloud Run scaled to zero in `europe-north1`, Cloud Scheduler,
Secret Manager and keyless Workload Identity Federation. Five custom Duo flows and two custom agents live
in `.gitlab/duo/`.

To keep ourselves honest we built three evaluation tools:
- a **receding-horizon simulator** that gives the dispatcher only what it would have known at the time:
  NESO forecasts at the right lead, and Spanish prices only after their ~13:00 publication;
- **`joule demo`**, which drives the *production* tick against an in-memory GitLab over a real week of
  grid data, so @grid's numbers and every "Shipped" balance are tested end to end. It needs no accounts
  and runs in about a second;
- a **robustness study** over five seeded backlogs and four assumptions in the price-to-marginal model.

## Challenges we ran into

- **Our own headline was inflated, and we published the smaller number.** Running the real loop end to
  end showed two problems. The planner billed a 40-minute job as a full hour, which quietly made deferral
  stricter than designed. And the live tick started work up to 30 minutes early, in a dirtier slot than
  planned. Fixing both cut our "carbon dividend of autonomy" from 6.3–8.7 % to 4.9–6.8 %. The hands-off
  savings still hold, and the live loop now does exactly what the simulator measures.
- **Bots cannot trigger flows**, so the dispatcher starts them through the Flows API, and a GitLab
  webhook makes the loop event-driven so that critical work starts within seconds.
- **Averages lie.** Finland is 39 g/kWh on average but about 785 g/kWh on the margin. Scheduling on
  averages moves load into hours that only look clean, so every decision uses marginal or surplus
  signals.
- **Forecasts have no error bars.** We calibrated split-conformal intervals on NESO's archive. Rolling
  recalibration fixes the under-coverage at long lead times (from 81 % to 87 %).

## Accomplishments that we're proud of

- **Hands-off saves 25–32 % of emissions on real grids and missed no deadline in any run**, while
  supervised autonomy missed 8–24. Results: [`results/autonomy_dividend.md`](results/autonomy_dividend.md),
  [`results/robustness.md`](results/robustness.md).
- A replayed week in Madrid: 30 issues, 30 shipped, 0 late, **−60 % CO₂** against running each task when
  filed, and **91 %** of the energy used in surplus hours ([transcript](results/hands_off_replay.md)).
- Carbon receipts that anyone can check with `cosign verify-attestation`.
- Setup in one command (`joule bootstrap`) and a try-it in one more (`joule demo`).

## What we learned

Autonomy pays a climate dividend only if the agent may *wait*. The gap between supervised and hands-off
autonomy is real (2–9 points of baseline emissions across backlogs). It depends on the grid and the
season, so we report it as a range, never as one number.

## What's next

WattTime MOER where it is available; spot capacity for deferrable work; and self-hosted, region-pinned
models so that agent inference itself can follow the wind, not only CI. Today provider-hosted inference
runs where the provider runs it, and the ledger says so.

---

## Environmental impact (Most Environmentally Impactful)

**Standards.** SCI (ISO/IEC 21031:2024), `SCI = ((E × I) + M) / R`, and the GSF **SCI for AI** for the
agents themselves (EcoLogits ranges, consumer boundary). There are two ledgers. The *attributional*
ledger uses location-based averages and is for reports. The *consequential* ledger uses marginal signals
and is for decisions; it is the only basis for "avoided" emissions. Full method:
[`METHODOLOGY.md`](METHODOLOGY.md).

**SCI per Surge Request** (R = one deferrable work item; E and I from the experiments; consequential;
operational only). Time-shifting runs the same work on the same hardware, so the embodied term M does
not change, and every gain comes from I.

| Grid (real data) | Run when filed | Hands-off (Joule Thief) | Change | Effective marginal intensity |
|---|---:|---:|---:|---:|
| Great Britain, Sep–Oct 2026 | 15.9 g | 11.9 g | −24.9 % | 105 → 79 g/kWh |
| Spain, Mar–May 2025 | 18.1 g | 12.4 g | −31.6 % | 120 → 82 g/kWh |
| Spain, Jul–Sep 2025 | 44.5 g | 31.7 g | −28.8 % | 293 → 209 g/kWh |

Put per unit of energy: **every MWh of deferrable delivery compute that Joule Thief schedules avoids
about 26–84 kg CO₂e** on the margin, with no missed deadlines. Across five seeded backlogs, hands-off cuts
emissions by 22–33 %. Across price-model assumptions from 20 to 80 €/MWh, it cuts Spanish emissions by
22–38 %.

**Practices in the system itself.** Deterministic first, LLM last: @grid, plans, footprints and
receipts use no LLM. Every flow declares small or large models, loop caps act as token budgets, and
`coding_environment: none` is set where no clone is needed. Retry Guard prevents blind retries. Pipelines
are interruptible and auto-cancel superseded runs. Cloud Run scales to zero in a 98 % CFE region. An
eco-mode feature flag shapes the app's own demand when the grid is dirty. The MCP tools are cheap,
deterministic and cached.

**Honest limitations.** Cloud CPU energy and LLM energy are modelled, not measured, and always shown as
ranges. The price-to-marginal mapping is a documented heuristic, and its sensitivity is published. The
GB signal is an average used as a proxy. The experiment backlogs are synthetic; the grids are real.
