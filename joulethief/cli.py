"""``joule`` — command line for CI jobs and humans.

    joule grid europe-north1                 # live decision signal + surplus windows
    joule tick [--dry-run]                   # one hands-off dispatcher tick against GitLab
    joule ci-energy --machine e2-standard-2  # this CI job's footprint -> ledger
    joule receipt build|verify ...           # carbon receipts (in-toto predicate)
    joule control --ledger ledger.jsonl ...  # report the carbon budget to the compliance centre
    joule footprint --trace trace.jsonl      # SCI for AI of a Duo session trace
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .estimate import Estimate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cmd_grid(args) -> int:
    from .live import LiveSignals
    from .signals.marginal import surplus_windows
    from .signals.regions import REGIONS

    sig = LiveSignals()
    s = sig.decision_signal(args.region, _now())
    print(f"{args.region}: {s.metric} ({s.unit}) from {s.source}")
    now_v = s.value_at(_now())
    print(f"  now: {now_v if now_v is not None else 'n/a'}")
    window = s.slice(_now(), _now() + timedelta(hours=args.hours))
    if len(window):
        best = min(window, key=lambda p: p.value)
        print(f"  cleanest in next {args.hours} h: {best.value:.0f} at {best.start:%Y-%m-%d %H:%M} UTC")
    zone = REGIONS[args.region].price_zone
    if zone:
        for start, end, low in surplus_windows(sig.prices(zone, _now())):
            print(f"  surplus: {start:%a %H:%M}–{end:%H:%M} UTC (min {low:.2f} €/MWh)")
    return 0


def cmd_tick(args) -> int:
    from .gitlab import GitLab
    from .live import LiveSignals
    from .loop import LoopConfig, publish_plan, tick

    consumer = os.environ.get("JOULE_FLOW_CONSUMER_ID")
    gitlab = GitLab.from_env()
    cfg = LoopConfig(flow_consumer_id=int(consumer) if consumer else None, dry_run=args.dry_run,
                     ref=os.environ.get("CI_DEFAULT_BRANCH", "main"))
    report = tick(gitlab, LiveSignals(), cfg, _now())
    if args.publish_plan and not args.dry_run:
        publish_plan(gitlab, report)
    print(json.dumps({"plan": report.plan.to_dict(), "started": report.started, "held": report.held}, indent=2))
    return 0


def cmd_eco(args) -> int:
    """Demand shaping: switch the app's eco-mode feature flag from the grid's current marginal signal."""
    from .gitlab import GitLab
    from .live import LiveSignals

    value = LiveSignals().decision_signal(args.region, _now()).value_at(_now())
    active = value is not None and value > args.threshold_g
    print(f"{args.region}: {value} gCO2/kWh -> eco-mode {'ON' if active else 'OFF'} (threshold {args.threshold_g})")
    if not args.dry_run:
        GitLab.from_env().set_feature_flag(args.flag, active)
    return 0


def cmd_ci_energy(args) -> int:
    """Footprint of the current CI job from its duration (CI_JOB_STARTED_AT) and machine type."""
    from .carbon.ledger import Ledger, LedgerEntry
    from .carbon.power import CloudPowerModel
    from .signals.regions import google_region_carbon

    started = os.environ.get("CI_JOB_STARTED_AT")
    start = datetime.fromisoformat(started.replace("Z", "+00:00")) if started else _now() - timedelta(minutes=args.minutes)
    end = _now()
    hours = max((end - start).total_seconds() / 3600, 1 / 3600)
    pm = CloudPowerModel()
    energy = pm.energy_kwh(args.vcpus, hours, args.utilisation, args.memory_gb)
    region = google_region_carbon()[args.region]
    attributional = energy * region.grid_intensity_avg
    marginal = args.marginal_g or region.grid_intensity_avg
    embodied = pm.embodied_g(args.machine, args.vcpus, hours)
    entry = LedgerEntry(os.environ.get("CI_JOB_URL", "local"), "ci_job", args.region, start, end, energy,
                        attributional + embodied, energy * marginal + embodied, signals=["google-region-carbon-2024"])
    Ledger(Path(args.ledger)).record(entry)
    print(f"CI job: {hours * 60:.1f} min on {args.machine} in {args.region}: {energy:.4f} kWh, "
          f"{entry.attributional_g:.2f} gCO2e (attributional)")
    return 0


# GitLab.com hosted runner sizes (docs: "Hosted runners on Linux"); all run in GCP us-east1.
RUNNER_PROFILES = {
    "saas-linux-small-amd64": ("e2-standard-2", 2, 8, "us-east1"),
    "saas-linux-medium-amd64": ("e2-standard-4", 4, 16, "us-east1"),
    "saas-linux-large-amd64": ("n2d-standard-8", 8, 32, "us-east1"),
    "saas-linux-small-arm64": ("t2a-standard-2", 2, 8, "us-east1"),
    # Self-hosted always-free e2-micro in us-west1 (Oregon): 0.25 vCPU sustained, 1 GB.
    "green-runner": ("e2-micro", 0.25, 1, "us-west1"),
}


def cmd_pipeline_footprint(args) -> int:
    """Account for every job of this pipeline (including retries) from the GitLab API — one job, no per-job overhead."""
    from .carbon.ledger import Ledger, LedgerEntry
    from .carbon.power import CloudPowerModel
    from .gitlab import GitLab
    from .signals.regions import google_region_carbon

    gl = GitLab.from_env()
    jobs = gl.pipeline_jobs(args.pipeline or os.environ["CI_PIPELINE_ID"])
    pm, regions = CloudPowerModel(), google_region_carbon()
    ledger = Ledger(Path(args.ledger))
    retried = 0
    for job in jobs:
        if not job.get("duration") or not job.get("started_at"):
            continue
        tags = job.get("tag_list") or []
        profile = next((RUNNER_PROFILES[t] for t in tags if t in RUNNER_PROFILES), RUNNER_PROFILES["saas-linux-small-amd64"])
        machine, vcpus, mem, region = profile
        hours = job["duration"] / 3600
        energy = pm.energy_kwh(vcpus, hours, args.utilisation, mem)
        intensity = regions[region].grid_intensity_avg
        embodied = pm.embodied_g(machine, vcpus, hours)
        start = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
        retried += bool(job.get("retried"))
        ledger.record(LedgerEntry(job.get("web_url", job["name"]), "ci_job", region, start,
                                  start + timedelta(seconds=job["duration"]), energy,
                                  energy * intensity + embodied, energy * (args.marginal_g or intensity) + embodied,
                                  signals=["google-region-carbon-2024", f"runner:{machine}"]))
    summary = ledger.summary()
    print(f"pipeline: {len(jobs)} jobs ({retried} retried), {summary['energy_kwh']['likely']:.4f} kWh, "
          f"{summary['attributional_g']['likely']:.2f} gCO2e attributional")
    Path(args.summary).write_text(json.dumps(summary, indent=2))
    return 0


def cmd_footprint(args) -> int:
    from .carbon.llm import agent_footprint, calls_from_trace

    calls = calls_from_trace(Path(args.trace).read_text(), args.provider, args.model)
    fp = agent_footprint(calls, args.zone)
    print(json.dumps({**fp.to_dict(), "sci_for_ai": fp.sci_for_ai(args.units, args.unit)}, indent=2))
    return 0


def cmd_receipt(args) -> int:
    from .carbon.ledger import Ledger
    from .receipts.intoto import PREDICATE_TYPE, Budget, Policy, Receipt, verify

    if args.action == "build":
        summary = Ledger(Path(args.ledger)).summary() if Path(args.ledger).exists() else {}
        zero = Estimate.zero().to_dict()
        spent = (summary.get("consequential_g") or zero)["likely"] + args.month_to_date_g
        receipt = Receipt(
            subject_name=args.subject, subject_digest=args.digest.removeprefix("sha256:"),
            build={"energy_kwh": summary.get("energy_kwh", zero), "attributional_g": summary.get("attributional_g", zero),
                   "consequential_g": summary.get("consequential_g", zero), "water_l": summary.get("water_l", zero),
                   "surplus_energy_share": summary.get("surplus_energy_share", 0.0)},
            agents=json.loads(Path(args.agents).read_text()) if args.agents else {},
            runtime={}, signals=[], budget=Budget(_now().strftime("%Y-%m"), args.cap_g, spent),
            pipeline={k: os.environ.get(k, "") for k in ("CI_PROJECT_PATH", "CI_PIPELINE_ID", "CI_COMMIT_SHA", "CI_JOB_URL")})
        Path(args.out).write_text(json.dumps(receipt.predicate(), indent=2, sort_keys=True))
        print(f"wrote {args.out} ({receipt.predicate()['verdict']}); attest with: cosign attest --type "
              f"{os.environ.get('JOULE_PREDICATE_TYPE', PREDICATE_TYPE)} --predicate {args.out} <image@digest>")
        return 0
    statement = json.loads(Path(args.statement).read_text())
    if "payload" in statement:  # cosign verify-attestation output: DSSE envelope
        import base64

        statement = json.loads(base64.b64decode(statement["payload"]))
    problems = verify(statement, args.digest.removeprefix("sha256:") if args.digest else None,
                      Policy(predicate_type=os.environ.get("JOULE_PREDICATE_TYPE", PREDICATE_TYPE)))
    for p in problems:
        print(f"receipt: {p}", file=sys.stderr)
    print("receipt OK" if not problems else "receipt REJECTED")
    return 0 if not problems else 1


def cmd_control(args) -> int:
    from .carbon.ledger import Ledger
    from .gitlab import GitLab

    spent = Ledger(Path(args.ledger)).summary()["consequential_g"]["likely"] if Path(args.ledger).exists() else 0.0
    passed = spent + args.month_to_date_g <= args.cap_g
    print(f"carbon budget: {spent + args.month_to_date_g:.1f} / {args.cap_g:.1f} g -> {'pass' if passed else 'fail'}")
    if not args.dry_run:
        GitLab.from_env().set_external_control(args.control_id, passed, os.environ["JOULE_CONTROL_SECRET"])
    return 0 if passed else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="joule", description="Joule Thief")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("grid")
    p.add_argument("region")
    p.add_argument("--hours", type=int, default=36)
    p.set_defaults(fn=cmd_grid)

    p = sub.add_parser("tick")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--publish-plan", action="store_true", help="also post the plan as an issue")
    p.set_defaults(fn=cmd_tick)

    p = sub.add_parser("eco")
    p.add_argument("--region", default=os.environ.get("JOULE_REGION", "europe-north1"))
    p.add_argument("--flag", default="eco-mode")
    p.add_argument("--threshold-g", type=float, default=200.0)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_eco)

    p = sub.add_parser("ci-energy")
    p.add_argument("--machine", default="e2-standard-2")
    p.add_argument("--vcpus", type=float, default=2)
    p.add_argument("--memory-gb", type=float, default=8)
    p.add_argument("--utilisation", type=float, default=0.6)
    p.add_argument("--region", default="us-east1", help="GitLab.com hosted runners run in us-east1")
    p.add_argument("--marginal-g", type=float, default=None)
    p.add_argument("--minutes", type=float, default=5.0, help="fallback when CI_JOB_STARTED_AT is unset")
    p.add_argument("--ledger", default="ledger.jsonl")
    p.set_defaults(fn=cmd_ci_energy)

    p = sub.add_parser("pipeline-footprint")
    p.add_argument("--pipeline", default="")
    p.add_argument("--utilisation", type=float, default=0.6)
    p.add_argument("--marginal-g", type=float, default=None)
    p.add_argument("--ledger", default="ledger.jsonl")
    p.add_argument("--summary", default="footprint-summary.json")
    p.set_defaults(fn=cmd_pipeline_footprint)

    p = sub.add_parser("footprint")
    p.add_argument("--trace", required=True)
    p.add_argument("--provider", default="anthropic")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--zone", default=None)
    p.add_argument("--units", type=float, default=1.0)
    p.add_argument("--unit", default="resolved issue")
    p.set_defaults(fn=cmd_footprint)

    p = sub.add_parser("receipt")
    p.add_argument("action", choices=["build", "verify"])
    p.add_argument("--subject", default=os.environ.get("CI_REGISTRY_IMAGE", "artifact"))
    p.add_argument("--digest", default="")
    p.add_argument("--ledger", default="ledger.jsonl")
    p.add_argument("--agents", default="")
    p.add_argument("--cap-g", type=float, default=float(os.environ.get("JOULE_MONTHLY_CAP_G", "5000")))
    p.add_argument("--month-to-date-g", type=float, default=0.0)
    p.add_argument("--out", default="receipt.predicate.json")
    p.add_argument("--statement", default="attestation.json")
    p.set_defaults(fn=cmd_receipt)

    p = sub.add_parser("control")
    p.add_argument("--control-id", type=int, default=int(os.environ.get("JOULE_CONTROL_ID", "0")))
    p.add_argument("--ledger", default="ledger.jsonl")
    p.add_argument("--cap-g", type=float, default=float(os.environ.get("JOULE_MONTHLY_CAP_G", "5000")))
    p.add_argument("--month-to-date-g", type=float, default=0.0)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_control)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
