from datetime import datetime, timedelta, timezone

import pytest

from joulethief.dispatch.jobs import PRIORITY_SLA, Job, job_from_issue, priority_from_labels
from joulethief.dispatch.optimizer import plan
from joulethief.dispatch.receding import OfficeHours, simulate, synthetic_backlog
from joulethief.dispatch.uncertainty import ConformalIntervals, chronological_split, conformal_quantile
from joulethief.dispatch.vcc import virtual_capacity_curve
from joulethief.signals.base import Point, Series
from joulethief.signals.snapshots import gb_forecast_errors, gb_intensity

T0 = datetime(2026, 10, 6, tzinfo=timezone.utc)
SLOT = timedelta(minutes=30)


def signal(values, zone="r1"):
    return Series(zone, "carbon_intensity_marginal_estimate", "gCO2/kWh", SLOT,
                  [Point(T0 + i * SLOT, v) for i, v in enumerate(values)], "test")


def job(jid, hours=1.0, deadline_h=24, power=1.0, regions=("r1",), priority="normal", release=T0):
    return Job(jid, timedelta(hours=hours), power, release, release + timedelta(hours=deadline_h), regions, priority=priority)


def test_labels_map_to_service_levels():
    assert priority_from_labels(["priority::low"]) == "low"
    assert priority_from_labels(["surge::now", "priority::low"]) == "critical"
    assert priority_from_labels([]) == "normal"
    j = job_from_issue(42, ["priority::high"], T0, timedelta(minutes=30), 0.3)
    assert j.id == "#42" and j.deadline == T0 + PRIORITY_SLA["high"] + timedelta(minutes=30)


@pytest.mark.parametrize("use_solver", [True, False])
def test_plan_moves_work_into_the_clean_valley(use_solver):
    values = [500] * 10 + [20] * 4 + [500] * 10
    p = plan([job("a")], {"r1": signal(values)}, T0, horizon=timedelta(hours=12), use_solver=use_solver)
    a = p.assignment("a")
    assert a.start == T0 + 10 * SLOT
    assert a.expected_g == pytest.approx(20.0)
    assert p.baseline_g == pytest.approx(500.0)
    assert p.saving_fraction > 0.9


def test_partial_slot_jobs_are_costed_on_their_energy():
    # 40 minutes spans two 30-minute slots; the plan must cost 40 minutes of energy, not an hour.
    j = Job("a", timedelta(minutes=40), 0.3, T0, T0 + timedelta(hours=12), ("r1",))
    p = plan([j], {"r1": signal([500] * 4 + [20] * 4 + [500] * 16)}, T0, horizon=timedelta(hours=12))
    a = p.assignment("a")
    assert a.expected_g == pytest.approx(j.energy_kwh * 20, rel=1e-3)
    assert p.baseline_g == pytest.approx(j.energy_kwh * 500, rel=1e-3)


def test_slot_as_clean_as_typical_is_not_deferred():
    # Spanish spring: most known hours sit on the surplus floor, so the median *is* the floor.
    # A slot that matches it must run, not wait for a later plan that cannot do better.
    p = plan([job("a", deadline_h=72)], {"r1": signal([30] * 2 + [11] * 28 + [490] * 10)}, T0, horizon=timedelta(hours=20))
    assert p.deferred == [] and p.assignment("a").start == T0 + 2 * SLOT


def test_plan_respects_deadline_even_when_dirty():
    values = [500] * 4 + [10] * 20
    p = plan([job("a", deadline_h=2)], {"r1": signal(values)}, T0, horizon=timedelta(hours=12))
    a = p.assignment("a")
    assert a.start + timedelta(hours=1) <= T0 + timedelta(hours=2)
    assert not a.late


def test_plan_chooses_cleanest_region():
    p = plan([job("a", regions=("dirty", "clean"))],
             {"dirty": signal([400] * 24, "dirty"), "clean": signal([50] * 24, "clean")}, T0, horizon=timedelta(hours=12))
    assert p.assignment("a").region == "clean"


def test_capacity_prevents_herding():
    values = [500] * 6 + [10] * 2 + [500] * 40
    jobs = [job(f"j{i}", deadline_h=12) for i in range(3)]
    p = plan(jobs, {"r1": signal(values)}, T0, horizon=timedelta(hours=24), capacity=1)
    assert not p.deferred
    starts = sorted(a.start for a in p.assignments)
    assert len(set(starts)) == 3  # one job in the valley, the others spread out instead of piling in
    assert p.assignment("j0").start == T0 + 6 * SLOT or T0 + 6 * SLOT in starts


def test_defer_when_horizon_has_no_clean_slot():
    values = [500] * 24
    p = plan([job("a", deadline_h=72)], {"r1": signal(values)}, T0, horizon=timedelta(hours=12),
             defer_value={"r1": 100.0})
    assert p.deferred == ["a"] and not p.assignments


def test_office_hours_mask_is_respected():
    office = OfficeHours(tz="UTC", start_hour=9, end_hour=18)
    values = [5] * 18 + [400] * 30  # cleanest at night
    p = plan([job("a", deadline_h=20)], {"r1": signal(values)}, T0, horizon=timedelta(hours=24),
             allowed_start=office, mask_is_hard=True)
    assert 9 <= p.assignment("a").start.hour < 18


def test_vcc_preserves_demand_and_prefers_clean_slots():
    cap = virtual_capacity_curve([300, 100, 50, 400, None], demand_slot_units=10, floor=1, ceiling=4, headroom=1.0)
    assert sum(cap) >= 10
    assert cap == [1, 3, 4, 1, 1]  # cleanest slot filled first, unknown slot last


def test_conformal_quantile_and_real_coverage():
    assert conformal_quantile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.1) == 10
    calib, test = chronological_split(gb_forecast_errors(), 0.6)
    ci = ConformalIntervals.fit(calib, alpha=0.1)
    cov = ci.coverage(test)
    assert cov[1] > 0.85  # near-nominal at short leads on held-out real NESO data
    lo, hi = ci.interval(150, lead_hours=3)
    assert lo < 150 < hi and ci.bucket(3) == 6


def test_receding_horizon_beats_run_now_on_real_gb_data():
    start = datetime(2026, 9, 7, tzinfo=timezone.utc)
    end = start + timedelta(days=6)
    gb = gb_intensity()
    jobs = synthetic_backlog(start, 3, per_weekday=6, region="gb")

    def forecast(region, now):  # oracle forecast keeps this test fast and deterministic
        return gb.slice(now - timedelta(hours=1), now + timedelta(hours=48))

    base = simulate(jobs, {"gb": gb}, forecast, "run_now", start, end)
    smart = simulate(jobs, {"gb": gb}, forecast, "hands_off", start, end)
    assert smart.realized_g < base.realized_g
    assert smart.late_jobs == 0
