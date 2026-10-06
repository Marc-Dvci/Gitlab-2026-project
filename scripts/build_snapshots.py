"""Rebuild the real-data snapshots committed under data/snapshots and data/reference.

Every file is derived from public, zero-cost sources. Run:

    python scripts/build_snapshots.py --cache .cache/raw

Sources and licences are listed in docs/DATA_SOURCES.md.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RAW = "https://raw.githubusercontent.com"
SOURCES = {
    # NESO Carbon Intensity API history, scraped twice an hour by nmpowell (MIT).
    # Underlying data: NESO, CC BY 4.0.
    "neso_2026-09": f"{RAW}/nmpowell/carbon-intensity-forecast-tracking/main/data/db/2026/national_2026-09.sqlite",
    "neso_2026-10": f"{RAW}/nmpowell/carbon-intensity-forecast-tracking/main/data/db/2026/national_2026-10.sqlite",
    "neso_generation_2026": f"{RAW}/nmpowell/carbon-intensity-forecast-tracking/main/data/db/2026/generation_2026.sqlite",
    # Spanish day-ahead prices (OMIE) + ENTSO-E forecasts, packaged by cesar-tatto (MIT).
    "es_omie": f"{RAW}/cesar-tatto/mibel-dayahead-dataset/main/dataset/final/ES.csv",
    # Google Cloud region carbon data (Apache-2.0).
    "gcp_regions_2024": f"{RAW}/GoogleCloudPlatform/region-carbon-info/main/data/yearly/2024.csv",
    # Cloud Carbon Footprint coefficients (Apache-2.0).
    "ccf_gcp_use": f"{RAW}/cloud-carbon-footprint/cloud-carbon-coefficients/main/output/coefficients-gcp-use.csv",
    "ccf_gcp_embodied": f"{RAW}/cloud-carbon-footprint/cloud-carbon-coefficients/main/output/coefficients-gcp-embodied.csv",
}

LEADS_HOURS = (1, 6, 12, 24, 36, 47)


def fetch(name: str, cache: Path) -> Path:
    url = SOURCES[name]
    target = cache / (name + Path(url).suffix)
    if not target.exists():
        cache.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}", file=sys.stderr)
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (fixed https URLs)
            target.write_bytes(resp.read())
    return target


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_gb_intensity(cache: Path, out: Path) -> int:
    """One row per half-hour window: final actual, latest forecast and forecasts at fixed leads."""
    rows: dict[int, list[tuple[int, int | None, int | None]]] = defaultdict(list)
    for name in ("neso_2026-09", "neso_2026-10"):
        con = sqlite3.connect(fetch(name, cache))
        for window, capture, forecast, actual in con.execute(
            "SELECT window_utc, capture_utc, forecast, actual FROM national_intensity"
        ):
            rows[window].append((capture, forecast, actual))
        con.close()

    header = ["window_start_utc", "actual_gco2_kwh", "forecast_latest_gco2_kwh"] + [
        f"forecast_lead_{h}h_gco2_kwh" for h in LEADS_HOURS
    ]
    written = 0
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for window in sorted(rows):
            caps = sorted(rows[window])
            actuals = [a for _, _, a in caps if a is not None]
            forecasts = [(c, f) for c, f, _ in caps if f is not None]
            if not forecasts:
                continue
            latest = forecasts[-1][1]
            leads = []
            for h in LEADS_HOURS:
                cutoff = window - h * 3600
                eligible = [f for c, f in forecasts if c <= cutoff]
                leads.append(eligible[-1] if eligible else "")
            writer.writerow([iso(window), actuals[-1] if actuals else "", latest, *leads])
            written += 1
    return written


def build_gb_generation(cache: Path, out: Path) -> int:
    con = sqlite3.connect(fetch("neso_generation_2026", cache))
    fuels = ["biomass", "coal", "gas", "hydro", "imports", "nuclear", "other", "solar", "wind"]
    latest: dict[int, tuple] = {}
    for row in con.execute(f"SELECT window_utc, capture_utc, {', '.join(fuels)} FROM generation_mix ORDER BY capture_utc"):
        latest[row[0]] = row[2:]
    con.close()
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        # NESO reports the mix in percent x10 (per-mille) in this archive; we keep the raw integers.
        writer.writerow(["window_start_utc"] + [f"{f}_permille" for f in fuels])
        for window in sorted(latest):
            writer.writerow([iso(window), *latest[window]])
    return len(latest)


def build_es_prices(cache: Path, out: Path, start: str = "2025-01-01") -> int:
    src = fetch("es_omie", cache)
    written = 0
    with src.open() as fin, out.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.writer(fout)
        writer.writerow(["datetime_local_madrid", "price_eur_mwh", "load_forecast_mw", "solar_forecast_mw", "wind_onshore_forecast_mw"])
        for r in reader:
            if r["datetime"] >= start:
                writer.writerow([r["datetime"], r["price_es"], r["load_forecast_mw"], r["solar_forecast_mw"], r["wind_onshore_forecast_mw"]])
                written += 1
    return written


def copy_reference(cache: Path, ref_dir: Path) -> None:
    for name, filename in (
        ("gcp_regions_2024", "gcp_region_carbon_2024.csv"),
        ("ccf_gcp_use", "ccf_coefficients_gcp_use.csv"),
        ("ccf_gcp_embodied", "ccf_coefficients_gcp_embodied.csv"),
    ):
        (ref_dir / filename).write_bytes(fetch(name, cache).read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path(".cache/raw"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    snaps = args.root / "data" / "snapshots"
    ref = args.root / "data" / "reference"
    snaps.mkdir(parents=True, exist_ok=True)
    ref.mkdir(parents=True, exist_ok=True)
    n = build_gb_intensity(args.cache, snaps / "gb_neso_intensity_2026-09_10.csv")
    print(f"gb intensity windows: {n}")
    n = build_gb_generation(args.cache, snaps / "gb_neso_generation_mix_2026.csv")
    print(f"gb generation windows: {n}")
    n = build_es_prices(args.cache, snaps / "es_omie_dayahead_2025.csv")
    print(f"es price hours: {n}")
    copy_reference(args.cache, ref)
    print("reference files copied")


if __name__ == "__main__":
    main()
