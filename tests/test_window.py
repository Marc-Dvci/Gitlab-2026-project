"""The grid-window CI/CD component: plan a delayed child pipeline for deferrable jobs."""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from joulethief.signals.base import Point, Series
from joulethief.window import WAIT_JOB, child_pipeline, choose, parse_duration

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 6, 18, tzinfo=timezone.utc)
SLOT = timedelta(minutes=30)
JOBS = """stages: [test]
matrix:
  stage: test
  script: [pytest -q]
"""


def signal(values):
    return Series("FI", "m", "gCO2/kWh", SLOT, [Point(T0 + i * SLOT, v) for i, v in enumerate(values)], "test")


def test_parse_duration():
    assert parse_duration("45m") == timedelta(minutes=45)
    assert parse_duration("1h30m") == timedelta(minutes=90)
    assert parse_duration("1d") == timedelta(days=1) and parse_duration("20") == timedelta(minutes=20)
    with pytest.raises(ValueError):
        parse_duration("soon")


def test_choose_waits_for_the_clean_window_inside_the_deadline():
    values = [500] * 8 + [20] * 4 + [500] * 8 + [5] * 20  # cleaner still, but only after the deadline
    w = choose(signal(values), "europe-north1", T0, timedelta(minutes=45), timedelta(hours=8))
    assert w.start == T0 + 8 * SLOT and w.wait == timedelta(hours=4)
    assert w.start_g_per_kwh == pytest.approx(20) and w.saving == pytest.approx(0.96)


def test_choose_runs_now_without_slack_or_without_a_forecast():
    assert choose(signal([500] + [20] * 10), "r", T0, timedelta(hours=2), timedelta(hours=2)).wait == timedelta()
    flat = choose(signal([300] * 48), "r", T0, timedelta(minutes=30), timedelta(hours=12))
    assert flat.wait == timedelta() and flat.saving == 0


def test_child_pipeline_holds_the_jobs_behind_a_delayed_pre_job():
    w = choose(signal([500] * 8 + [20] * 4 + [500] * 30), "europe-north1", T0, timedelta(minutes=45), timedelta(hours=8))
    child = yaml.safe_load(child_pipeline(JOBS, w, "Hamina (`europe-north1`): it's windy"))
    wait = child[WAIT_JOB]
    assert wait["stage"] == ".pre" and wait["when"] == "delayed" and wait["start_in"] == "240 minutes"
    assert child["matrix"]["script"] == ["pytest -q"]
    assert "20 gCO2/kWh" in wait["script"][0]
    now = choose(signal([20] * 48), "r", T0, timedelta(minutes=30), timedelta(hours=8))
    assert "when" not in yaml.safe_load(child_pipeline(JOBS, now, "r"))[WAIT_JOB]
    with pytest.raises(ValueError):
        child_pipeline(JOBS + f"{WAIT_JOB}:\n  script: [true]\n", w, "r")


def test_component_template_is_well_formed():
    spec, jobs = list(yaml.safe_load_all((ROOT / "templates" / "grid-window" / "template.yml").read_text()))
    inputs = spec["spec"]["inputs"]
    assert {"jobs", "region"} <= {k for k, v in inputs.items() if "default" not in v}  # required: no silent defaults
    used = set(re.findall(r"\$\[\[\s*inputs\.(\w+)\s*\]\]", yaml.safe_dump(jobs)))
    assert used <= set(inputs) and used == set(inputs)
    plan, run = jobs["grid-window:plan"], jobs["grid-window:run"]
    assert "joulethief.cli window" in plan["script"][0] and "grid-window-child.yml" in plan["artifacts"]["paths"]
    assert run["trigger"]["include"][0] == {"artifact": "grid-window-child.yml", "job": "grid-window:plan"}
    assert run["trigger"]["strategy"] == "depend" and run["needs"] == ["grid-window:plan"]
