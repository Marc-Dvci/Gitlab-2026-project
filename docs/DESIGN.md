# Joule Thief — design document

> **Joule Thief** · *Just-in-time Orchestration Using Leftover Energy*
> Hands-off agents that run the post-code lifecycle on the energy the grid throws away.
> **The backlog is a battery.**

GitLab Transcend Hackathon "Life After Code" · Path A (Start Fresh) · Hands-off autonomy.
Also entered for Most Environmentally Impactful, Most Creative and Most Stages Covered.

---

## 1. The name

A *joule thief* is a tiny electronics circuit, a favourite of hardware hackers, that squeezes
the last useful energy out of batteries everyone else considers dead. This project does the same
with electricity grids: it schedules the deferrable part of software delivery into the hours when
clean power would otherwise be wasted (curtailed wind, negative-price solar).

The backronym, **J.O.U.L.E. — Just-in-time Orchestration Using Leftover Energy**, is the whole idea
in five words. The vocabulary that goes with it:

| Term | Meaning |
|---|---|
| **Surge Request** | A deferrable issue or merge request waiting for a clean-power window (pun on *merge request*). |
| **@grid** | The electricity grid, given a seat at code review. It comments on issues with real numbers. |
| **Carbon blame** | `git blame` for grams of CO₂: joules per request per source line, tied to the commit that added it. |
| **Carbon receipt** | A Sigstore-signed in-toto attestation on every image: energy, both carbon ledgers, water, verdict. |
| **The carbon dividend of autonomy** | The extra emissions hands-off autonomy saves compared with supervised autonomy. Measured, not claimed. |

## 2. The problem

1. **"Life After Code" puts an agent in every stage, and agents are energy-hungry.** The Green
   Software Foundation reports that agentic coding consumes up to 1000× more tokens than chat, with
   30× run-to-run variance and no accuracy gain beyond a point
   ([Tokens and Greens](https://greensoftware.foundation/articles/tokens-and-greens-measuring-the-impacts-of-agentic-ai/)).
   IEA expects data-centre electricity to grow from ~415 TWh (2024) to ~945 TWh (2030).
2. **Grids are throwing clean power away.** Britain curtailed a record 10 TWh of renewables in
   2025 and paid £363 m to do it; Finland had 724 negative-price hours in 2024 and 447 in 2025;
   Spain's day-ahead price was at or below zero for **760 hours between January and September 2025**
   (counted in our snapshot of OMIE data).
3. **Existing carbon tooling for CI/CD reports but does not act, and mostly uses the wrong number.**
   The previous GitLab AI Hackathon had 70+ sustainability entries; the winners (GreenPipe, Carbon
   Tracker, CarbonLint) estimate pipeline footprints and suggest optimisations. GitLab now documents
   Eco CI natively. Nearly all of them schedule or compare on *average* grid intensity, which can
   move load to "clean-looking" hours while a gas plant still answers the extra demand.

## 3. The insight

**Hands-off agents are the most flexible electricity load ever created.** They don't sleep, don't
need daylight, and most of their work isn't urgent: dependency upgrades, test-matrix runs, fuzzing,
refactors, full security scans. A human-supervised workflow must happen while someone is awake to
approve it; a hands-off one can follow the wind.

So autonomy is not only a speed feature, it is a **climate feature**: the more of the lifecycle
runs hands-off, the more of its energy can be moved into surplus hours. Joule Thief treats the
backlog of deferrable post-code work like a battery: it charges (work accumulates) while the grid
is dirty and discharges (agents and pipelines run) when clean power is in surplus. Critical work
never waits.

## 4. Measured results (real grid data, reproducible)

From `experiments/autonomy_dividend.py`. The backlog is synthetic and reproducible; the grids are real.

| Grid | Supervised vs run-now | Hands-off vs run-now | **Dividend of autonomy** | Late jobs (supervised / hands-off) |
|---|---:|---:|---:|---:|
| GB, NESO, Sep–Oct 2026 (average signal, real forecasts) | −18.6 % | −24.9 % | **6.3 %** | 9 / 0 |
| Spain, OMIE, Mar–May 2025 (marginal price heuristic) | −25.3 % | −34.0 % | **8.7 %** | 22 / 0 |
| Spain, OMIE, Jul–Sep 2025 | −23.6 % | −31.1 % | **7.4 %** | 27 / 0 |

Hands-off saves 25–34 % of emissions against running work the moment it is filed, misses no
deadlines, and beats supervised autonomy by 6–9 points of baseline emissions, while supervised
misses 9–27 deadlines. Details: [`results/autonomy_dividend.md`](results/autonomy_dividend.md).

**Forecast uncertainty is calibrated, not assumed.** NESO publishes forecasts without error bars;
from the archived forecast history we fit split-conformal intervals per lead time (±45–51 g/kWh at
90 %). Static calibration under-covers at long leads (81 % at 47 h) because errors drift;
recalibrating on a rolling 14-day window brings coverage back to 87–92 %.

**Average and marginal disagree, sometimes by 20×.**
[`results/region_ledgers.md`](results/region_ledgers.md): Finland (`europe-north1`) is 39 g/kWh
on average but ~785 g/kWh on the margin (GSF/WattTime annual figure), higher than South Carolina's
728. Moving work to Finland is only a real win in surplus hours. That is why Joule Thief decides on
marginal and surplus signals, and why every claim of *avoided* emissions is consequential.

## 5. Architecture

```
            ┌────────────────────────── GitLab ───────────────────────────┐
 human ───▶ │ Issue ──(Work item created)──▶ Surge Intake flow ──▶ labels  │
 files      │   priority::*, energy::*, surge::queued                      │
 an issue   │                                                               │
            │ Dispatcher tick (Cloud Scheduler → Cloud Run, or schedule)    │
            │   ├─ reads Surge Requests (issues)                           │
            │   ├─ fetches grid signals (Energy-Charts, NESO, Open-Meteo)   │
            │   ├─ CP-SAT plan under SLAs + virtual capacity curve          │
            │   ├─ @grid note on every hold / release                       │
            │   └─ window open → Flows API: start "surge-worker" flow      │
            │                   or API pipeline JOULE_TASK=heavy-*         │
            │ Surge Worker flow (small model explores, large implements)   │
            │   └─ MR ──▶ CI: test · energy benchmark · scanners ·          │
            │            image · carbon receipt (Sigstore) · receipt gate · │
            │            Cloud Run canary · energy-regression gate ·        │
            │            promote · release · footprint ledger · compliance │
            │ Carbon Reviewer flow on MR · Retry Guard on failed pipeline  │
            │ Release Captain posts the carbon balance on the closed issue │
            └───────────────────────────────────────────────────────────────┘
                       │ MCP (streamable HTTP)            ▲ feature flag eco-mode
                       ▼                                  │
            ┌─ Google Cloud (free tier) ─────────────────────────────────────┐
            │ Cloud Run europe-north1: control room + MCP server + /api/tick │
            │ Artifact Registry (cleanup policy) · Workload Identity Fed.    │
            │ Cloud Scheduler (tick) · Secret Manager · optional e2-micro    │
            └────────────────────────────────────────────────────────────────┘
```

Why the dispatcher uses the Flows API: GitLab triggers require a human action; a bot or another
flow cannot trigger a flow by mention (documented restriction). So the hands-off loop starts flows
directly with `POST /ai/duo_workflows/workflows` (`start_workflow: true`,
`allow_agent_to_request_user: false`) when the window opens.

## 6. The nine stages

| Stage | What runs | GitLab features |
|---|---|---|
| **Plan** | Surge Intake flow triages; dispatcher plans on the grid; plan published as an issue; @grid comments | Custom flow (Work item trigger), labels, issues, Flows API, schedules |
| **Create** | Surge Worker flow implements the issue in a clean window; small→large model routing; loop caps as token budget | Custom flow (`model_tags`, `max_cycles`), Flows API, MR |
| **Verify** | Tests; energy benchmark with joules/request as a **metrics report**; carbon blame artifact; Carbon Reviewer flow; Retry Guard on failures; deferred test matrix | CI, metrics reports, `expose_as`, MR-created and pipeline-failed triggers |
| **Package** | Slim image; push to GitLab registry and Artifact Registry; container scanning; registry cleanup | Container registry, Container Scanning |
| **Secure** | SAST, secret detection, dependency scanning; heavy scans deferred to clean windows | Security templates, vulnerability report |
| **Release** | Carbon receipt signed keylessly (Sigstore + GitLab OIDC); **receipt gate**; Cloud Run canary; GitLab release | id_tokens, cosign, environments, releases (evidence) |
| **Configure** | OpenTofu with GitLab-managed state; eco-mode feature flag flipped from the grid signal (demand shaping) | Terraform state, Feature Flags (Unleash API), schedules |
| **Monitor** | Canary vs production joules/request; energy regression blocks promotion and opens an incident issue | Environments, deployments, issues |
| **Govern** | Pipeline-wide footprint ledger (one job, all jobs incl. retries); carbon budget reported as a compliance **external control**; audit artifacts | Compliance centre external controls (HMAC API), artifacts |

## 7. Engineering that few teams can do

1. **Marginal and surplus signals, not averages.** A transparent price→marginal model for European
   bidding zones (negative/zero price ⇒ surplus; high price ⇒ the zone's fossil margin, set from the
   GSF/WattTime annual marginal when known), WattTime MOER when a free account is configured, NESO
   average for GB flagged as a proxy. Day-ahead prices are *market results*, published a day ahead —
   a forecast with no forecast error.
2. **Google's carbon-intelligent computing method, applied to GitLab.** OR-Tools CP-SAT
   dispatch with release times, deadlines from priority labels, a defer option valued at the zone's
   typical emissions, office-hours masks for supervised autonomy, and per-region concurrency from a
   **virtual capacity curve** (Radovanović et al., Google) that prevents herding into one hour.
3. **Receding-horizon evaluation without look-ahead.** The simulator gives the dispatcher only
   forecasts at the right lead time (never fresher), and Spanish prices only after the ~13:00 CET
   publication.
4. **Split-conformal forecast intervals** calibrated on NESO's archived forecasts, with rolling
   recalibration to handle drift.
5. **SCI for AI on the agents themselves.** EcoLogits ranges for energy, carbon and water per LLM
   call; input and output tokens tracked separately; trace-based reconstruction of the quadratic
   context growth of Duo sessions when token counts are not exposed.
6. **Carbon blame.** An in-process sampling profiler (works on Cloud Run, no eBPF) ties CPU samples
   to request threads, converts to joules per request per line, scales by traffic and intensity into
   g/day, and maps lines to commits with `git blame`. The same arithmetic projects an MR's production
   impact: Δ J/request × requests/day × intensity.
7. **Carbon receipts.** in-toto Statement v1 with a custom predicate, signed keylessly with Sigstore
   from GitLab OIDC, recorded in Rekor, verified by a release gate that also checks budget, ranges and
   signal freshness. Anyone can verify a claim with `cosign verify-attestation`.
8. **Water as a second objective.** Onsite WUE varies with temperature (solar noon is clean *and*
   thirsty); Hamina is seawater-cooled. Water is computed per entry and reported next to carbon.

## 8. Sustainability practices in the design itself

- **Deterministic first, LLM last.** @grid messages, plans, footprints and receipts involve no LLM.
- **Model routing.** Every flow component declares `model_tags`; triage, review, retry diagnosis and
  release notes use the small model; only implementation uses the large one.
- **Token budgets.** `max_cycles` and `identical_tool_call_limit` cap loops; `coding_environment: none`
  avoids cloning the repository for API-only flows.
- **No blind retries.** Retry Guard classifies failures; only infrastructure failures are retryable.
- **Interruptible pipelines + auto-cancel** stop superseded work; one job accounts for the whole
  pipeline instead of instrumenting every job.
- **Scale to zero** on Cloud Run with CPU only during requests, no startup boost; registry cleanup.
- **Low-carbon home region** (`europe-north1`, 98 % CFE) and an optional always-free e2-micro runner in
  Oregon (79 g/kWh) instead of hosted runners in South Carolina (576 g/kWh).
- **Demand shaping.** The eco-mode flag lengthens caches and turns the profiler off when the grid is dirty.

## 9. Zero-cost plan

| Need | Free option used |
|---|---|
| Grid prices & generation (EU) | Energy-Charts API (no key, CC BY 4.0) |
| GB intensity + 48 h forecast | NESO Carbon Intensity API (no key) |
| Weather (cooling water) | Open-Meteo (no key) |
| Region carbon, PUE, marginal | Google region-carbon-info (Apache-2.0), GSF Real Time Cloud (fetched at run time) |
| LLM footprint | EcoLogits (open source) |
| Optional richer signals | ENTSO-E token (free), WattTime account (free plan), Fingrid key (free) |
| Compute | Cloud Run free tier, Cloud Scheduler 3 free jobs, e2-micro always free, GitLab CI minutes |
| Secrets & auth | Workload Identity Federation (no keys), Secret Manager free tier |
| Signing | Sigstore public good instance (free) |
| Agents | GitLab Duo Agent Platform (hackathon credits) |

Every piece runs inside a free tier. Set a $1 billing budget alert as a safety net (see SETUP.md).

## 10. Honest limitations

- CPU energy on cloud VMs and LLM energy are **modelled** (CCF coefficients, EcoLogits), always shown as ranges.
- The price→marginal mapping is a documented heuristic; replace it with WattTime MOER where available.
- Provider-hosted LLM inference happens where the provider runs it; shifting agent sessions in time
  changes their footprint only for self-hosted or region-pinned models. The ledger labels which is which.
- GB curtailment is mostly behind the Scotland–England constraint; load in London does not absorb it.
- The experiment backlog is synthetic (seeded, reproducible); emissions are scored on real grid data.
- Profiler line shares are wall-clock samples (I/O wait counts); per-endpoint CPU time is exact.

## 11. Plan to submission (Oct 27, 13:00 UTC)

| Week | Deliverable |
|---|---|
| Oct 6–12 | Mirror to GitLab, onboarding, CI green, Cloud Run deployed, flows created and triggers set |
| Oct 13–19 | Live tick against real Surge Requests; capture real negative-price windows in Finland/Spain; first receipts |
| Oct 20–25 | Seeded backlog fixed by agents end to end; ledger and dashboard polish; video recorded |
| Oct 26–27 | Submission text (Devpost), environmental opt-in write-up from `METHODOLOGY.md` |
