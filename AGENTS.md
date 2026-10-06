# AGENTS.md — rules for every agent working on Joule Thief

You are working on a project whose purpose is to make agentic software delivery cheaper for the
planet. Your own footprint is measured and published (SCI for AI). Work like it.

## Energy rules
1. **Deterministic first, LLM last.** If a script, test or API call can answer, use it.
2. **Read narrowly.** Open the files you need. Never read `data/` snapshots, lock files or generated
   results in full; use `grep` or read the first lines.
3. **Never re-run a failing command unchanged.** Diagnose, change something, then re-run.
4. **One merge request per issue**, smallest correct change, no drive-by refactors.
5. **Time is a resource you may spend.** Work labelled `priority::low|normal` may wait for a clean
   window; `priority::critical` never waits.

## How to verify a change
- `python -m pytest -q` — must pass.
- `python scripts/energy_benchmark.py` — when you touch `app/` or `joulethief/`; report joules/request
  before and after in the MR description.
- `python experiments/autonomy_dividend.py` — only when you touch `joulethief/dispatch/` (slow, ~2 min).

## Code map
- `joulethief/signals/` grid data adapters (free sources), real snapshots, marginal-signal heuristic.
- `joulethief/dispatch/` CP-SAT dispatcher, virtual capacity curves, conformal intervals, simulator.
- `joulethief/carbon/` SCI, SCI for AI (EcoLogits), water, power model, two ledgers.
- `joulethief/receipts/` in-toto carbon receipts; `joulethief/blame/` carbon blame profiler.
- `joulethief/loop.py` hands-off dispatcher tick; `joulethief/voice.py` @grid messages (no LLM).
- `app/` Cloud Run control room + MCP server mount. `app/insights.py` contains a **disclosed seeded
  inefficiency** used in the demo: `weekly_pairs` is O(n·m) and should be O(n+m).

## Style
Python 3.11+, standard library first, type hints, small functions, ranges (`Estimate`) for every
environmental quantity. Match the surrounding code.
