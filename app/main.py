"""Joule Thief control room: dashboard, grid API, carbon blame, dispatcher tick and MCP server.

Runs on Cloud Run's free tier (scale to zero) in a low-carbon region. Every handler that
does real work is metered, so the app can carbon-blame itself.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from joulethief.blame import SamplingProfiler, attribute, render_markdown
from joulethief.carbon.ledger import Ledger
from joulethief.live import LiveSignals
from joulethief.signals.base import Series
from joulethief.signals.marginal import PriceMarginalModel, surplus_windows
from joulethief.signals.regions import REGIONS, google_region_carbon
from joulethief.signals.snapshots import es_prices, gb_intensity

from .flags import FeatureFlags
from .insights import compare

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
RESULTS = ROOT / "docs" / "results" / "autonomy_dividend.json"
BATTERY = ROOT / "docs" / "results" / "battery_replay.json"  # `joule demo --json ...`
STARTED = time.time()

profiler = SamplingProfiler(root=ROOT)
flags = FeatureFlags()
signals = LiveSignals()
_grid_cache: dict[str, tuple[float, dict]] = {}
_queue_cache: dict[str, tuple[float, dict]] = {}
_tick_lock = threading.Lock()  # one tick at a time: a webhook and the heartbeat must not both start a flow

try:
    from joulethief.mcp_server import http_app as _mcp_http_app
    from joulethief.mcp_server import server as _mcp_server

    _mcp_app = _mcp_http_app()
except Exception:  # noqa: BLE001 — the dashboard must run even without the MCP extra
    _mcp_server = _mcp_app = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not flags.enabled("eco-mode"):
        profiler.start()
    if _mcp_app is not None and hasattr(_mcp_server, "session_manager"):
        async with _mcp_server.session_manager.run():
            yield
    else:
        yield
    profiler.stop()


app = FastAPI(title="Joule Thief", version="0.1.0", lifespan=lifespan)


def _series_payload(s: Series, mode: str, hours_back: int = 12, hours_fwd: int = 36, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    window = s.slice(now - timedelta(hours=hours_back), now + timedelta(hours=hours_fwd))
    if not len(window):  # replay data: show its last 48 h
        window = s.slice(s.end - timedelta(hours=hours_back + hours_fwd), s.end)
    return {"metric": s.metric, "unit": s.unit, "source": s.source, "mode": mode,
            "points": [{"t": p.start.isoformat(), "v": round(p.value, 2)} for p in window]}


def _replay(region: str) -> tuple[Series, str] | None:
    if region == "europe-southwest1":
        prices = es_prices()
        return PriceMarginalModel().series(prices), "replay: OMIE 2025 day-ahead"
    if region == "europe-west2":
        return gb_intensity(), "replay: NESO Sep–Oct 2026"
    return None


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "uptime_s": round(time.time() - STARTED), "eco_mode": flags.enabled("eco-mode")}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/regions")
def regions() -> list[dict]:
    carbon = google_region_carbon()
    return [{"region": name, "city": r.city, "price_zone": r.price_zone, "signal": r.intensity_source,
             "cooling": r.cooling, "notes": r.notes,
             "google_cfe": carbon[name].google_cfe if name in carbon else None,
             "grid_intensity_avg": carbon[name].grid_intensity_avg if name in carbon else None}
            for name, r in REGIONS.items()]


@app.get("/api/grid/{region}")
@profiler.metered("/api/grid")
def grid(region: str) -> dict:
    if region not in REGIONS:
        raise HTTPException(404, f"unknown region {region}")
    ttl = 3600 if flags.enabled("eco-mode") else 900  # demand shaping: cache longer when the grid is dirty
    cached = _grid_cache.get(region)
    if cached and time.time() - cached[0] < ttl:
        return cached[1]
    now = datetime.now(timezone.utc)
    try:
        series = signals.decision_signal(region, now)
        payload = _series_payload(series, "live" if series.kind != "derived" else "annual", now=now)
        zone = REGIONS[region].price_zone
        if zone:
            payload["surplus_windows"] = [{"start": s.isoformat(), "end": e.isoformat(), "min_price": m}
                                          for s, e, m in surplus_windows(signals.prices(zone, now))]
    except Exception as err:  # noqa: BLE001 — offline or source down: fall back to labelled replay data
        replay = _replay(region)
        if replay is None:
            series = signals.flat(region, now)
            payload = _series_payload(series, "annual", now=now)
        else:
            payload = _series_payload(replay[0], replay[1], now=now)
        payload["fallback_reason"] = type(err).__name__
    _grid_cache[region] = (time.time(), payload)
    return payload


@app.get("/api/compare")
@profiler.metered("/api/compare")
def compare_regions(a: str = "europe-southwest1", b: str = "europe-west2") -> dict:
    sa, sb = _replay(a), _replay(b)
    if not sa or not sb:
        raise HTTPException(400, "comparison is available for regions with replay data")
    hourly_a = sa[0].resample(timedelta(hours=1))
    hourly_b = sb[0].resample(timedelta(hours=1))
    return compare(hourly_a, hourly_b)


@app.get("/api/results/autonomy")
def autonomy() -> JSONResponse:
    if not RESULTS.exists():
        raise HTTPException(404, "no results yet")
    return JSONResponse(json.loads(RESULTS.read_text()))


@app.get("/api/results/battery")
def battery() -> JSONResponse:
    """A real week of hands-off operation replayed by ``joule demo``: the backlog charging and discharging."""
    if not BATTERY.exists():
        raise HTTPException(404, "run: joule demo --json docs/results/battery_replay.json")
    return JSONResponse(json.loads(BATTERY.read_text()))


@app.get("/api/queue")
@profiler.metered("/api/queue")
def queue() -> dict:
    """The live battery: open Surge Requests and the dispatcher's current plan (a read-only, dry-run tick)."""
    if not (os.environ.get("JOULE_GITLAB_TOKEN") and (os.environ.get("JOULE_PROJECT") or os.environ.get("CI_PROJECT_ID"))):
        return {"configured": False}
    ttl = 1800 if flags.enabled("eco-mode") else 600
    cached = _queue_cache.get("queue")
    if cached and time.time() - cached[0] < ttl:
        return cached[1]
    from joulethief.gitlab import GitLab
    from joulethief.loop import QUEUED, RUNNING, SCHEDULED, LoopConfig, tick

    gl, now = GitLab.from_env(), datetime.now(timezone.utc)
    try:
        report = tick(gl, signals, LoopConfig(dry_run=True), now)  # dry run: no notes, labels or flows
        issues = {i["iid"]: i for label in (QUEUED, SCHEDULED, RUNNING) for i in gl.issues([label])}
    except Exception as err:  # noqa: BLE001 — GitLab or the grid unreachable: say so, keep the page up
        return {"configured": True, "error": type(err).__name__}
    rows = []
    for iid, issue in issues.items():
        a = report.plan.assignment(f"#{iid}")
        status = ("running" if RUNNING in issue.get("labels", []) else "starts now" if f"#{iid}" in report.started
                  else "waiting for a cleaner window" if f"#{iid}" in report.deferred else "held")
        rows.append({"iid": iid, "title": issue.get("title", ""), "url": issue.get("web_url", ""),
                     "labels": [x for x in issue.get("labels", []) if x.split("::")[0] in ("priority", "energy")],
                     "status": status, "start": a.start.isoformat() if a else None,
                     "region": a.region if a else None, "expected_g": round(a.expected_g, 2) if a else None})
    payload = {"configured": True, "at": now.isoformat(timespec="seconds"), "rows": sorted(rows, key=lambda r: r["iid"]),
               "expected_g": round(report.plan.expected_g, 2), "baseline_g": round(report.plan.baseline_g, 2)}
    _queue_cache["queue"] = (time.time(), payload)
    return payload


@app.get("/api/ledger")
def ledger() -> dict:
    path = Path(os.environ.get("JOULE_LEDGER", ROOT / "ledger.jsonl"))
    return Ledger(path).summary() if path.exists() else {"entries": 0}


@app.get("/api/blame")
def blame(intensity: float = 50.0) -> dict:
    snap = profiler.snapshot()
    uptime_days = max((time.time() - STARTED) / 86400, 1e-6)
    per_day = {ep: v["requests"] / uptime_days for ep, v in snap["endpoints"].items()}
    costs = attribute(snap, per_day, intensity)
    return {"endpoints": snap["endpoints"],
            "lines": [c.__dict__ for c in costs[:20]],
            "markdown": render_markdown(costs, intensity_label=f"{intensity:.0f} gCO₂/kWh")}


def _require_key(given: str, header: str) -> None:
    expected = os.environ.get("JOULE_TICK_KEY")
    if not expected or given != expected:
        raise HTTPException(403, f"missing or wrong {header}")


def _locked_tick() -> dict:
    if not _tick_lock.acquire(blocking=False):
        return {"ticked": False, "reason": "a tick is already running"}
    try:
        from joulethief.gitlab import GitLab
        from joulethief.loop import LoopConfig, tick

        cfg = LoopConfig(flow_consumer_id=int(os.environ["JOULE_FLOW_CONSUMER_ID"]) if os.environ.get("JOULE_FLOW_CONSUMER_ID") else None,
                         dry_run=os.environ.get("JOULE_DRY_RUN") == "1")
        report = tick(GitLab.from_env(), signals, cfg, datetime.now(timezone.utc))
    finally:
        _tick_lock.release()
    return {"ticked": True, "plan": report.plan.to_dict(), "started": report.started, "held": report.held,
            "deferred": report.deferred, "notes": report.notes}


@app.post("/api/tick")
def run_tick(x_joule_key: str = Header(default="")) -> dict:
    """The heartbeat (Cloud Scheduler or a pipeline schedule, every 30 minutes)."""
    _require_key(x_joule_key, "X-Joule-Key")
    return _locked_tick()


@app.post("/api/webhook/gitlab")
def gitlab_webhook(event: dict = Body(default={}), x_gitlab_token: str = Header(default="")) -> dict:
    """GitLab issue events: tick at once for a new or critical Surge Request instead of waiting for the heartbeat."""
    from joulethief.loop import webhook_wants_tick

    _require_key(x_gitlab_token, "X-Gitlab-Token")
    if not webhook_wants_tick(event):
        return {"ticked": False, "reason": "not a new or critical Surge Request"}
    return _locked_tick()


@app.get("/api/receipt/schema", response_class=PlainTextResponse)
def receipt_schema() -> str:
    return (ROOT / "docs" / "RECEIPT.md").read_text() if (ROOT / "docs" / "RECEIPT.md").exists() else ""


if _mcp_app is not None:
    app.mount("/", _mcp_app)  # serves /mcp; mounted last so the routes above take precedence
