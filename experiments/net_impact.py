"""Net impact — does Joule Thief pay back its own footprint?

A carbon-aware scheduler that burns more than it saves is greenwashing with extra steps. This
experiment puts everything Joule Thief *adds* to a delivery on one side and what its dispatch
*saves* on the other, per Surge Request, with ranges, in the consequential (marginal) ledger.

What Joule Thief adds comes in two layers:
  scheduling   what makes the savings possible, for every Surge Request: dispatcher ticks
               (measured here: interpreter cold start + CP-SAT solve, Cloud Run power model) and
               the Surge Intake triage session (EcoLogits).
  measurement  what makes the claims verifiable, for Surge Requests that become code changes
               (heavy-tests / heavy-scan pipelines skip it): energy benchmark and MR energy gate,
               carbon receipt and receipt gate, canary energy check, footprint ledger, and the LLM
               sessions around them (Carbon Reviewer; Release Captain in v1).

Two configurations are compared: ``v1`` as first built, and ``now`` after this experiment showed
where the overhead was (receipts only for deployable images, a deterministic "Shipped" note
instead of the Release Captain LLM flow, the Carbon Reviewer woken only by a measured
regression, a one-call triage fast path for issues filed from the Surge Request template).

Savings per Surge Request and per kind of work come from the same receding-horizon replays as
experiments/autonomy_dividend.py (same backlog, same grids, hands-off vs run-now), in two
hosting scenarios, because only energy that runs where we schedule it can be moved:
  self-hosted model   agent sessions run on our own inference worker: every kind is shiftable;
  provider-hosted     LLM inference runs wherever the provider runs it: only CI work moves.

Run:  python experiments/net_impact.py   (~1 min; writes docs/results/net_impact.{json,md})
"""

from __future__ import annotations

import json
import random
import resource
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from autonomy_dividend import es_forecast_fn, gb_forecast_fn  # noqa: E402

from joulethief.carbon.llm import AgentCall, agent_footprint  # noqa: E402
from joulethief.carbon.power import CloudPowerModel  # noqa: E402
from joulethief.dispatch.optimizer import plan  # noqa: E402
from joulethief.dispatch.receding import _score, simulate, synthetic_backlog  # noqa: E402
from joulethief.estimate import Estimate, total  # noqa: E402
from joulethief.signals.base import Point, Series  # noqa: E402
from joulethief.signals.marginal import PriceMarginalModel  # noqa: E402
from joulethief.signals.snapshots import es_prices, gb_intensity  # noqa: E402

UTC = timezone.utc
OUT = ROOT / "docs" / "results"

# Annual marginal intensity (GSF Real Time Cloud, WattTime-derived; see docs/results/region_ledgers.md).
# Overhead is charged at the *marginal* rate so that it is comparable with consequential savings.
MARGINAL_G = {"europe-north1": 785.0, "us-east1": 728.0}
CLOUD_RUN = {"vcpus": 1.0, "memory_gb": 0.5, "idle_minutes": 15.0}  # CPU allocated only during requests
TICKS_PER_DAY = 48  # Cloud Scheduler, every 30 minutes
SURGE_REQUESTS_PER_DAY = 12 * 5 / 7  # the experiment's arrival rate: 12 per working day
CODE_KINDS = {"agent_session", "dependency_upgrade"}  # become MRs; CI kinds run as JOULE_TASK pipelines
SHIFTABLE_IF_PROVIDER_HOSTED = {"ci_pipeline", "security_scan"}
GOOGLE_MEDIAN_PROMPT_WH = 0.24  # Google, "Measuring the environmental impact of delivering AI at Google scale" (2025)
SMALL_MODEL, UPPER_MODEL = ("anthropic", "claude-haiku-4-5"), ("anthropic", "claude-sonnet-4-6")

# Minutes per job on saas-linux-small-amd64 (e2-standard-2, us-east1), image pull and installs included.
JOB_MINUTES = {"verify:energy": (1.5, 2.0, 3.0), "release:receipt": (0.7, 1.0, 2.0),
               "release:verify-receipt": (0.5, 0.8, 1.5), "monitor:canary-energy": (0.5, 0.8, 1.5),
               "govern:footprint": (0.5, 0.7, 1.5), "govern:footprint+shipped": (0.6, 0.8, 1.6)}


@dataclass(frozen=True)
class Session:
    flow: str
    calls: tuple[int, int, int]  # low / likely / high, bounded by the flow's max_cycles
    output_tokens: tuple[int, int, int]  # per call


@dataclass(frozen=True)
class Config:
    label: str
    intake: Session
    code_sessions: tuple[Session, ...]  # per code-changing Surge Request
    mr_jobs: tuple[str, ...]  # accounting jobs in each MR pipeline
    main_jobs: tuple[str, ...]  # accounting jobs in the default-branch pipeline
    mr_pipelines: tuple[int, int, int] = (1, 1, 2)  # pushes per MR (low / likely / high)


CONFIGS = {
    "v1": Config(
        "v1, as first built",
        intake=Session("surge-intake", (3, 5, 8), (100, 200, 300)),
        code_sessions=(Session("carbon-reviewer (every MR)", (4, 8, 12), (150, 300, 600)),
                       Session("release-captain (every delivery)", (4, 6, 10), (100, 200, 400))),
        mr_jobs=("verify:energy", "release:receipt", "release:verify-receipt", "govern:footprint"),
        main_jobs=("verify:energy", "release:receipt", "release:verify-receipt", "monitor:canary-energy",
                   "govern:footprint")),
    "now": Config(
        "now, after measuring itself",
        # template fast path: 1 call; untemplated issues: full triage (likely: half of each)
        intake=Session("surge-intake", (1, 3, 8), (50, 150, 300)),
        # woken only by a measured regression or a hot-line edit (likely: 1 MR in 4 × 8 calls)
        code_sessions=(Session("carbon-reviewer (on regression)", (0, 2, 12), (150, 300, 600)),),
        mr_jobs=("verify:energy", "govern:footprint"),
        main_jobs=("verify:energy", "release:receipt", "release:verify-receipt", "monitor:canary-energy",
                   "govern:footprint+shipped")),
}


# ── dispatcher (measured) ──────────────────────────────────────────────────────────────────
def cold_start_cpu_s(runs: int = 3) -> list[float]:
    """CPU seconds of a fresh interpreter importing everything a tick needs (worst case: every tick is cold)."""
    code = "import app.main, joulethief.loop, joulethief.gitlab, ortools.sat.python.cp_model"
    out = []
    for _ in range(runs):
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        out.append((after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime))
    return out


def solve_cpu_s(samples: int = 12, seed: int = 1) -> dict[str, list[float]]:
    """CPU seconds (all solver threads) of a real tick's plan: two regions, 36 h horizon, capacity 3."""
    es = PriceMarginalModel().series(es_prices()).slice(datetime(2025, 4, 1, tzinfo=UTC), datetime(2025, 5, 15, tzinfo=UTC))
    gb = gb_intensity()
    rng = random.Random(seed)
    out: dict[str, list[float]] = {"typical": [], "stress": []}
    for label, per_weekday in (("typical", 12), ("stress", 48)):
        for _ in range(samples):
            now = datetime(2026, 9, 7, tzinfo=UTC) + timedelta(hours=rng.randint(0, 21 * 24))
            # GB data covers Sep–Oct 2026: shift the Spanish prices onto the same dates.
            offset = now - datetime(2025, 4, 8, tzinfo=UTC)
            es_now = Series(es.zone, es.metric, es.unit, es.resolution, [Point(p.start + offset, p.value) for p in es],
                            es.source)
            jobs = [j for j in synthetic_backlog(now - timedelta(days=3), 4, per_weekday=per_weekday,
                                                 seed=rng.randint(0, 10**6), region="europe-southwest1")
                    if now - timedelta(hours=24) <= j.release <= now and not j.urgent]
            jobs = [type(j)(j.id, j.duration, j.power_kw, j.release, j.deadline, ("europe-southwest1", "europe-west2"),
                            j.kind, j.priority) for j in jobs]
            if not jobs:
                continue
            t0 = time.process_time()
            plan(jobs, {"europe-southwest1": es_now, "europe-west2": gb}, now, timedelta(hours=36), capacity=3)
            out[label].append(time.process_time() - t0)
    return out


def dispatcher_overhead(cold: list[float], solve: dict[str, list[float]]) -> dict:
    pm = CloudPowerModel()
    mem = CLOUD_RUN["memory_gb"]
    cold_s = Estimate(min(cold), statistics.median(cold), max(cold))
    solve_s = Estimate(min(solve["typical"]), statistics.median(solve["typical"]),
                       max(solve["stress"] + solve["typical"]))
    busy = pm.energy_from_cpu_seconds(cold_s.likely + solve_s.likely, mem * (cold_s.likely + solve_s.likely) / 3600)
    # After a request the instance may idle up to 15 min: CPU is throttled (not allocated), memory stays.
    likely = busy.likely + pm.energy_kwh(0, CLOUD_RUN["idle_minutes"] / 2 / 60, 0.0, mem).likely
    low = pm.energy_from_cpu_seconds(cold_s.low).low  # no idle time, no solve (empty battery)
    # Upper bound: worst solve, and the idle vCPU charged at its minimum power for the full 15 minutes.
    high = (pm.energy_from_cpu_seconds(cold_s.high + solve_s.high, mem * (cold_s.high + solve_s.high) / 3600).high
            + pm.energy_kwh(CLOUD_RUN["vcpus"], CLOUD_RUN["idle_minutes"] / 60, 0.0, mem).high)
    per_tick = Estimate(low, likely, high)
    per_day_g = per_tick * TICKS_PER_DAY * MARGINAL_G["europe-north1"]
    # Alternative heartbeat: a GitLab scheduled pipeline, one ~1-minute job per tick on a hosted runner.
    gitlab_tick_g = ci_minutes_g(Estimate(0.5, 1.0, 1.5)) * TICKS_PER_DAY
    return {"cold_start_cpu_s": cold_s.to_dict(3), "solve_cpu_s": solve_s.to_dict(3),
            "solve_samples": {k: len(v) for k, v in solve.items()}, "per_tick_kwh": per_tick.to_dict(9),
            "per_day_g": per_day_g.to_dict(4), "per_surge_request_g": (per_day_g / SURGE_REQUESTS_PER_DAY).to_dict(4),
            "gitlab_schedule_alternative_per_day_g": gitlab_tick_g.to_dict(3)}


# ── agents and CI jobs (modelled from this repository's configuration) ─────────────────────
def session_g(s: Session) -> Estimate:
    def g(model, calls, tokens, which):
        return getattr(agent_footprint([AgentCall(*model, 0, tokens)] * calls).gwp_g, which) if calls else 0.0

    return Estimate(g(SMALL_MODEL, s.calls[0], s.output_tokens[0], "low"),
                    g(SMALL_MODEL, s.calls[1], s.output_tokens[1], "likely"),
                    g(UPPER_MODEL, s.calls[2], s.output_tokens[2], "high"))


def ci_minutes_g(minutes: Estimate) -> Estimate:
    pm = CloudPowerModel()
    machine, vcpus, mem = "e2-standard-2", 2, 8
    energy = Estimate(pm.energy_kwh(vcpus, minutes.low / 60, 0.3, mem).low,
                      pm.energy_kwh(vcpus, minutes.likely / 60, 0.45, mem).likely,
                      pm.energy_kwh(vcpus, minutes.high / 60, 0.6, mem).high)
    embodied = Estimate(*(pm.embodied_g(machine, vcpus, m / 60) for m in (minutes.low, minutes.likely, minutes.high)))
    return energy * MARGINAL_G["us-east1"] + embodied


def config_overhead(cfg: Config, dispatcher_g: Estimate) -> dict:
    intake = session_g(cfg.intake)
    sessions = {s.flow: session_g(s) for s in cfg.code_sessions}
    mr_min = total([Estimate(*JOB_MINUTES[j]) for j in cfg.mr_jobs]) * Estimate(*cfg.mr_pipelines)
    main_min = total([Estimate(*JOB_MINUTES[j]) for j in cfg.main_jobs])
    ci_g = ci_minutes_g(mr_min + main_min)
    scheduling = dispatcher_g + intake
    measurement = ci_g + total(list(sessions.values()))
    calls_likely = cfg.intake.calls[1] + sum(s.calls[1] for s in cfg.code_sessions)
    return {"label": cfg.label, "intake_g": intake.to_dict(4), "sessions_g": {k: v.to_dict(4) for k, v in sessions.items()},
            "ci_minutes": (mr_min + main_min).to_dict(2), "ci_g": ci_g.to_dict(4),
            "scheduling_g": scheduling.to_dict(4), "measurement_g_per_code_change": measurement.to_dict(4),
            "llm_calls_likely": calls_likely,
            "google_median_prompt_cross_check_wh": round(calls_likely * GOOGLE_MEDIAN_PROMPT_WH, 3)}


# ── savings ────────────────────────────────────────────────────────────────────────────────
def savings_case(name: str, region: str, actual, forecast, start: datetime, end: datetime, tz: str) -> dict:
    jobs = synthetic_backlog(start, (end - start).days - 3, region=region, tz=tz)
    by_id = {j.id: j for j in jobs}
    per_job: dict[str, dict[str, float]] = {}
    for policy in ("run_now", "hands_off"):
        res = simulate(jobs, {region: actual}, forecast, policy, start, end)
        for a in res.assignments:
            g, _, _ = _score([a], by_id, {region: actual}, timedelta(minutes=30), None)
            per_job.setdefault(a.job_id, {})[policy] = g
    by_kind: dict[str, dict] = {}
    for job_id, g in per_job.items():
        k = by_kind.setdefault(by_id[job_id].kind, {"jobs": 0, "kwh": 0.0, "saved_g": 0.0, "run_now_g": 0.0})
        k["jobs"] += 1
        k["kwh"] += by_id[job_id].energy_kwh
        k["saved_g"] += g["run_now"] - g["hands_off"]
        k["run_now_g"] += g["run_now"]
    n = len(jobs)
    kwh = sum(k["kwh"] for k in by_kind.values())
    return {"case": name, "region": region, "jobs": n,
            "saved_g_per_kwh_shifted": round(sum(k["saved_g"] for k in by_kind.values()) / kwh, 2),
            "code_change_share": round(sum(k["jobs"] for kind, k in by_kind.items() if kind in CODE_KINDS) / n, 4),
            "by_kind": {kind: {**{x: round(v, 3) for x, v in k.items()},
                               "saved_g_per_job": round(k["saved_g"] / k["jobs"], 3)} for kind, k in sorted(by_kind.items())},
            "run_now_g_per_surge_request": round(sum(k["run_now_g"] for k in by_kind.values()) / n, 3),
            "saved_g_per_surge_request": {
                "self_hosted": round(sum(k["saved_g"] for k in by_kind.values()) / n, 3),
                "provider_hosted": round(sum(k["saved_g"] for kind, k in by_kind.items()
                                             if kind in SHIFTABLE_IF_PROVIDER_HOSTED) / n, 3)}}


def balance(case: dict, oh: dict) -> dict:
    scheduling = Estimate(**oh["scheduling_g"])
    full = scheduling + Estimate(**oh["measurement_g_per_code_change"]) * case["code_change_share"]
    per_kwh = case["saved_g_per_kwh_shifted"]
    out = {"overhead_g_per_surge_request": full.to_dict(4),
           # the deferrable energy per Surge Request at which dispatch repays what Joule Thief adds (likely)
           "break_even_wh": {"scheduling": round(scheduling.likely / per_kwh * 1000, 1),
                             "everything": round(full.likely / per_kwh * 1000, 1)}}
    for scenario, saved in case["saved_g_per_surge_request"].items():
        out[scenario] = {
            "net_g": (Estimate.exact(saved) - full).to_dict(3),
            "payback_full": {"likely": round(saved / full.likely, 2), "worst": round(saved / full.high, 2)},
            "payback_scheduling": {"likely": round(saved / scheduling.likely, 2), "worst": round(saved / scheduling.high, 2)},
        }
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    dispatcher = dispatcher_overhead(cold_start_cpu_s(), solve_cpu_s())
    dispatcher_g = Estimate(**dispatcher["per_surge_request_g"])
    overhead = {name: config_overhead(cfg, dispatcher_g) for name, cfg in CONFIGS.items()}

    marginal = PriceMarginalModel(fossil_margin_g=490.0, fossil_price=40.0).series(es_prices())
    cases = [
        savings_case("GB, NESO average, Sep–Oct 2026", "europe-west2", gb_intensity(), gb_forecast_fn(),
                     datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC), "Europe/London"),
        savings_case("ES spring 2025, marginal heuristic", "europe-southwest1", marginal, es_forecast_fn(marginal),
                     datetime(2025, 3, 1, tzinfo=UTC), datetime(2025, 6, 1, tzinfo=UTC), "Europe/Madrid"),
        savings_case("ES summer 2025, marginal heuristic", "europe-southwest1", marginal, es_forecast_fn(marginal),
                     datetime(2025, 7, 1, tzinfo=UTC), datetime(2025, 9, 30, tzinfo=UTC), "Europe/Madrid"),
    ]
    for c in cases:
        c["balance"] = {name: balance(c, oh) for name, oh in overhead.items()}
    report = {"generated": datetime.now(UTC).isoformat(timespec="seconds"), "runtime_s": round(time.time() - t0, 1),
              "dispatcher": dispatcher, "overhead": overhead, "cases": cases,
              "assumptions": {"marginal_g": MARGINAL_G, "cloud_run": CLOUD_RUN, "ticks_per_day": TICKS_PER_DAY,
                              "surge_requests_per_day": round(SURGE_REQUESTS_PER_DAY, 2), "job_minutes": JOB_MINUTES,
                              "models": {"likely": SMALL_MODEL[1], "upper_bound": UPPER_MODEL[1]}}}
    (OUT / "net_impact.json").write_text(json.dumps(report, indent=2, default=str))
    (OUT / "net_impact.md").write_text(render(report))
    print(render(report))


def _r(d: dict, digits: int = 2) -> str:
    return f"{d['likely']:.{digits}f} ({d['low']:.{digits}f}–{d['high']:.{digits}f})"


def render(r: dict) -> str:
    d, o = r["dispatcher"], r["overhead"]
    v1, now = o["v1"], o["now"]
    lines = [
        "# Net impact: does Joule Thief pay back its own footprint? (generated)", "",
        f"Generated {r['generated']} by `experiments/net_impact.py`. Every gram Joule Thief *adds* is charged at the "
        "annual **marginal** intensity of where it runs (Finland 785, South Carolina 728 g/kWh), so it is comparable "
        "with the consequential savings. Values are likely (low–high).", "",
        "## What Joule Thief adds", "",
        "| Layer | Component | How it was obtained | v1 | now |", "|---|---|---|---:|---:|",
        f"| scheduling, per Surge Request | Dispatcher ticks (Cloud Run, every 30 min) | **measured** on this machine: cold "
        f"start {_r(d['cold_start_cpu_s'])} CPU-s, CP-SAT solve {_r(d['solve_cpu_s'], 3)} CPU-s; CCF power model; "
        f"idle memory after each tick | {_r(d['per_surge_request_g'], 3)} | {_r(d['per_surge_request_g'], 3)} |",
        f"| scheduling, per Surge Request | Surge Intake triage | EcoLogits, {r['assumptions']['models']['likely']} "
        f"(upper bound {r['assumptions']['models']['upper_bound']}) | {_r(v1['intake_g'], 3)} | {_r(now['intake_g'], 3)} |",
        f"| measurement, per code change | Accounting CI jobs | CCF model, e2-standard-2 hosted runner in `us-east1`: "
        f"{_r(v1['ci_minutes'], 1)} → {_r(now['ci_minutes'], 1)} runner-minutes | {_r(v1['ci_g'], 3)} | {_r(now['ci_g'], 3)} |",
    ]
    for flow in list(v1["sessions_g"]) + [f for f in now["sessions_g"] if f not in v1["sessions_g"]]:
        a, b = v1["sessions_g"].get(flow), now["sessions_g"].get(flow)
        lines.append(f"| measurement, per code change | {flow} | EcoLogits | {_r(a, 3) if a else '—'} | {_r(b, 3) if b else '—'} |")
    lines += [
        f"| | **Scheduling layer** | | **{_r(v1['scheduling_g'], 3)}** | **{_r(now['scheduling_g'], 3)}** |",
        f"| | **Measurement layer** | | **{_r(v1['measurement_g_per_code_change'], 3)}** | "
        f"**{_r(now['measurement_g_per_code_change'], 3)}** |", "",
        f"What changed between v1 and now: carbon receipts and the receipt gate run only for images that can be deployed "
        f"(default branch); the Release Captain LLM flow became `joule shipped`, a script that copies the numbers from the "
        f"pipeline's artifacts; the Carbon Reviewer agent is started by CI only when an MR regresses joules/request or "
        f"edits a hot line (every MR still gets a deterministic energy table); issues filed from the Surge Request "
        f"template carry their labels, so triage takes one call. LLM calls per code change, likely: "
        f"{v1['llm_calls_likely']} → {now['llm_calls_likely']}.", "",
        f"Cross-check on the agents: at Google's published median of 0.24 Wh per Gemini prompt, {now['llm_calls_likely']} "
        f"calls would use {now['google_median_prompt_cross_check_wh']:.2f} Wh. EcoLogits models output tokens only, "
        "so long agent contexts are under-counted; the upper bound uses a mid-size model to cover that.", "",
        f"Heartbeat choice: the Cloud Run tick costs {_r(d['per_day_g'], 2)} g/day; the same heartbeat as a GitLab "
        f"scheduled pipeline would cost {_r(d['gitlab_schedule_alternative_per_day_g'], 1)} g/day.", "",
        "## The balance (now)", "",
        "Saved = hands-off versus run-now on the same backlog and grids as the autonomy experiment. Overhead = the "
        "scheduling layer for every Surge Request + the measurement layer for the share that becomes code changes. "
        "*Provider-hosted*: LLM inference runs wherever the provider runs it, so only CI work (pipelines, scans) is credited.", "",
        "| Grid | Scenario | Run-now g/SR | Saved g/SR | Overhead g/SR | Payback, scheduling only | Payback, everything (v1 → now) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for c in r["cases"]:
        b1, bn = c["balance"]["v1"], c["balance"]["now"]
        for scenario, label in (("self_hosted", "self-hosted model"), ("provider_hosted", "provider-hosted")):
            sn, s1 = bn[scenario], b1[scenario]
            lines.append(
                f"| {c['case']} | {label} | {c['run_now_g_per_surge_request']:.1f} | {c['saved_g_per_surge_request'][scenario]:.2f} | "
                f"{_r(bn['overhead_g_per_surge_request'], 2)} | {sn['payback_scheduling']['likely']:.0f}× "
                f"(worst {sn['payback_scheduling']['worst']:.1f}×) | {s1['payback_full']['likely']:.1f}× → "
                f"**{sn['payback_full']['likely']:.1f}×** (worst {sn['payback_full']['worst']:.1f}×) |")
    lines += ["", "## Break-even: how much energy must a Surge Request move?", "",
              "Each kWh the dispatcher moves saves the grams below; dividing what Joule Thief adds by that gives the "
              "deferrable energy per Surge Request at which it pays for itself (likely values). Work below the "
              "threshold is cheaper to run now.", "",
              "| Grid | Saved per kWh moved (g) | Break-even, scheduling only (Wh) | Break-even, everything (Wh) |",
              "|---|---:|---:|---:|"]
    for c in r["cases"]:
        be = c["balance"]["now"]["break_even_wh"]
        lines.append(f"| {c['case']} | {c['saved_g_per_kwh_shifted']:.0f} | {be['scheduling']:.1f} | {be['everything']:.1f} |")
    lines += ["", "For scale: a 4-vCPU hosted runner draws ≈ 15–20 W, so 20 Wh is about an hour of CI; one GPU inference "
              "worker (≈ 350 W in the backlog model) moves that much in four minutes.", ""]
    lines += ["## Savings by kind of work (hands-off vs run-now)", "",
              "| Grid | Kind | Jobs | Energy (kWh) | Saved (g) | Saved per job (g) |", "|---|---|---:|---:|---:|---:|"]
    for c in r["cases"]:
        for kind, k in c["by_kind"].items():
            lines.append(f"| {c['case']} | {kind} | {k['jobs']} | {k['kwh']:.2f} | {k['saved_g']:.0f} | {k['saved_g_per_job']:.2f} |")
    sched = [c["balance"]["now"][s]["payback_scheduling"]["likely"] for c in r["cases"] for s in ("self_hosted", "provider_hosted")]
    full_self = [c["balance"]["now"]["self_hosted"]["payback_full"]["likely"] for c in r["cases"]]
    full_prov = [c["balance"]["now"]["provider_hosted"]["payback_full"]["likely"] for c in r["cases"]]
    lines += ["", "## Reading", "",
              "- Payback = grams avoided ÷ grams added; above 1× Joule Thief removes more than it emits. *Worst* divides "
              "the likely saving by the upper bound of every overhead (largest model, every loop at its cap, idle vCPU "
              "charged at its minimum power): it is a bound, not a forecast.",
              f"- Likely case: scheduling repays itself {min(sched):.0f}–{max(sched):.0f}× in every grid and scenario. With "
              f"the measurement layer (receipts, benchmarks, ledgers, reviewers) included, Joule Thief repays itself "
              f"{min(full_self):.0f}–{max(full_self):.0f}× when inference is self-hosted and {min(full_prov):.1f}–"
              f"{max(full_prov):.1f}× when only CI work can move: below break-even on the GB average signal, above it on "
              "the Spanish marginal signal.",
              "- Measurement is what makes the claims verifiable, and it is now the largest overhead: runner minutes "
              "of accounting jobs on hosted runners in South Carolina. Where only small CI jobs can move, it is close "
              "to break-even; the break-even table says which work is worth scheduling at all.",
              "- GB rows use NESO *average* intensity (no free marginal signal for GB): indicative, not consequential. "
              "Spain uses the price→marginal heuristic of METHODOLOGY.md §3.",
              "- The backlog is synthetic and seeded; grids are real. Runner minutes are modelled until a real "
              "`govern:footprint` ledger exists, which records every job's actual duration.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
