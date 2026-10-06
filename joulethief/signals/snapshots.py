"""Loaders for the real-data snapshots committed in data/snapshots (see docs/DATA_SOURCES.md)."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from .base import Point, Series, parse_time

SNAPSHOTS = Path(__file__).resolve().parents[2] / "data" / "snapshots"
GB_INTENSITY = SNAPSHOTS / "gb_neso_intensity_2026-09_10.csv"
GB_MIX = SNAPSHOTS / "gb_neso_generation_mix_2026.csv"
ES_PRICES = SNAPSHOTS / "es_omie_dayahead_2025.csv"
GB_LEADS = (1, 6, 12, 24, 36, 47)
NESO = "NESO Carbon Intensity API via nmpowell/carbon-intensity-forecast-tracking (CC BY 4.0 / MIT)"


@lru_cache(maxsize=None)
def _gb_rows() -> tuple[dict, ...]:
    with GB_INTENSITY.open() as fh:
        return tuple(csv.DictReader(fh))


def gb_intensity(column: str = "actual_gco2_kwh") -> Series:
    """GB national average intensity, half-hourly, Sep–Oct 2026."""
    pts = [Point(parse_time(r["window_start_utc"]), float(r[column])) for r in _gb_rows() if r[column]]
    kind = "actual" if column.startswith("actual") else "forecast"
    return Series("GB", "carbon_intensity_average", "gCO2/kWh", timedelta(minutes=30), pts, NESO, kind=kind)


def gb_forecast_at_lead(hours: int) -> Series:
    if hours not in GB_LEADS:
        raise ValueError(f"lead must be one of {GB_LEADS}")
    return gb_intensity(f"forecast_lead_{hours}h_gco2_kwh")


def gb_forecast_errors() -> dict[int, list[tuple[datetime, float, float]]]:
    """Per lead time: (window, forecast, actual) triples — the raw material for conformal calibration."""
    out: dict[int, list[tuple[datetime, float, float]]] = {h: [] for h in GB_LEADS}
    for r in _gb_rows():
        if not r["actual_gco2_kwh"]:
            continue
        actual = float(r["actual_gco2_kwh"])
        t = parse_time(r["window_start_utc"])
        for h in GB_LEADS:
            v = r[f"forecast_lead_{h}h_gco2_kwh"]
            if v:
                out[h].append((t, float(v), actual))
    return out


def gb_generation_mix() -> dict[str, Series]:
    """Share (0–1) of each NESO fuel category, half-hourly, 2026."""
    with GB_MIX.open() as fh:
        rows = list(csv.DictReader(fh))
    fuels = [c.removesuffix("_permille") for c in rows[0] if c.endswith("_permille")]
    return {
        fuel: Series("GB", f"share_{fuel}", "fraction", timedelta(minutes=30),
                     [Point(parse_time(r["window_start_utc"]), float(r[f"{fuel}_permille"]) / 1000) for r in rows], NESO)
        for fuel in fuels
    }


def es_prices() -> Series:
    """Spanish day-ahead prices (OMIE), hourly, Jan–Sep 2025, converted from Madrid local time to UTC."""
    madrid = ZoneInfo("Europe/Madrid")
    seen: dict[datetime, float] = {}
    with ES_PRICES.open() as fh:
        for r in csv.DictReader(fh):
            local = datetime.fromisoformat(r["datetime_local_madrid"]).replace(tzinfo=madrid)
            t = local.astimezone(timezone.utc)
            seen.setdefault(t, float(r["price_eur_mwh"]))  # DST-normalised source: keep first on collisions
    return Series("ES", "day_ahead_price", "EUR / MWh", timedelta(hours=1), [Point(t, v) for t, v in seen.items()],
                  "OMIE via cesar-tatto/mibel-dayahead-dataset (MIT)")
