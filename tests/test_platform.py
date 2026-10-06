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
    assert {"grid_signal", "best_window", "plan_work", "estimate_agent_footprint", "explain_region", "check_carbon_receipt",
            "autonomy_dividend"} <= names
