import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from joulethief.blame import SamplingProfiler, attribute, mr_delta_g_per_day, render_markdown
from joulethief.cli import main as cli
from joulethief.gitlab.client import GitLab, external_control_signature
from joulethief.loop import QUEUED, RUNNING, SCHEDULED, LoopConfig, tick
from joulethief.receipts.intoto import Budget, Policy, Receipt, verify
from joulethief.signals.base import Point, Series

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def rng(v):
    return {"low": v * 0.8, "likely": v, "high": v * 1.3}


def make_receipt(spent=100.0, cap=1000.0):
    return Receipt("registry.gitlab.com/x/app", "ab" * 32,
                   build={"energy_kwh": rng(0.01), "attributional_g": rng(1.0), "consequential_g": rng(2.0)},
                   agents={}, runtime={}, signals=[{"source": "s", "fetched_at": NOW.isoformat()}],
                   budget=Budget("2026-10", cap, spent))


def test_receipt_statement_and_policy():
    st = make_receipt().statement()
    assert st["_type"] == "https://in-toto.io/Statement/v1"
    assert verify(st, "ab" * 32, now=NOW) == []
    assert "subject digest does not match the artifact" in verify(st, "cd" * 32, now=NOW)
    over = make_receipt(spent=2000).statement()
    assert "carbon budget exceeded" in verify(over, now=NOW)
    stale = verify(st, now=NOW + timedelta(days=3))
    assert any("old" in p for p in stale)
    strict = verify(st, now=NOW, policy=Policy(max_build_consequential_g=1.0))
    assert any("limit" in p for p in strict)


def test_external_control_signature_matches_documented_scheme():
    sig = external_control_signature("s3cret", "1700000000", "abc", "/api/v4/projects/1/compliance_external_controls/2/status", "pass")
    import hashlib
    import hmac
    expected = hmac.new(b"s3cret", b"1700000000abc/api/v4/projects/1/compliance_external_controls/2/statuspass".replace(
        b"statuspass", b"statusstatus=pass"), hashlib.sha256).hexdigest()
    assert sig == expected


def test_profiler_attributes_cpu_to_lines(tmp_path):
    prof = SamplingProfiler(root=ROOT, interval_s=0.001).start()

    @prof.metered("/busy")
    def busy():
        total = 0
        for i in range(400_000):  # the hot line
            total += i * i
        return total

    for _ in range(5):
        busy()
    time.sleep(0.01)
    prof.stop()
    snap = prof.snapshot()
    assert snap["endpoints"]["/busy"]["requests"] == 5
    assert snap["endpoints"]["/busy"]["cpu_seconds"] > 0
    costs = attribute(snap, {"/busy": 10_000}, intensity_g_per_kwh=100.0)
    assert costs and costs[0].file == "tests/test_platform.py"
    assert costs[0].g_per_day > 0
    assert "Carbon blame" in render_markdown(costs)


def test_mr_delta_projection():
    # +0.5 J/request at 1M requests/day on a 400 g/kWh grid ≈ 55.6 g/day
    assert mr_delta_g_per_day(1.0, 1.5, 1_000_000, 400) == pytest.approx(55.56, rel=1e-3)


class FakeGitLab:
    def __init__(self, issues):
        self._issues = issues
        self.flows, self.notes, self.labels = [], [], []

    def issues(self, labels):
        return [i for i in self._issues if labels[0] in i["labels"]]

    def start_flow(self, goal, **kw):
        self.flows.append((goal, kw))
        return {"id": 1}

    def set_labels(self, iid, add=(), remove=()):
        self.labels.append((iid, list(add), list(remove)))

    def issue_note(self, iid, body):
        self.notes.append((iid, body))


class Signals:
    def decision_signal(self, region, now):
        # dirty now, clean in six hours
        vals = [500] * 12 + [20] * 8 + [500] * 60
        return Series(region, "m", "g", timedelta(minutes=30), [Point(NOW + i * timedelta(minutes=30), v) for i, v in enumerate(vals)], "t")


def test_hands_off_tick_holds_deferrable_and_starts_urgent():
    issues = [
        {"iid": 1, "title": "Upgrade deps", "labels": [QUEUED, "priority::low", "energy::dependency_upgrade"], "created_at": "2026-10-06T11:00:00Z"},
        {"iid": 2, "title": "Prod is down", "labels": [QUEUED, "priority::critical"], "created_at": "2026-10-06T11:55:00Z"},
    ]
    gl = FakeGitLab(issues)
    report = tick(gl, Signals(), LoopConfig(regions=("europe-north1",), flow_consumer_id=7), NOW)
    assert report.started == ["#2"] and report.held == ["#1"]
    assert gl.flows[0][1]["consumer_id"] == 7 and gl.flows[0][1]["issue_iid"] == 2
    assert (2, [RUNNING], [QUEUED, SCHEDULED]) in gl.labels
    assert (1, [SCHEDULED], [QUEUED]) in gl.labels
    held_note = dict(gl.notes)[1]
    assert "@grid" in held_note and "Surge Request" in held_note


def test_gitlab_client_requests_are_well_formed():
    calls = []

    def transport(method, url, headers, body):
        calls.append((method, url, headers, json.loads(body) if body else None))
        return 201, b'{"id": 5}'

    gl = GitLab("https://gitlab.com/api/v4", "tok", "group/proj", transport=transport)
    gl.start_flow("do it", consumer_id=3, issue_iid=9)
    method, url, headers, body = calls[-1]
    assert url.endswith("/ai/duo_workflows/workflows") and body["start_workflow"] is True
    assert body["allow_agent_to_request_user"] is False and body["ai_catalog_item_consumer_id"] == 3
    assert headers["PRIVATE-TOKEN"] == "tok"
    gl.set_feature_flag("eco-mode", True)
    assert calls[-1][1].endswith("/projects/group%2Fproj/feature_flags/eco-mode") and calls[-1][3] == {"active": True}


def test_cli_receipt_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli(["ci-energy", "--minutes", "10", "--ledger", "ledger.jsonl"]) == 0
    assert cli(["receipt", "build", "--digest", "sha256:" + "ab" * 32, "--subject", "img", "--cap-g", "1000"]) == 0
    predicate = json.loads((tmp_path / "receipt.predicate.json").read_text())
    statement = {"_type": "https://in-toto.io/Statement/v1", "subject": [{"name": "img", "digest": {"sha256": "ab" * 32}}],
                 "predicateType": "urn:joulethief:carbon-receipt:v1", "predicate": predicate}
    (tmp_path / "attestation.json").write_text(json.dumps(statement))
    assert cli(["receipt", "verify", "--digest", "ab" * 32]) == 0


def test_app_endpoints_offline():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        assert client.get("/healthz").json()["ok"]
        regions = client.get("/api/regions").json()
        assert any(r["region"] == "europe-north1" for r in regions)
        grid = client.get("/api/grid/europe-southwest1").json()
        assert grid["points"] and grid["mode"]
        cmp = client.get("/api/compare").json()
        assert cmp["points"] > 0
        assert client.get("/api/results/autonomy").status_code in (200, 404)
        assert "markdown" in client.get("/api/blame").json()
        assert client.post("/api/tick").status_code == 403
        assert "Joule Thief" in client.get("/").text


def test_mcp_tools_registered():
    import asyncio

    from joulethief.mcp_server import server

    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"grid_signal", "plan_work", "estimate_agent_footprint", "explain_region", "check_carbon_receipt",
            "autonomy_dividend"} <= names


class PricedSignals(Signals):
    def prices(self, zone, now):
        return Series(zone, "day_ahead_price", "EUR / MWh", timedelta(hours=1), [Point(NOW, -2.5)], "t")


def test_tick_releases_only_the_current_slot_and_explains_urgency():
    issues = [{"iid": 3, "title": "Hotfix", "labels": [QUEUED, "priority::critical"], "created_at": "2026-10-06T11:58:00Z"}]
    gl = FakeGitLab(issues)
    tick(gl, Signals(), LoopConfig(regions=("europe-north1",)), NOW)
    note = dict(gl.notes)[3]
    # dirty now (500), clean from 18:00 (20): the price of urgency is the difference, not "0.0 g"
    assert "waiting until Tue 18:00 UTC would have saved about" in note and "**0.0 g**" not in note
    # Clock skew: GitLab stamped the issue a few seconds after our "now"; critical still never waits.
    skewed = [{"iid": 7, "title": "Outage", "labels": [QUEUED, "priority::critical"], "created_at": "2026-10-06T12:00:05Z"}]
    assert tick(FakeGitLab(skewed), Signals(), LoopConfig(regions=("europe-north1",)), NOW).started == ["#7"]
    # A job whose clean slot opens in 30 minutes is held, not started early in the dirty slot.
    soon = [{"iid": 4, "title": "Deps", "labels": [QUEUED, "priority::high"], "created_at": "2026-10-06T12:00:00Z"}]
    vals = [500] + [20] * 10 + [500] * 69
    class Soon:
        def decision_signal(self, region, now):
            return Series(region, "m", "g", timedelta(minutes=30), [Point(NOW + i * timedelta(minutes=30), v) for i, v in enumerate(vals)], "t")
    gl = FakeGitLab(soon)
    report = tick(gl, Soon(), LoopConfig(regions=("europe-north1",)), NOW)
    assert report.held == ["#4"] and not gl.flows
    report = tick(FakeGitLab(soon), Soon(), LoopConfig(regions=("europe-north1",)), NOW + timedelta(minutes=30))
    assert report.started == ["#4"]


def test_release_note_names_a_surplus_price():
    issues = [{"iid": 5, "title": "Matrix", "labels": [QUEUED, "priority::high"], "created_at": "2026-10-06T11:00:00Z"}]
    flat = [20] * 80
    class Clean(PricedSignals):
        def decision_signal(self, region, now):
            return Series(region, "m", "g", timedelta(minutes=30), [Point(NOW + i * timedelta(minutes=30), v) for i, v in enumerate(flat)], "t")
    gl = FakeGitLab(issues)
    tick(gl, Clean(), LoopConfig(regions=("europe-north1",)), NOW)
    assert "-2.5 €/MWh" in dict(gl.notes)[5] and "surplus" in dict(gl.notes)[5]


def test_deferred_work_is_explained_once(monkeypatch):
    import joulethief.loop as loop_module
    from joulethief.dispatch.optimizer import Plan

    issues = [{"iid": 6, "title": "Scan", "labels": [QUEUED, "priority::low", "energy::security_scan"], "created_at": "2026-10-06T12:00:00Z"}]
    monkeypatch.setattr(loop_module, "plan", lambda *a, **k: Plan(NOW, timedelta(minutes=30), [], ["#6"], 0.0, 0.0, "stub", "OPTIMAL"))
    gl = FakeGitLab(issues)
    report = tick(gl, Signals(), LoopConfig(regions=("europe-north1",)), NOW)
    assert report.deferred == ["#6"] and (6, [SCHEDULED], [QUEUED]) in gl.labels
    assert "keeping this Surge Request in the battery" in dict(gl.notes)[6] and "Deadline" in dict(gl.notes)[6]
    issues[0]["labels"] = [SCHEDULED, "priority::low", "energy::security_scan"]
    gl = FakeGitLab(issues)
    tick(gl, Signals(), LoopConfig(regions=("europe-north1",)), NOW + timedelta(minutes=30))
    assert gl.notes == []  # said once, not every tick


def test_webhook_ticks_only_for_new_or_critical_surge_requests():
    from joulethief.loop import webhook_wants_tick

    def event(labels, previous=None, action="update", state="opened"):
        e = {"object_kind": "issue", "object_attributes": {"action": action, "state": state},
             "labels": [{"title": x} for x in labels]}
        if previous is not None:
            e["changes"] = {"labels": {"previous": [{"title": x} for x in previous], "current": e["labels"]}}
        return e

    assert webhook_wants_tick(event([QUEUED, "priority::low"], previous=["priority::low"]))  # intake just triaged it
    assert webhook_wants_tick(event([QUEUED, "priority::critical"], action="open"))
    assert webhook_wants_tick(event([SCHEDULED, "priority::critical"], previous=[SCHEDULED, "priority::low"]))
    assert not webhook_wants_tick(event([SCHEDULED], previous=[QUEUED]))  # the loop's own relabelling
    assert not webhook_wants_tick(event([RUNNING], previous=[SCHEDULED]))
    assert not webhook_wants_tick(event([QUEUED], action="update"))  # no label change: an edit
    assert not webhook_wants_tick(event([QUEUED], action="open", state="closed"))
    assert not webhook_wants_tick({"object_kind": "merge_request"})


def test_webhook_endpoint_requires_the_key(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("JOULE_TICK_KEY", "k")
    client = TestClient(app)  # no lifespan: the MCP session manager runs once per process
    assert client.post("/api/webhook/gitlab", json={}).status_code == 403
    r = client.post("/api/webhook/gitlab", json={"object_kind": "note"}, headers={"X-Gitlab-Token": "k"})
    assert r.status_code == 200 and r.json()["ticked"] is False


def test_demo_replays_the_hands_off_loop_end_to_end():
    from joulethief.demo import markdown, run

    result = run("es", days=4, filing_days=2, per_day=3)
    s = result["summary"]
    assert s["shipped"] == s["issues"] and s["late"] == 0
    assert s["hands_off_g"] < s["run_now_g"] and s["surplus_share"] > 0.5
    assert s["flows_started"] + s["pipelines_started"] == s["issues"]
    assert all(i["state"] == "closed" for i in result["issues"])
    critical = next(r for r in result["runs"] if r["priority"] == "critical")
    assert critical["wait_h"] == 0 and critical["on_time"]  # the webhook tick starts it at once
    assert result["timeline"] and {"queued_kwh", "signal", "price"} <= set(result["timeline"][0])
    text = markdown(result)
    assert "@grid" in text and "Shipped" in text and "Production returns 500" in text


def test_battery_replay_and_queue_endpoints(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    for var in ("JOULE_GITLAB_TOKEN", "JOULE_PROJECT", "CI_PROJECT_ID"):
        monkeypatch.delenv(var, raising=False)
    client = TestClient(app)  # no lifespan: the MCP session manager runs once per process
    assert client.get("/api/queue").json() == {"configured": False}
    replay = client.get("/api/results/battery")
    assert replay.status_code == 200
    body = replay.json()
    assert body["summary"]["late"] == 0 and body["timeline"] and body["events"]


def test_bootstrap_is_idempotent_and_well_formed():
    from joulethief.gitlab.bootstrap import Bootstrap

    calls = []
    existing = {"/labels": [{"name": "priority::low"}], "/feature_flags": [{"name": "eco-mode"}],
                "/pipeline_schedules": [{"description": "Joule Thief: eco-mode"}], "/hooks": []}

    def transport(method, url, headers, body):
        calls.append((method, url.split("?")[0], json.loads(body) if body else None))
        if method == "GET":
            path = "/" + url.split("?")[0].rsplit("/", 1)[1]
            return 200, json.dumps(existing[path]).encode()
        return 201, b'{"id": 9}'

    gl = GitLab("https://gitlab.com/api/v4", "tok", "g/p", transport=transport)
    log = Bootstrap(gl, service_url="https://jt.run.app/", tick_key="k").run()
    posts = [(u, b) for m, u, b in calls if m == "POST"]
    labels = [b["name"] for u, b in posts if u.endswith("/labels")]
    assert "surge::queued" in labels and "priority::low" not in labels and "exists  label: priority::low" in log
    assert not any(u.endswith("/feature_flags") for u, _ in posts)
    created = [b for u, b in posts if u.endswith("/pipeline_schedules")]
    assert {b["description"] for b in created} == {"Joule Thief: dispatcher tick", "Joule Thief: daily dispatch plan"}
    assert ("https://gitlab.com/api/v4/projects/g%2Fp/pipeline_schedules/9/variables", {"key": "JOULE_TASK", "value": "tick"}) in posts
    hook = next(b for u, b in posts if u.endswith("/hooks"))
    assert hook == {"url": "https://jt.run.app/api/webhook/gitlab", "token": "k", "issues_events": True,
                    "push_events": False, "enable_ssl_verification": True}
    assert all(m == "GET" or m == "POST" for m, _, _ in calls)
