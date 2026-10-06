import json
from datetime import datetime, timedelta, timezone

import pytest

from joulethief.carbon.ledger import Ledger, LedgerEntry
from joulethief.carbon.llm import AgentCall, agent_footprint, calls_from_trace
from joulethief.carbon.power import CloudPowerModel
from joulethief.carbon.sci import sci
from joulethief.carbon.water import EVAPORATIVE, SEAWATER, water_litres
from joulethief.estimate import Estimate
from joulethief.signals.base import Point, Series
from joulethief.signals.marginal import NESO_FUEL_FACTORS, PriceMarginalModel, intensity_from_mix, surplus_windows
from joulethief.signals.regions import google_region_carbon
from joulethief.signals.snapshots import es_prices, gb_forecast_errors, gb_generation_mix, gb_intensity
from joulethief.signals.sources import EnergyCharts, Neso, OpenMeteo, parse_entsoe_prices, parse_watttime

T0 = datetime(2026, 10, 6, tzinfo=timezone.utc)


def hourly(values, zone="FI", metric="day_ahead_price"):
    return Series(zone, metric, "EUR / MWh", timedelta(hours=1),
                  [Point(T0 + timedelta(hours=i), v) for i, v in enumerate(values)], "test")


def test_estimate_arithmetic():
    a = Estimate(1, 2, 3)
    b = Estimate.exact(10)
    assert (a + b).to_dict() == {"low": 11, "likely": 12, "high": 13}
    assert (a * 2).high == 6
    assert (a * Estimate(1, 2, 4)).to_dict() == {"low": 1, "likely": 4, "high": 12}
    assert (Estimate.exact(10) - a).to_dict() == {"low": 7, "likely": 8, "high": 9}
    with pytest.raises(ValueError):
        Estimate(3, 2, 1)


def test_series_lookup_and_resample():
    s = Series("GB", "x", "u", timedelta(minutes=30), [Point(T0 + timedelta(minutes=30 * i), i) for i in range(4)], "t")
    assert s.value_at(T0 + timedelta(minutes=45)) == 1
    assert s.value_at(T0 - timedelta(minutes=1)) is None
    h = s.resample(timedelta(hours=1))
    assert h.values() == [0.5, 2.5]
    assert h.resample(timedelta(minutes=30)).values() == [0.5, 0.5, 2.5, 2.5]
    assert s.on_grid(T0, 2, timedelta(hours=1)) == [1, 3]


def test_energy_charts_price_adapter():
    payload = {"unix_seconds": [int(T0.timestamp()) + 900 * i for i in range(4)], "price": [10.0, -2.5, None, 3.0],
               "unit": "EUR / MWh", "deprecated": False}
    calls = []
    ec = EnergyCharts(fetch=lambda url, h: calls.append(url) or json.dumps(payload))
    s = ec.day_ahead_price("FI", T0.date(), T0.date())
    assert "bzn=FI" in calls[0] and s.resolution == timedelta(minutes=15)
    assert s.values() == [10.0, -2.5, 3.0]


def test_neso_adapter_prefers_actual_then_forecast():
    payload = {"data": [
        {"from": "2026-10-06T00:00Z", "to": "2026-10-06T00:30Z", "intensity": {"forecast": 100, "actual": 90, "index": "low"}},
        {"from": "2026-10-06T00:30Z", "to": "2026-10-06T01:00Z", "intensity": {"forecast": 80, "actual": None, "index": "low"}},
    ]}
    neso = Neso(fetch=lambda url, h: json.dumps(payload))
    hist = neso.national_history(T0, T0 + timedelta(hours=1))
    assert hist.values() == [90, 80]
    assert neso.national_forecast_48h(T0).values() == [100, 80]


def test_open_meteo_adapter():
    payload = {"hourly": {"time": ["2026-10-06T00:00", "2026-10-06T01:00"], "temperature_2m": [7.5, 7.1],
                          "wind_speed_100m": [30.2, 33.0]}, "hourly_units": {"temperature_2m": "°C"}}
    om = OpenMeteo(fetch=lambda url, h: json.dumps(payload))
    out = om.hourly(60.57, 27.19)
    assert out["temperature_2m"].values() == [7.5, 7.1]
    assert out["temperature_2m"].unit == "°C"


def test_entsoe_parser_forward_fills_a03_curves():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
 <TimeSeries><Period>
  <timeInterval><start>2026-10-05T22:00Z</start><end>2026-10-06T02:00Z</end></timeInterval>
  <resolution>PT60M</resolution>
  <Point><position>1</position><price.amount>12.5</price.amount></Point>
  <Point><position>3</position><price.amount>-1.0</price.amount></Point>
 </Period></TimeSeries>
</Publication_MarketDocument>"""
    s = parse_entsoe_prices(xml, "FI")
    assert s.values() == [12.5, 12.5, -1.0, -1.0]


def test_watttime_units_converted():
    payload = {"meta": {"units": "lbs_co2_per_mwh", "data_point_period_seconds": 300},
               "data": [{"point_time": "2026-10-06T00:00:00+00:00", "value": 1000}]}
    s = parse_watttime(payload, "CAISO_NORTH")
    assert s.values()[0] == pytest.approx(453.59, rel=1e-3)
    assert s.metric == "carbon_intensity_marginal"


def test_price_marginal_model_and_surplus_windows():
    m = PriceMarginalModel(fossil_margin_g=785, surplus_g=11, fossil_price=40)
    assert m.g_per_kwh(-5) == 11
    assert m.g_per_kwh(80) == 785
    assert m.g_per_kwh(20) == pytest.approx(398)
    prices = hourly([30, -1, -3, 5, 0, 50])
    wins = surplus_windows(prices)
    assert [(w[0].hour, w[1].hour, w[2]) for w in wins] == [(1, 3, -3), (4, 5, 0)]


def test_intensity_from_mix_rejects_unknown_fuels():
    assert intensity_from_mix({"wind": 0.5, "gas": 0.5}, NESO_FUEL_FACTORS) == pytest.approx((11 + 490) / 2)
    with pytest.raises(KeyError):
        intensity_from_mix({"unobtainium": 1.0}, NESO_FUEL_FACTORS)


def test_real_snapshots_load():
    gb = gb_intensity()
    assert len(gb) > 1500 and 10 < gb.mean() < 300
    errs = gb_forecast_errors()
    assert len(errs[24]) > 1000
    mix = gb_generation_mix()
    assert {"wind", "gas", "solar"} <= set(mix)
    es = es_prices()
    assert len(es) > 6000
    assert sum(1 for p in es if p.value <= 0) > 500  # real 2025 solar surplus hours
    regions = google_region_carbon()
    assert regions["us-east1"].grid_intensity_avg > 500 > regions["europe-north1"].grid_intensity_avg


def test_power_model_and_sci():
    pm = CloudPowerModel()
    e = pm.energy_kwh(vcpus=2, hours=1, utilisation=0.5, memory_gb=8)
    assert 0.002 < e.likely < 0.02
    assert e.low <= e.likely <= e.high
    emb = pm.embodied_g("e2-standard-2", vcpus=2, hours=1)
    assert 1 < emb < 50
    r = sci(e, 100.0, emb, functional_units=1000, functional_unit="request")
    assert r.per_unit_g.likely == pytest.approx((e.likely * 100 + emb) / 1000)


def test_agent_footprint_with_ecologits():
    fp = agent_footprint([AgentCall("anthropic", "claude-sonnet-4-6", 20000, 800, 20.0),
                          AgentCall("anthropic", "claude-haiku-4-5-20251001", 5000, 200, 3.0)], "FIN")
    assert fp.calls == 2 and fp.input_tokens == 25000
    assert fp.gwp_g.low > 0 and fp.water_l.high > 0
    assert fp.sci_for_ai(1)["g_per_unit"]["likely"] == pytest.approx(fp.gwp_g.likely, rel=1e-4)


def test_trace_reconstruction_counts_growing_context():
    trace = "\n".join(json.dumps(x) for x in [
        {"message_type": "human", "content": "x" * 400},
        {"message_type": "ai", "content": "y" * 40},
        {"message_type": "tool", "content": "z" * 400},
        {"message_type": "ai", "content": "w" * 40},
    ])
    calls = calls_from_trace(trace, "anthropic", "claude-sonnet-4-6")
    assert [c.input_tokens for c in calls] == [100, 210]
    assert [c.output_tokens for c in calls] == [10, 10]


def test_water_seawater_vs_evaporative():
    e = Estimate.exact(1.0)
    pue = Estimate.exact(1.1)
    hot = water_litres(e, EVAPORATIVE, 30, pue, 0.0)
    cold = water_litres(e, EVAPORATIVE, 0, pue, 0.0)
    sea = water_litres(e, SEAWATER, 30, pue, 0.0)
    assert hot.likely > cold.likely > sea.likely


def test_ledger_roundtrip_and_avoided(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path)
    ledger.record(LedgerEntry("issue#1", "agent_session", "europe-north1", T0, T0 + timedelta(minutes=5),
                              Estimate.exact(0.01), Estimate.exact(0.4), Estimate.exact(0.2),
                              baseline_consequential_g=Estimate.exact(5.0), surplus_energy_kwh=0.01))
    again = Ledger(path)
    s = again.summary()
    assert s["entries"] == 1
    assert s["avoided_consequential_g"]["likely"] == pytest.approx(4.8)
    assert s["surplus_energy_share"] == pytest.approx(1.0)
