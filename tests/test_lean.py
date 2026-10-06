"""Deterministic-first replacements for LLM work: the MR energy gate and the "Shipped" note."""

import json
from urllib.parse import unquote, urlparse

import pytest

from joulethief import voice
from joulethief.blame.gate import compare
from joulethief.cli import main as cli
from joulethief.gitlab import client as gitlab_client
from joulethief.gitlab.client import GitLab


def bench(compare_j, grid_j=0.002, lines=()):
    return {"endpoints": {"/api/compare": {"joules_per_request": compare_j}, "/api/grid": {"joules_per_request": grid_j}},
            "traffic": {"/api/compare": 2000, "/api/grid": 20000}, "intensity_g_per_kwh": 40,
            "lines": list(lines)}


HOT = {"file": "app/insights.py", "line": 19, "function": "weekly_pairs", "g_per_day": 0.41}


def test_gate_quiet_when_nothing_material():
    gate = compare(bench(0.10), bench(0.105, lines=[HOT]), ["README.md"])
    assert not gate.needs_reviewer
    assert gate.deltas[0].change == pytest.approx(0.05)
    assert "no LLM review needed" in voice.energy_check(gate, "main", "")


def test_gate_wakes_reviewer_on_regression_or_hot_line():
    regressed = compare(bench(0.10), bench(0.15), [])
    assert regressed.reasons == ["/api/compare: +50% J/request"]
    assert regressed.deltas[0].g_per_day == pytest.approx(0.05 / 3.6e6 * 40 * 2000)
    hot = compare(bench(0.10), bench(0.10, lines=[HOT]), ["app/insights.py"])
    assert hot.needs_reviewer and "app/insights.py:19" in hot.reasons[0]
    first = compare(None, bench(0.1), [])  # target branch has no benchmark yet
    assert not first.needs_reviewer and first.deltas[0].base_j is None


class FakeGitLabAPI:
    """Just enough of the REST API, behind the client's transport."""

    def __init__(self, base_benchmark=None, changed=(), notes=(), jobs=(), mrs=(), closes=(), issue_notes=()):
        self.base_benchmark, self.changed, self.notes = base_benchmark, list(changed), list(notes)
        self.issue_notes = list(issue_notes)
        self.jobs, self.mrs, self.closes = list(jobs), list(mrs), list(closes)
        self.calls = []

    def __call__(self, method, url, headers, body):
        path = unquote(urlparse(url).path).split("/projects/7", 1)[-1]
        payload = json.loads(body) if body else None
        self.calls.append((method, path, payload))
        if "/jobs/artifacts/" in path:
            return (200, json.dumps(self.base_benchmark).encode()) if self.base_benchmark else (404, b"")
        routes = {
            ("GET", "/merge_requests/3/diffs"): [{"new_path": f} for f in self.changed],
            ("GET", "/merge_requests/3/notes"): self.notes,
            ("GET", "/pipelines/99/jobs"): self.jobs,
            ("GET", "/repository/commits/abcdef1234/merge_requests"): self.mrs,
            ("GET", "/merge_requests/3/closes_issues"): self.closes,
            ("GET", "/issues/8/notes"): self.issue_notes,
        }
        if (method, path) in routes:
            return 200, json.dumps(routes[(method, path)]).encode()
        return 201, b'{"id": 1}'

    def posted(self, method, fragment):
        return [p for m, path, p in self.calls if m == method and fragment in path]


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for k, v in {"CI_MERGE_REQUEST_IID": "3", "CI_MERGE_REQUEST_TARGET_BRANCH_NAME": "main", "CI_COMMIT_SHA": "abcdef1234",
                 "CI_PIPELINE_ID": "99", "CI_PIPELINE_IID": "12"}.items():
        monkeypatch.setenv(k, v)

    def install(api, consumer=None):
        if consumer:
            monkeypatch.setenv("JOULE_REVIEWER_CONSUMER_ID", consumer)
        monkeypatch.setattr(gitlab_client.GitLab, "from_env",
                            classmethod(lambda cls: GitLab("https://gitlab.example/api/v4", "t", "7", transport=api)))
        return api
    return install


def test_energy_gate_cli_starts_reviewer_once(fake, tmp_path):
    (tmp_path / "benchmark.json").write_text(json.dumps(bench(0.2)))
    api = fake(FakeGitLabAPI(base_benchmark=bench(0.1)), consumer="42")
    assert cli(["energy-gate"]) == 0
    flows = api.posted("POST", "/ai/duo_workflows/workflows")
    assert len(flows) == 1 and flows[0]["ai_catalog_item_consumer_id"] == 42 and "!3" in flows[0]["goal"]
    note = api.posted("POST", "/merge_requests/3/notes")[0]["body"]
    assert voice.ENERGY_CHECK_MARKER in note and "+100%" in note

    # Same findings on the next push: the note is edited, the agent is not woken again.
    api2 = fake(FakeGitLabAPI(base_benchmark=bench(0.1), notes=[{"id": 5, "body": note}]), consumer="42")
    assert cli(["energy-gate"]) == 0
    assert not api2.posted("POST", "/ai/duo_workflows/workflows")
    assert api2.posted("PUT", "/merge_requests/3/notes/5")


def test_energy_gate_cli_quiet_without_regression(fake, tmp_path):
    (tmp_path / "benchmark.json").write_text(json.dumps(bench(0.1)))
    api = fake(FakeGitLabAPI(base_benchmark=bench(0.1), changed=["docs/DESIGN.md"]), consumer="42")
    assert cli(["energy-gate"]) == 0
    assert not api.posted("POST", "/ai/duo_workflows/workflows")


def footprint():
    r = {"low": 1.0, "likely": 2.0, "high": 3.0}
    return {"entries": 14, "energy_kwh": {"low": 0.01, "likely": 0.02, "high": 0.03}, "attributional_g": r,
            "consequential_g": r}


def test_shipped_note_and_label(fake, tmp_path):
    (tmp_path / "footprint-summary.json").write_text(json.dumps(footprint()))
    (tmp_path / "receipt.predicate.json").write_text(json.dumps(
        {"verdict": "within-budget", "budget": {"period": "2026-10", "capG": 5000, "spentG": 120.5}, "agents": {}}))
    (tmp_path / "canary-report.json").write_text(json.dumps(
        {"canary_j_per_request": {"/api/compare": 0.01}, "prod_j_per_request": {"/api/compare": 0.02}}))
    jobs = [{"name": "monitor:promote", "status": "success"}, {"name": "release:gitlab-release", "status": "success"},
            {"name": "monitor:canary-energy", "status": "failed", "retried": True},
            {"name": "monitor:canary-energy", "status": "success"}]
    api = fake(FakeGitLabAPI(jobs=jobs, mrs=[{"iid": 3, "state": "merged"}], closes=[{"iid": 8}]))
    assert cli(["shipped", "--region", "europe-north1"]) == 0
    note = api.posted("POST", "/issues/8/notes")[0]["body"]
    assert "Shipped" in note and "Hamina" in note and "v0.1.12" in note
    assert "2.00 (1.00–3.00)" in note and "-50%" in note and "within-budget" in note
    assert api.posted("PUT", "/issues/8")[0]["remove_labels"] == "surge::running"


@pytest.mark.parametrize("failed", ["monitor:canary-energy", "verify:test"])
def test_shipped_skips_blocked_delivery(fake, tmp_path, failed):
    jobs = [{"name": failed, "status": "failed"}, {"name": "secret_detection", "status": "failed", "allow_failure": True}]
    api = fake(FakeGitLabAPI(jobs=jobs, mrs=[{"iid": 3, "state": "merged"}], closes=[{"iid": 8}]))
    assert cli(["shipped"]) == 0
    assert not api.posted("POST", "/issues/8/notes")


def test_shipped_is_idempotent_and_tolerates_allowed_failures(fake, tmp_path):
    jobs = [{"name": "secret_detection", "status": "failed", "allow_failure": True}]
    already = [{"id": 1, "body": voice.shipped_marker("abcdef1234") + " Shipped"}]
    api = fake(FakeGitLabAPI(jobs=jobs, mrs=[{"iid": 3, "state": "merged"}], closes=[{"iid": 8}], issue_notes=already))
    assert cli(["shipped"]) == 0
    assert not api.posted("POST", "/issues/8/notes")
    api = fake(FakeGitLabAPI(jobs=jobs, mrs=[{"iid": 3, "state": "merged"}], closes=[{"iid": 8}]))
    assert cli(["shipped"]) == 0
    assert "is merged (not deployed)" in api.posted("POST", "/issues/8/notes")[0]["body"]
