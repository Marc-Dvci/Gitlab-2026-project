# Data sources — all zero-cost

## Committed snapshots (real data, reproducible with `python scripts/build_snapshots.py`)

| File | What | Source | Licence |
|---|---|---|---|
| `data/snapshots/gb_neso_intensity_2026-09_10.csv` | GB national carbon intensity, half-hourly, 1 Sep → 7 Oct 2026: final actual, latest forecast, and the forecast available 1/6/12/24/36/47 h before each window | NESO Carbon Intensity API, archived twice an hour by [nmpowell/carbon-intensity-forecast-tracking](https://github.com/nmpowell/carbon-intensity-forecast-tracking) | NESO data CC BY 4.0; archive MIT |
| `data/snapshots/gb_neso_generation_mix_2026.csv` | GB generation mix (per-mille by fuel), half-hourly, Jul → Oct 2026 | same | same |
| `data/snapshots/es_omie_dayahead_2025.csv` | Spanish day-ahead prices (EUR/MWh) with load, solar and wind forecasts, hourly, Jan → Sep 2025 (760 hours ≤ 0 €/MWh) | OMIE + ENTSO-E via [cesar-tatto/mibel-dayahead-dataset](https://github.com/cesar-tatto/mibel-dayahead-dataset) | MIT |
| `data/reference/gcp_region_carbon_2024.csv` | Google CFE % and location-based grid intensity per Google Cloud region (2024) | [GoogleCloudPlatform/region-carbon-info](https://github.com/GoogleCloudPlatform/region-carbon-info) | Apache-2.0 |
| `data/reference/ccf_coefficients_gcp_use.csv`, `..._embodied.csv` | CPU min/max watts per vCPU by microarchitecture; embodied kgCO₂e per machine type | [Cloud Carbon Footprint coefficients](https://github.com/cloud-carbon-footprint/cloud-carbon-coefficients) | Apache-2.0 |

## Fetched at run time (not redistributed)

| Source | Used for | Access | Cost |
|---|---|---|---|
| [Energy-Charts API](https://api.energy-charts.info) (Fraunhofer ISE) | Day-ahead prices per bidding zone (FI, SE3, ES, NL, BE, DE-LU, FR…), public generation | No key | $0, CC BY 4.0 |
| [NESO Carbon Intensity API](https://carbonintensity.org.uk) | GB intensity, 48 h national and regional forecasts | No key | $0, CC BY 4.0 |
| [Open-Meteo](https://open-meteo.com) | Hourly temperature (cooling water model) and 100 m wind | No key (non-commercial) | $0, CC BY 4.0 |
| [GSF Real Time Cloud](https://github.com/Green-Software-Foundation/real-time-cloud) | Annual marginal intensity and PUE per cloud region | Raw CSV over HTTPS | $0 (GSF terms; we fetch, never commit) |
| [EcoLogits](https://ecologits.ai) | LLM energy, GWP and water per request (ranges), electricity mixes | Python package | $0, open source |
| [ENTSO-E Transparency](https://transparency.entsoe.eu) *(optional)* | Day-ahead prices for every EU bidding zone | Free token by email | $0 |
| [WattTime](https://watttime.org) *(optional)* | Marginal emissions (MOER); free plan gives a relative index | Free account | $0 |
| [Fingrid open data](https://data.fingrid.fi) *(optional)* | Finnish real-time emission factors and wind | Free API key | $0 |

## Facts quoted in the docs

- GB curtailed a record 10 TWh of renewables in 2025, £363 m in constraint payments, 98 % in Scotland ([edie](https://www.edie.net/report-renewable-energy-curtailment-reached-record-high-in-2025/)).
- Finland: 724 negative-price hours in 2024, 447 in 2025 ([Gem Energy Analytics](https://gemenergyanalytics.substack.com/p/negative-electricity-prices-current)).
- GitLab.com hosted Linux runners run in GCP `us-east1` ([GitLab docs](https://docs.gitlab.com/ci/runners/hosted_runners/linux/)).
- Hamina (`europe-north1`) is cooled with seawater ([Trellis](https://trellis.net/article/google-uses-sea-water-cool-finland-data-center/)).
- Data-centre electricity ~415 TWh (2024) → ~945 TWh (2030) ([IEA](https://www.iea.org/reports/energy-and-ai/executive-summary)).

## What could not be reached from the build sandbox

The live APIs above were blocked by the sandbox's egress policy while building, so the adapters are
tested against recorded payloads in the documented formats, and the snapshots come from public
GitHub mirrors. In GitLab CI and on Cloud Run the adapters call the live APIs directly.
