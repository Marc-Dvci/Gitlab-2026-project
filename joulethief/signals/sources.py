"""Adapters for zero-cost grid and weather data sources.

No-key sources (work out of the box):
    * Energy-Charts (Fraunhofer ISE) — European day-ahead prices and generation, CC BY 4.0.
    * NESO Carbon Intensity API — Great Britain intensity + 48 h forecast, CC BY 4.0.
    * Open-Meteo — weather forecasts (temperature drives cooling water use), CC BY 4.0.

Free with registration (optional, never required):
    * ENTSO-E Transparency Platform — day-ahead prices for every EU bidding zone.
    * WattTime — marginal emissions (MOER); the free plan exposes a relative index.

Every adapter takes an injectable ``fetch`` callable so tests run on recorded payloads.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .base import Point, Series, infer_resolution, parse_time, utc

USER_AGENT = "joulethief/0.1 (+https://gitlab.com)"
FetchText = Callable[[str, dict[str, str]], str]


def http_get_text(url: str, headers: dict[str, str] | None = None, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only, fixed hosts)
        return resp.read().decode("utf-8")


def _json(fetch: FetchText, url: str, headers: dict[str, str] | None = None) -> Any:
    return json.loads(fetch(url, headers or {}))


def _day(d: date | datetime) -> str:
    return (d.date() if isinstance(d, datetime) else d).isoformat()


class EnergyCharts:
    """https://api.energy-charts.info — no key, CC BY 4.0."""

    BASE = "https://api.energy-charts.info"

    def __init__(self, fetch: FetchText = http_get_text):
        self.fetch = fetch

    def day_ahead_price(self, bzn: str, start: date | datetime, end: date | datetime) -> Series:
        url = f"{self.BASE}/price?" + urllib.parse.urlencode({"bzn": bzn, "start": _day(start), "end": _day(end)})
        payload = _json(self.fetch, url)
        starts = [datetime.fromtimestamp(s, tz=timezone.utc) for s in payload["unix_seconds"]]
        pts = [Point(t, v) for t, v in zip(starts, payload["price"]) if v is not None]
        return Series(
            zone=bzn,
            metric="day_ahead_price",
            unit=payload.get("unit", "EUR / MWh"),
            resolution=infer_resolution(starts),
            points=pts,
            source="energy-charts.info (CC BY 4.0)",
            kind="forecast" if starts and starts[-1] > datetime.now(timezone.utc) else "actual",
        )

    def public_power(self, country: str, start: date | datetime, end: date | datetime) -> dict[str, Series]:
        """Net public generation by production type (MW)."""
        url = f"{self.BASE}/public_power?" + urllib.parse.urlencode(
            {"country": country.lower(), "start": _day(start), "end": _day(end)}
        )
        payload = _json(self.fetch, url)
        starts = [datetime.fromtimestamp(s, tz=timezone.utc) for s in payload["unix_seconds"]]
        res = infer_resolution(starts, timedelta(minutes=15))
        out: dict[str, Series] = {}
        for ptype in payload.get("production_types", []):
            pts = [Point(t, v) for t, v in zip(starts, ptype["data"]) if v is not None]
            out[ptype["name"]] = Series(country.upper(), "generation", "MW", res, pts, "energy-charts.info (CC BY 4.0)")
        return out


class Neso:
    """https://api.carbonintensity.org.uk — Great Britain, no key, CC BY 4.0."""

    BASE = "https://api.carbonintensity.org.uk"

    def __init__(self, fetch: FetchText = http_get_text):
        self.fetch = fetch

    @staticmethod
    def _fmt(t: datetime) -> str:
        return utc(t).strftime("%Y-%m-%dT%H:%MZ")

    def _series(self, rows: list[dict], prefer: str, zone: str) -> Series:
        pts = []
        for row in rows:
            intensity = row["intensity"]
            value = intensity.get(prefer)
            if value is None:
                value = intensity.get("forecast")
            if value is not None:
                pts.append(Point(parse_time(row["from"]), value))
        return Series(zone, "carbon_intensity_average", "gCO2/kWh", timedelta(minutes=30), pts, "NESO Carbon Intensity API (CC BY 4.0)",
                      kind="forecast" if prefer == "forecast" else "actual")

    def national_forecast_48h(self, start: datetime | None = None) -> Series:
        start = start or datetime.now(timezone.utc)
        payload = _json(self.fetch, f"{self.BASE}/intensity/{self._fmt(start)}/fw48h")
        return self._series(payload["data"], "forecast", "GB")

    def national_history(self, start: datetime, end: datetime) -> Series:
        payload = _json(self.fetch, f"{self.BASE}/intensity/{self._fmt(start)}/{self._fmt(end)}")
        return self._series(payload["data"], "actual", "GB")

    def regional_forecast_48h(self, region_id: int, start: datetime | None = None) -> Series:
        start = start or datetime.now(timezone.utc)
        payload = _json(self.fetch, f"{self.BASE}/regional/intensity/{self._fmt(start)}/fw48h/regionid/{region_id}")
        data = payload["data"]
        rows = data["data"] if isinstance(data, dict) else data[0]["data"]
        return self._series(rows, "forecast", f"GB-region-{region_id}")


class OpenMeteo:
    """https://open-meteo.com — no key for non-commercial use, CC BY 4.0."""

    BASE = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, fetch: FetchText = http_get_text):
        self.fetch = fetch

    def hourly(self, lat: float, lon: float, variables: tuple[str, ...] = ("temperature_2m", "wind_speed_100m"),
               days: int = 3, zone: str = "") -> dict[str, Series]:
        params = {"latitude": lat, "longitude": lon, "hourly": ",".join(variables), "forecast_days": days, "timezone": "UTC"}
        payload = _json(self.fetch, f"{self.BASE}?" + urllib.parse.urlencode(params))
        hourly = payload["hourly"]
        units = payload.get("hourly_units", {})
        starts = [parse_time(t) for t in hourly["time"]]
        return {
            var: Series(zone or f"{lat},{lon}", var, units.get(var, ""), timedelta(hours=1),
                        [Point(t, v) for t, v in zip(starts, hourly[var]) if v is not None],
                        "open-meteo.com (CC BY 4.0)", kind="forecast")
            for var in variables
        }


# ENTSO-E bidding zone EIC codes for the zones behind Google Cloud's European regions.
ENTSOE_EIC = {
    "FI": "10YFI-1--------U",
    "SE3": "10Y1001A1001A46L",
    "ES": "10YES-REE------0",
    "BE": "10YBE----------2",
    "NL": "10YNL----------L",
    "DE-LU": "10Y1001A1001A82H",
    "FR": "10YFR-RTE------C",
    "CH": "10YCH-SWISSGRIDZ",
    "IT-North": "10Y1001A1001A73I",
    "PL": "10YPL-AREA-----S",
}


class Entsoe:
    """ENTSO-E Transparency Platform (free security token on request)."""

    BASE = "https://web-api.tp.entsoe.eu/api"

    def __init__(self, token: str, fetch: FetchText = http_get_text):
        self.token = token
        self.fetch = fetch

    def day_ahead_price(self, zone: str, start: datetime, end: datetime) -> Series:
        eic = ENTSOE_EIC[zone]
        params = {
            "securityToken": self.token,
            "documentType": "A44",
            "in_Domain": eic,
            "out_Domain": eic,
            "periodStart": utc(start).strftime("%Y%m%d%H%M"),
            "periodEnd": utc(end).strftime("%Y%m%d%H%M"),
        }
        xml = self.fetch(f"{self.BASE}?" + urllib.parse.urlencode(params), {})
        return parse_entsoe_prices(xml, zone)


def parse_entsoe_prices(xml: str, zone: str) -> Series:
    """Parse an A44 publication document; forward-fills positions omitted by curve type A03."""
    root = ET.fromstring(xml)
    ns = {"ns": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    q = (lambda tag: f"ns:{tag}") if ns else (lambda tag: tag)
    points: dict[datetime, float] = {}
    resolution = timedelta(hours=1)
    for period in root.iter(f"{{{ns['ns']}}}Period" if ns else "Period"):
        start = parse_time(period.find(f"{q('timeInterval')}/{q('start')}", ns).text)
        end = parse_time(period.find(f"{q('timeInterval')}/{q('end')}", ns).text)
        res_text = period.find(q("resolution"), ns).text  # e.g. PT60M / PT15M
        resolution = timedelta(minutes=int(res_text.removeprefix("PT").removesuffix("M")))
        by_pos = {
            int(p.find(q("position"), ns).text): float(p.find(q("price.amount"), ns).text)
            for p in period.findall(q("Point"), ns)
        }
        n = int((end - start) / resolution)
        last = None
        for pos in range(1, n + 1):
            last = by_pos.get(pos, last)
            if last is not None:
                points[start + (pos - 1) * resolution] = last
    return Series(zone, "day_ahead_price", "EUR / MWh", resolution, [Point(t, v) for t, v in points.items()],
                  "ENTSO-E Transparency Platform")


LBS_PER_MWH_TO_G_PER_KWH = 0.45359237


class WattTime:
    """WattTime v3 (free account). Marginal operating emissions rate, or a 0–100 index on the free plan."""

    BASE = "https://api.watttime.org"

    def __init__(self, username: str, password: str, fetch: FetchText = http_get_text):
        self.username, self.password, self.fetch = username, password, fetch
        self._token: str | None = None

    def _auth(self) -> dict[str, str]:
        if self._token is None:
            basic = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            self._token = _json(self.fetch, f"{self.BASE}/login", {"Authorization": f"Basic {basic}"})["token"]
        return {"Authorization": f"Bearer {self._token}"}

    def forecast(self, region: str, signal_type: str = "co2_moer") -> Series:
        payload = _json(self.fetch, f"{self.BASE}/v3/forecast?" + urllib.parse.urlencode(
            {"region": region, "signal_type": signal_type}), self._auth())
        return parse_watttime(payload, region)

    def signal_index(self, region: str, signal_type: str = "co2_moer") -> Series:
        payload = _json(self.fetch, f"{self.BASE}/v3/signal-index?" + urllib.parse.urlencode(
            {"region": region, "signal_type": signal_type}), self._auth())
        return parse_watttime(payload, region)


def parse_watttime(payload: dict, region: str) -> Series:
    meta = payload.get("meta", {})
    units = meta.get("units", "")
    period = timedelta(seconds=meta.get("data_point_period_seconds", 300))
    scale, unit, metric = 1.0, units, "marginal_index"
    if units == "lbs_co2_per_mwh":
        scale, unit, metric = LBS_PER_MWH_TO_G_PER_KWH, "gCO2/kWh", "carbon_intensity_marginal"
    pts = [Point(parse_time(d["point_time"]), d["value"] * scale) for d in payload.get("data", [])]
    return Series(region, metric, unit, period, pts, "WattTime", kind="forecast")
