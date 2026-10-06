"""Live decision signals per Google Cloud region, from free sources, with honest fallbacks."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .signals.base import Point, Series, utc
from .signals.marginal import IPCC_AR5_LIFECYCLE_MEDIAN, PriceMarginalModel
from .signals.regions import REGIONS, google_region_carbon, gsf_region_metadata
from .signals.sources import EnergyCharts, FetchText, Neso, WattTime, http_get_text


@dataclass
class SignalRecord:
    source: str
    zone: str
    metric: str
    fetched_at: str
    sha256: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class LiveSignals:
    """Decision signal (gCO2/kWh of one more kWh) per region, plus provenance for receipts."""

    fetch: FetchText = http_get_text
    marginal_annual: dict[str, float] = field(default_factory=dict)  # from GSF metadata when available
    records: list[SignalRecord] = field(default_factory=list)
    _cache: dict[tuple[str, str], Series] = field(default_factory=dict)
    load_gsf: bool = True  # use the GSF/WattTime annual marginal as each zone's fossil margin
    _gsf_loaded: bool = False
    # WattTime MOER for regions without a price zone: JOULE_WATTTIME_USERNAME / _PASSWORD, and
    # JOULE_WATTTIME_REGIONS="us-west1=<WattTime region>,..." (codes from WattTime's region lookup).
    watttime: WattTime | None = None
    watttime_regions: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        user, password = os.environ.get("JOULE_WATTTIME_USERNAME"), os.environ.get("JOULE_WATTTIME_PASSWORD")
        if self.watttime is None and user and password:
            self.watttime = WattTime(user, password, self.fetch)
        if not self.watttime_regions:
            pairs = (item.split("=", 1) for item in os.environ.get("JOULE_WATTTIME_REGIONS", "").split(",") if "=" in item)
            self.watttime_regions = {k.strip(): v.strip() for k, v in pairs}

    def _record(self, series: Series) -> None:
        digest = hashlib.sha256(json.dumps([(p.start.isoformat(), p.value) for p in series], sort_keys=True).encode())
        self.records.append(SignalRecord(series.source, series.zone, series.metric,
                                         datetime.now(timezone.utc).isoformat(timespec="seconds"), digest.hexdigest()))

    def prices(self, zone: str, now: datetime) -> Series:
        key = (zone, now.strftime("%Y%m%d%H"))
        if key not in self._cache:
            s = EnergyCharts(self.fetch).day_ahead_price(zone, now - timedelta(days=1), now + timedelta(days=2))
            self._record(s)
            self._cache[key] = s
        return self._cache[key]

    def _ensure_marginal_annual(self) -> None:
        """Fill fossil-margin defaults from the GSF Real Time Cloud dataset once (best effort)."""
        if self._gsf_loaded or not self.load_gsf:
            return
        self._gsf_loaded = True
        try:
            for region, meta in gsf_region_metadata(self.fetch).items():
                if meta.get("marginal_annual") and region not in self.marginal_annual:
                    self.marginal_annual[region] = float(meta["marginal_annual"])
        except Exception:  # noqa: BLE001 — fall back to the IPCC gas CCGT median
            pass

    def decision_signal(self, region: str, now: datetime) -> Series:
        now = utc(now)
        self._ensure_marginal_annual()
        info = REGIONS.get(region)
        if info and info.intensity_source == "price" and info.price_zone:
            fossil = self.marginal_annual.get(region, IPCC_AR5_LIFECYCLE_MEDIAN["gas_ccgt"])
            return PriceMarginalModel(fossil_margin_g=fossil).series(self.prices(info.price_zone, now))
        if info and info.intensity_source == "neso":
            s = Neso(self.fetch).national_forecast_48h(now)
            self._record(s)
            return s  # average intensity — flagged as a proxy in the ledger
        code = self.watttime_regions.get(region)
        if self.watttime is not None and code:
            try:
                s = self.watttime.forecast(code)
                if s.metric == "carbon_intensity_marginal" and len(s):  # gCO2/kWh, not the free plan's 0–100 index
                    self._record(s)
                    return s
            except Exception:  # noqa: BLE001 — not on this plan or region: the annual figure below
                pass
        return self.flat(region, now)

    def flat(self, region: str, now: datetime, hours: int = 72) -> Series:
        """No live signal: the region's annual figure (marginal if known, else Google's location-based average)."""
        value = self.marginal_annual.get(region) or google_region_carbon()[region].grid_intensity_avg
        start = utc(now).replace(minute=0, second=0, microsecond=0)
        pts = [Point(start + timedelta(hours=h), value) for h in range(hours)]
        return Series(region, "carbon_intensity_annual", "gCO2/kWh", timedelta(hours=1), pts,
                      "annual regional figure (no live signal)", kind="derived")
