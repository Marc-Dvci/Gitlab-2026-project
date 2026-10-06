"""Replayed grids: what the dispatcher would have known at any past moment.

Used by the experiments and by ``joule demo``. Information is released as it was live:
NESO forecasts at the lead time available then (never fresher), Spanish day-ahead prices
only after the ~13:00 CET daily publication. Emissions are scored on what the grid did.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .dispatch.receding import ForecastFn
from .signals.base import Point, Series, parse_time
from .signals.marginal import PriceMarginalModel
from .signals.snapshots import GB_LEADS, _gb_rows, es_prices, gb_intensity

UTC = timezone.utc


def gb_forecast_fn() -> ForecastFn:
    """NESO intensity as known at ``now``: actuals behind, the forecast at the right lead ahead."""
    table: dict[datetime, dict] = {}
    for r in _gb_rows():
        table[parse_time(r["window_start_utc"])] = r
    windows = sorted(table)
    actual = gb_intensity()

    def forecast(region: str, now: datetime) -> Series:
        pts = []
        for w in windows:
            if w < now - timedelta(hours=1) or w > now + timedelta(hours=48):
                continue
            row = table[w]
            if w < now:
                v = actual.value_at(w)
                if v is not None:
                    pts.append(Point(w, v))
                continue
            lead = (w - now).total_seconds() / 3600
            bucket = next((h for h in GB_LEADS if h >= lead), GB_LEADS[-1])
            v = row[f"forecast_lead_{bucket}h_gco2_kwh"] or row["forecast_latest_gco2_kwh"]
            if v:
                pts.append(Point(w, float(v)))
        return Series("GB", "carbon_intensity_average", "gCO2/kWh", timedelta(minutes=30), pts, "NESO forecast", kind="forecast")

    return forecast


def es_forecast_fn(series: Series) -> ForecastFn:
    """A Spanish day-ahead series as known at ``now``: tomorrow appears after ~13:00 Madrid time."""
    madrid = ZoneInfo("Europe/Madrid")

    def forecast(region: str, now: datetime) -> Series:
        local = now.astimezone(madrid)
        known_until_local = (local + timedelta(days=1 if local.hour >= 13 else 0)).replace(hour=0, minute=0) + timedelta(days=1)
        known_until = known_until_local.astimezone(UTC)
        return series.slice(now - timedelta(hours=1), known_until)

    return forecast


@dataclass
class ReplaySignals:
    """A ``SignalProvider`` for ``loop.tick`` over one replayed region."""

    region: str
    label: str
    actual: Series  # the decision signal as it happened (scoring)
    forecast: ForecastFn  # the decision signal as known at ``now`` (deciding)
    price_series: Series | None = None

    def decision_signal(self, region: str, now: datetime) -> Series:
        return self.forecast(region, now)

    def prices(self, zone: str, now: datetime) -> Series:
        if self.price_series is None:
            raise LookupError("no day-ahead prices in this replay")
        return es_forecast_fn(self.price_series)(self.region, now)

    def surplus(self, t: datetime) -> bool | None:
        """Price at or below zero (None when the replay has no prices)."""
        if self.price_series is None:
            return None
        v = self.price_series.value_at(t)
        return v is not None and v <= 0


def spain_2025(model: PriceMarginalModel | None = None) -> ReplaySignals:
    prices = es_prices()
    marginal = (model or PriceMarginalModel(fossil_margin_g=490.0, fossil_price=40.0)).series(prices)
    return ReplaySignals("europe-southwest1", "replay: OMIE day-ahead 2025 → marginal heuristic", marginal,
                         es_forecast_fn(marginal), prices)


def great_britain_2026() -> ReplaySignals:
    return ReplaySignals("europe-west2", "replay: NESO Sep–Oct 2026 (average intensity, proxy)", gb_intensity(),
                         gb_forecast_fn())
