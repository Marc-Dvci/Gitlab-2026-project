# Joule Thief

**Just-in-time Orchestration Using Leftover Energy** — hands-off agents that run the post-code
lifecycle on the energy the grid throws away. *The backlog is a battery.*

A [joule thief](https://en.wikipedia.org/wiki/Joule_thief) is a little circuit that squeezes the last
energy out of batteries everyone else considers dead. Joule Thief does the same with electricity
grids: GitLab Duo agents and pipelines do their deferrable work (dependency upgrades, test
matrices, scans, refactors) when clean power is in surplus, and critical work never waits.

Built for the GitLab Transcend Hackathon *Life After Code* — Path A, hands-off autonomy.

## What it does

- **Surge Requests.** A Duo flow triages every new issue: priority, kind of work, and whether it can wait.
- **@grid.** The electricity grid gets a seat at code review: it holds or releases work, with numbers.
- **Dispatcher.** Every 30 minutes, and the moment a Surge Request is filed (issue webhook), an OR-Tools
  CP-SAT planner schedules the backlog on marginal and surplus signals (day-ahead prices, NESO, WattTime),
  under each issue's deadline, using Google's virtual-capacity-curve method. When the window opens it
  starts a Duo flow through the Flows API.
- **Carbon blame.** `git blame` for grams of CO₂: joules per request per source line, in every MR.
- **Carbon receipts.** Every image gets a Sigstore-signed in-toto attestation with energy, two carbon
  ledgers (attributional and consequential), water and the agents' own footprint (SCI for AI). No
  valid, within-budget receipt → no deploy.
- **Energy regressions are bugs.** The Cloud Run canary is promoted only if it isn't hungrier than production.
- **Governed.** The carbon budget is a compliance-centre external control; every pipeline accounts for itself.
- **Measured against itself.** Everything Joule Thief adds (ticks, LLM calls, accounting jobs) is charged
  against what it saves. It cut its own LLM calls per change from 19 to 5 when the numbers said so.

## Results on real grid data

| Grid | Hands-off vs run-now | Supervised vs run-now | Carbon dividend of autonomy | Deadlines missed (hands-off) |
|---|---:|---:|---:|---:|
| Great Britain, Sep–Oct 2026 | −24.9 % | −17.9 % | 6.9 % | 0 |
| Spain, spring 2025 | −34.2 % | −26.5 % | 7.8 % | 0 |
| Spain, summer 2025 | −30.6 % | −20.5 % | 10.2 % | 0 |

Net of its own footprint, Joule Thief pays for itself 5–17× with self-hosted inference
([net impact](docs/results/net_impact.md)); the real dispatcher loop, replayed on a real week of Spanish
prices, cut emissions 41 % with no late work and no LLM call ([replay](docs/results/loop_replay.md)).

[Full results](docs/results/autonomy_dividend.md) · [Robustness](docs/results/robustness.md) ·
[Average vs marginal by region](docs/results/region_ledgers.md) · [Submission](docs/SUBMISSION.md) ·
[Design](docs/DESIGN.md) · [Methodology](docs/METHODOLOGY.md) · [Data sources](docs/DATA_SOURCES.md) ·
[Setup at $0](docs/SETUP.md) · [Demo script](docs/DEMO.md) · [Carbon receipt spec](docs/RECEIPT.md)

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q                         # 62 tests, offline
python experiments/loop_replay.py           # the real loop on a real week (seconds)
python experiments/autonomy_dividend.py     # replays real GB and Spanish grids (~2 min)
uvicorn app.main:app                        # dashboard (press Play on the battery) + API + MCP server at /mcp
python -m joulethief.cli grid europe-north1 # live decision signal (needs internet)
```

## Use the grid window in your own project

No agents, no cloud: one CI/CD Catalog component holds your deferrable jobs (nightly matrix, fuzzing,
full scans) until the cleanest start before a deadline, as a child pipeline behind a `when: delayed` job.

```yaml
include:
  - component: gitlab.com/<group>/joule-thief/grid-window@<version>
    inputs:
      jobs: ci/nightly.yml     # your deferrable jobs, unchanged
      region: europe-north1    # where your runners draw power
      deadline: 24h
      duration: 45m
```

On real Spanish prices, a 45-minute pipeline scheduled at 02:00 on 13 May 2025 waits 9 h for the
11:00 solar surplus: 98 % less carbon. With no live signal for the region, it runs at once.
Details: [`templates/grid-window/template.yml`](templates/grid-window/template.yml).

## Layout

```
joulethief/   signals · dispatch · carbon · receipts · blame · gitlab · loop · voice · mcp_server · cli
app/          Cloud Run control room (FastAPI): battery replay, eco-mode, issue webhook, MCP server at /mcp
templates/    CI/CD Catalog component `grid-window` (joulethief/window.py)
.gitlab/duo/  custom flows (surge-intake, surge-worker, carbon-reviewer, retry-guard), Surge Request issue template,
              custom agents (@grid, carbon-accountant), MCP client config
.gitlab-ci.yml  plan · verify · test · secure · package · release · configure · monitor · govern
infra/        OpenTofu/Terraform for Google Cloud's free tier (keyless Workload Identity Federation)
data/         real grid snapshots and reference coefficients (see docs/DATA_SOURCES.md)
experiments/  the carbon dividend of autonomy; average vs marginal per region
```

## License

MIT — see [LICENSE](LICENSE). Data files keep their own licences (docs/DATA_SOURCES.md).
