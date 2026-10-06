"""Google Cloud regions: where the electricity comes from and how the building is cooled."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .sources import FetchText, http_get_text

REPO_ROOT = Path(__file__).resolve().parents[2]
GOOGLE_REGION_CSV = REPO_ROOT / "data" / "reference" / "gcp_region_carbon_2024.csv"
# Green Software Foundation "Real Time Cloud" region metadata. Fetched at runtime (not redistributed):
# it adds PUE and an annual *marginal* grid intensity per region (WattTime-derived).
GSF_REGION_METADATA_URL = (
    "https://raw.githubusercontent.com/Green-Software-Foundation/real-time-cloud/main/Cloud_Region_Metadata_estimate.csv"
)


@dataclass(frozen=True)
class Region:
    name: str
    city: str
    lat: float
    lon: float
    price_zone: str | None  # bidding zone for day-ahead prices (Energy-Charts / ENTSO-E code)
    intensity_source: str  # "price" (EU day-ahead), "neso" (GB), "watttime" (US/CA)
    cooling: str = "evaporative"  # "seawater" | "evaporative" | "air"
    notes: str = ""


# Approximate data-centre coordinates (used for weather → cooling water models).
REGIONS: dict[str, Region] = {r.name: r for r in [
    Region("europe-north1", "Hamina", 60.57, 27.19, "FI", "price", "seawater",
           "Cooled with Baltic seawater; Finland had 724 negative-price hours in 2024 and 447 in 2025."),
    Region("europe-north2", "Stockholm", 59.33, 18.07, "SE3", "price"),
    Region("europe-southwest1", "Madrid", 40.42, -3.70, "ES", "price", notes="Solar surplus: zero/negative midday prices."),
    Region("europe-west1", "St. Ghislain", 50.47, 3.87, "BE", "price"),
    Region("europe-west4", "Eemshaven", 53.44, 6.83, "NL", "price"),
    Region("europe-west3", "Frankfurt", 50.11, 8.68, "DE-LU", "price"),
    Region("europe-west9", "Paris", 48.86, 2.35, "FR", "price"),
    Region("europe-west6", "Zürich", 47.37, 8.54, "CH", "price"),
    Region("europe-west2", "London", 51.51, -0.13, None, "neso",
           notes="GB curtailment is mostly in Scotland behind a transmission constraint; London load does not absorb it."),
    Region("us-east1", "Moncks Corner", 33.06, -80.04, None, "watttime",
           notes="Default region of GitLab.com hosted Linux runners."),
    Region("us-west1", "The Dalles", 45.60, -121.18, None, "watttime", notes="Always-free e2-micro eligible."),
    Region("us-central1", "Council Bluffs", 41.26, -95.86, None, "watttime", notes="Always-free e2-micro eligible."),
    Region("northamerica-northeast1", "Montréal", 45.50, -73.57, None, "watttime",
           notes="Hydro grid: ~0 g/kWh on average, but marginal demand displaces exports that offset fossil generation."),
]}


@dataclass(frozen=True)
class RegionCarbon:
    region: str
    google_cfe: float  # hourly-matched carbon-free energy share reported by Google
    grid_intensity_avg: float  # location-based gCO2e/kWh (Google, 2024)
    pue: float | None = None
    grid_intensity_marginal_annual: float | None = None  # GSF / WattTime, consequential


@lru_cache(maxsize=1)
def google_region_carbon(path: Path = GOOGLE_REGION_CSV) -> dict[str, RegionCarbon]:
    out = {}
    with path.open() as fh:
        for row in csv.DictReader(fh):
            out[row["Google Cloud Region"]] = RegionCarbon(
                region=row["Google Cloud Region"],
                google_cfe=float(row["Google CFE"]),
                grid_intensity_avg=float(row["Grid carbon intensity (gCO2eq / kWh)"]),
            )
    return out


def gsf_region_metadata(fetch: FetchText = http_get_text, provider: str = "Google Cloud") -> dict[str, dict[str, float | None]]:
    """Latest-year GSF metadata per region: PUE and annual marginal intensity (may be missing)."""
    text = fetch(GSF_REGION_METADATA_URL, {})
    latest: dict[str, tuple[int, dict]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("cloud-provider") != provider:
            continue
        year = int(row["year"])
        region = row["cloud-region"]
        if region not in latest or year > latest[region][0]:
            latest[region] = (year, row)

    def num(v: str | None) -> float | None:
        try:
            return float(v) if v not in (None, "") else None
        except ValueError:
            return None

    return {
        region: {
            "year": year,
            "pue": num(row.get("power-usage-effectiveness")),
            "wue": num(row.get("water-usage-effectiveness")),
            "cfe_hourly": num(row.get("provider-cfe-hourly")),
            "marginal_annual": num(row.get("grid-carbon-intensity-marginal-consumption-annual")),
            "average_hourly": num(row.get("provider-carbon-intensity-average-consumption-hourly")),
        }
        for region, (year, row) in latest.items()
    }


def region_carbon(name: str, gsf: dict[str, dict] | None = None) -> RegionCarbon:
    base = google_region_carbon()[name]
    extra = (gsf or {}).get(name, {})
    return RegionCarbon(
        region=name,
        google_cfe=base.google_cfe,
        grid_intensity_avg=base.grid_intensity_avg,
        pue=extra.get("pue"),
        grid_intensity_marginal_annual=extra.get("marginal_annual"),
    )
