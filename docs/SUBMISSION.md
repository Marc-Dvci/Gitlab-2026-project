# Joule Thief — submission

**Just-in-time Orchestration Using Leftover Energy.** Hands-off agents that run the post-code lifecycle
on the energy the grid throws away. *The backlog is a battery.*

GitLab Transcend Hackathon *Life After Code* · Path A (start fresh) · hands-off autonomy · also entered for
Most Environmentally Impactful, Most Creative and Most Stages Covered · deployed on Google Cloud.

Links: repository · live control room `<Cloud Run URL>` · video `<video URL>`

---

## Inspiration

Life after code puts an agent in every stage, and agents are energy-hungry. Meanwhile grids throw clean
power away: Spain's day-ahead price was at or below zero for 760 hours between January and September
2025; Britain paid £363 m to curtail a record 10 TWh in 2025. A human-supervised workflow has to happen
while someone is awake. A hands-off one can follow the wind. **Autonomy is not only a speed feature, it
is a climate feature**, and nobody had measured it.

## What it does

1. A human files an issue with the **Surge Request** template; the **Surge Intake** Duo flow triages it
   (one call when the template already set the labels).
2. A GitLab issue webhook wakes the **dispatcher**, which also ticks every 30 min on Cloud Run. It plans
   the backlog with OR-Tools CP-SAT on the grid's *marginal* signal (day-ahead prices, NESO), under each
   issue's deadline, the way Google schedules its own data centres.
3. **@grid**, the electricity grid with a seat at code review, explains every hold and release on the
   issue, with numbers. Critical work never waits, and @grid says what urgency cost.
4. When the window opens, the dispatcher starts the **Surge Worker** Duo flow through the Flows API (or a
   deferred heavy pipeline). Nobody is awake. That's the point.
5. Every MR gets a deterministic **energy check** (joules/request vs the target branch, carbon blame per
   line); the **Carbon Reviewer** agent is woken only when the numbers regress or a hot line changes.
6. Every deployable image carries a Sigstore-signed **carbon receipt** (in-toto). No valid,
   within-budget receipt means no deploy. A Cloud Run canary hungrier than production is not promoted.
7. The pipeline accounts for itself (every job, retries included), reports the carbon budget as a
   **compliance external control**, and closes each issue with a **"Shipped"** note: its carbon balance.

## How we built it

Python 3.11+, standard library first. OR-Tools CP-SAT; EcoLogits for LLM footprints; Cloud Carbon
Footprint coefficients; Energy-Charts, NESO and Open-Meteo (free, no keys); FastAPI on Cloud Run with an
MCP server mounted for any agent; OpenTofu with GitLab-managed state; keyless Workload Identity Federation;
Sigstore keyless signing from GitLab OIDC. Every environmental number carries a low/likely/high range.

## Challenges we ran into

- **Our own footprint.** Measuring Joule Thief against itself showed that its first version could emit
  more than it saved when only CI work can move. We cut it: receipts only for deployable images, a script
  instead of an LLM for the "Shipped" note, the reviewer woken only by a measured regression, one-call
  triage (19 → 5 LLM calls per code change).
- **Testing a scheduler honestly.** Replaying the real loop on a real week exposed six bugs no unit test
  had: a planner that billed 40-minute jobs for 60, deferral that tied with running at the cleanest hour,
  work started half an hour early in a dirtier slot, critical work waiting for the next tick, and two
  wrong @grid sentences. All fixed, all regression-tested, all results regenerated.

## Accomplishments we're proud of

- **The carbon dividend of autonomy, measured on real grids** — same backlog, same deadlines:

  | Grid | Supervised vs run-now | Hands-off vs run-now | Dividend of autonomy | Late (supervised / hands-off) |
  |---|---:|---:|---:|---:|
  | Great Britain, Sep–Oct 2026 (NESO) | −17.9 % | −24.9 % | 6.9 % | 10 / 0 |
  | Spain, spring 2025 (OMIE) | −26.5 % | −34.2 % | 7.8 % | 22 / 0 |
  | Spain, summer 2025 (OMIE) | −20.5 % | −30.6 % | 10.2 % | 29 / 0 |

- **It pays for itself, and we can say by how much** ([net impact](results/net_impact.md)).
- **It survives its critics** ([robustness](results/robustness.md)): the dividend is positive in all 15
  runs (3 grids × 5 backlogs, 3.3–11.0 %) and hands-off never misses a deadline while supervised misses
  5–29 per run; deciding with a wrong price model still cuts 22–39 %; and with no carbon model at all,
  hands-off pays about a third less for its electricity on the day-ahead market (Spain, spring:
  14.5 → 9.5 €/MWh; summer: 34.0 → 23.3 €/MWh).
- **Anyone can use the idea in six lines**: the `grid-window` CI/CD Catalog component holds a project's
  deferrable jobs behind a `when: delayed` job until the cleanest start before a deadline. No agents,
  no cloud.

## What we learned

Averages lie: Finland is 39 g/kWh on average and ~785 g/kWh on the margin. A carbon tool must decide on
the margin and report both ledgers. And an agentic system's first sustainability practice is to not call
an agent: deterministic first, LLM last.

## What's next

GitLab Duo Self-Hosted so inference can be scheduled too; WattTime MOER for more US regions (wired in,
but the free plan covers few); the grid-window component in the CI/CD Catalog.

---

## Judging criteria → evidence

| Criterion | Where to look |
|---|---|
| **Technological implementation** | 9 stages in [`.gitlab-ci.yml`](../.gitlab-ci.yml) · 4 custom Duo flows and 2 agents in [`.gitlab/duo/`](../.gitlab/duo/) · Flows API from the dispatcher and the MR energy gate ([`joulethief/loop.py`](../joulethief/loop.py), [`joulethief/cli.py`](../joulethief/cli.py)) · issue webhook ([`app/main.py`](../app/main.py)) · CP-SAT planner ([`joulethief/dispatch/optimizer.py`](../joulethief/dispatch/optimizer.py)) · Sigstore carbon receipts and gate · compliance external control (HMAC) · feature flags · metrics reports · Terraform state · CI/CD Catalog component ([`templates/grid-window`](../templates/grid-window/template.yml)) · MCP server with 7 tools · 62 offline tests |
| **Design: complete end-to-end workflow** | Issue template → Surge Intake → webhook tick → @grid hold → Flows API → Surge Worker MR → energy check → receipt → canary → promote → "Shipped" note. Replayed end to end on a real week: [`results/loop_replay.md`](results/loop_replay.md), and on the control room's *battery* panel |
| **Potential impact** | A real, quantified problem (curtailment, negative prices, agentic energy) · results on real grids · net of its own footprint · an adoption path that needs no agents ([`grid-window`](../templates/grid-window/template.yml)) |
| **Innovation** | Autonomy as a climate feature (the *carbon dividend of autonomy*) · marginal, not average, signals · the grid as a code reviewer · `git blame` for grams of CO₂ · signed carbon receipts as a deploy gate · a tool that measured itself and changed |
| **Presentation** | [`DEMO.md`](DEMO.md): three minutes, narrated by the grid, every number from the ledger or the experiments |
| **Google Cloud** | Cloud Run (scale to zero, `europe-north1`), Cloud Scheduler, Artifact Registry with cleanup, Workload Identity Federation, Secret Manager, optional always-free e2-micro runner — all in [`infra/terraform`](../infra/terraform/main.tf) |

## Most Environmentally Impactful: method and numbers

**Frameworks.** SCI (ISO/IEC 21031:2024), `SCI = (E × I + M) / R`, with R = one Surge Request for the
workflow, 1,000 requests for the service and one resolved issue for the agents (GSF SCI for AI, consumer
boundary). GHG Protocol location-based for reporting; consequential (marginal) accounting for every
decision and every "avoided" claim. Energy from Cloud Carbon Footprint coefficients and EcoLogits, always
as ranges. Full method: [`METHODOLOGY.md`](METHODOLOGY.md).

**Gain.** Hands-off dispatch cuts emissions 25–34 % against running work on filing, on real British and
Spanish grid data, with no missed deadline ([autonomy dividend](results/autonomy_dividend.md)).

**Net of itself.** Everything Joule Thief adds is charged at the marginal rate where it runs: dispatcher
ticks (measured), LLM sessions (EcoLogits), accounting CI jobs (CCF). Likely payback: scheduling
4–89×; everything included 5–17× with self-hosted inference, 0.7–2.6× when only CI work can move.

| SCI per Surge Request (gCO₂e, consequential, net of all overhead) | Run now | Hands-off | Change |
|---|---:|---:|---:|
| Spain, spring, self-hosted inference | 18.1 | 12.7 | −30 % |
| Spain, summer, self-hosted inference | 44.5 | 31.6 | −29 % |
| Great Britain, self-hosted inference | 15.9 | 12.7 | −20 % |
| Same grids, provider-hosted inference (only CI can move) | 15.9–44.5 | | −3 % to +1 % |

With provider-hosted inference Joule Thief is roughly neutral on a Surge Request's total: it can move
only the CI side. We publish that case rather than hide it; it is why the next step is inference that
can be scheduled (GitLab Duo Self-Hosted, region-pinned models). Full tables, ranges and the
break-even energy per job: [`results/net_impact.md`](results/net_impact.md).

**Practices in the design** ([`DESIGN.md` §8](DESIGN.md)): deterministic first, LLM last (the loop itself
makes zero LLM calls); small models for triage and review, a large one only to implement; loop caps as
token budgets; no blind retries; interruptible pipelines; scale to zero; a low-carbon home region;
demand shaping through an eco-mode feature flag; energy regressions treated as bugs.

## Check it yourself in five minutes (offline)

```bash
pip install -r requirements-dev.txt
python -m pytest -q                      # 62 tests, no network
python experiments/loop_replay.py        # the real loop on a real week, in seconds
python experiments/net_impact.py         # does it pay back its own footprint? (~1 min)
uvicorn app.main:app                     # http://localhost:8000 → press Play on "The backlog is a battery"
```

## Honest limitations

Cloud CPU and LLM energy are modelled, not metered (ranges everywhere). The price→marginal mapping is a
transparent heuristic (its sensitivity is tested). The experiment backlog is synthetic and seeded; the
grids are real. Provider-hosted inference cannot be moved in time by us; only its CI side can.
More in [`DESIGN.md` §10](DESIGN.md).
