"""Regressions found by replaying the real loop on a real week (experiments/loop_replay.py)."""

from datetime import datetime, timedelta, timezone

import pytest

from joulethief import voice
from joulethief.dispatch.jobs import Job
from joulethief.dispatch.optimizer import plan
from joulethief.loop import QUEUED, RUNNING, SCHEDULED, LoopConfig, cheapest_start, tick, wants_tick
from joulethief.signals.base import Point, Series

T0 = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
SLOT = timedelta(minutes=30)


def signal(values, history=()):
    """``history`` lies before T0 (already known), ``values`` from T0 on."""
    pts = [Point(T0 - (len(history) - i) * SLOT, v) for i, v in enumerate(history)]
    pts += [Point(T0 + i * SLOT, v) for i, v in enumerate(values)]
    return Series("r1", "m", "gCO2/kWh", SLOT, pts, "test")


class Signals:
    def __init__(self, values, history=()):
        self.values, self.history = values, history

    def decision_signal(self, region, now):
        return signal(self.values, self.history)


class FakeGitLab:
    def __init__(self, issues):
        self._issues = issues
        self.notes, self.labels, self.flows = [], [], []

    def issues(self, labels):
        return [i for i in self._issues if labels[0] in i["labels"]]

    def issue_note(self, iid, body):
        self.notes.append((iid, body))

    def set_labels(self, iid, add=(), remove=()):
        self.labels.append((iid, list(add), list(remove)))

    def start_flow(self, goal, **kw):
        self.flows.append(kw)

    def run_pipeline(self, ref, variables):
        self.flows.append(variables)


def issue(iid, priority, kind="agent_session", created=T0):
    return {"iid": iid, "title": "t", "labels": [QUEUED, f"priority::{priority}", f"energy::{kind}"],
            "created_at": created.isoformat()}


def test_partial_slot_jobs_are_billed_their_real_energy():
    # A 40-minute job touches two 30-minute slots but must not be billed for 60 minutes.
    j = Job("a", timedelta(minutes=40), 0.3, T0, T0 + timedelta(hours=2), ("r1",))
    p = plan([j], {"r1": signal([100] * 8)}, T0, horizon=timedelta(hours=4))
    assert p.assignment("a").expected_g == pytest.approx(j.energy_kwh * 100, rel=1e-3)


@pytest.mark.parametrize("use_solver", [True, False])
def test_defer_never_beats_running_at_the_same_intensity(use_solver):
    # Deadline beyond the horizon and a flat signal: running now is as clean as deferring, so run.
    j = Job("a", timedelta(minutes=40), 0.3, T0, T0 + timedelta(hours=72), ("r1",))
    p = plan([j], {"r1": signal([11] * 24)}, T0, horizon=timedelta(hours=12), use_solver=use_solver)
    assert not p.deferred and p.assignment("a").start == T0


def test_deferred_work_gets_a_note_and_leaves_the_queue():
    # A clean week behind, a dirty evening in view, tomorrow's prices not out yet: wait, and say so.
    gl = FakeGitLab([issue(1, "low")])
    report = tick(gl, Signals([490] * 12, history=[100] * 336), LoopConfig(regions=("r1",)), T0)
    assert report.started == [] and report.held == ["#1"]
    assert report.plan.deferred == ["#1"] and report.plan.typical["r1"] == 100
    assert (1, [SCHEDULED], [QUEUED]) in gl.labels
    assert "comes close to a good hour here (≈100" in gl.notes[0][1]
    # Flat signal, no better history: running now is as good as waiting, so it runs.
    gl = FakeGitLab([issue(2, "low")])
    assert tick(gl, Signals([490] * 72, history=[490] * 48), LoopConfig(regions=("r1",)), T0).started == ["#2"]


def test_work_planned_for_the_next_slot_waits_for_the_next_tick():
    # Dirty now, clean from the next slot on: do not start early in the dirty slot.
    gl = FakeGitLab([issue(1, "normal")])
    report = tick(gl, Signals([500] + [20] * 71), LoopConfig(regions=("r1",)), T0)
    assert report.started == [] and report.held == ["#1"]
    assert (1, [SCHEDULED], [QUEUED]) in gl.labels


def test_urgent_note_states_the_real_cost_of_not_waiting():
    gl = FakeGitLab([issue(7, "critical")])
    values = [490] * 4 + [11] * 68
    report = tick(gl, Signals(values), LoopConfig(regions=("r1",)), T0)
    assert report.started == ["#7"] and (7, [RUNNING], [QUEUED, SCHEDULED]) in gl.labels
    duration, power = timedelta(minutes=40), 0.35
    j = Job("#7", duration, power, T0, T0 + duration)
    grams, at = cheapest_start(signal(values), j, T0, timedelta(hours=36))
    assert at == T0 + 4 * SLOT and grams == pytest.approx(j.energy_kwh * 11)
    note = report.notes["#7"]
    assert "never waits" in note and f"{j.energy_kwh * (490 - 11):.1f} g" in note
    assert ".." not in voice.releasing("europe-north1", 11, None)


def label(title):
    return {"title": title}


def test_webhook_wakes_the_dispatcher_only_for_new_surge_requests():
    opened = {"object_kind": "issue", "object_attributes": {"action": "open"}, "labels": [label(QUEUED)]}
    assert wants_tick(opened)
    triaged = {"object_kind": "issue", "object_attributes": {"action": "update"}, "labels": [label(QUEUED)],
               "changes": {"labels": {"previous": [], "current": [label(QUEUED)]}}}
    assert wants_tick(triaged)
    # The dispatcher's own relabelling (queued -> scheduled / running) must not wake it again.
    own = {"object_kind": "issue", "object_attributes": {"action": "update"}, "labels": [label(SCHEDULED)],
           "changes": {"labels": {"previous": [label(QUEUED)], "current": [label(SCHEDULED)]}}}
    assert not wants_tick(own)
    edited = {"object_kind": "issue", "object_attributes": {"action": "update"}, "labels": [label(QUEUED)],
              "changes": {"title": {"previous": "a", "current": "b"}, "labels": {"previous": [label(QUEUED)]}}}
    assert not wants_tick(edited)
    assert not wants_tick({"object_kind": "merge_request", "labels": [label(QUEUED)]})


def test_webhook_endpoint_is_authenticated(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("JOULE_TICK_KEY", "k")
    client = TestClient(app)  # no lifespan: the MCP session manager may start only once per process
    assert client.post("/api/hook/gitlab", json={"object_kind": "issue"}).status_code == 403
    r = client.post("/api/hook/gitlab", json={"object_kind": "note"}, headers={"X-Gitlab-Token": "k"})
    assert r.status_code == 200 and r.json() == {"tick": False}
