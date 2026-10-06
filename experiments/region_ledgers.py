"""Average vs marginal, per Google Cloud region — why decisions and reports need different numbers.

Sources (fetched at run time, nothing redistributed):
  * Google Cloud region carbon data 2024 (CFE %, location-based grid intensity) — Apache-2.0.
  * Green Software Foundation Real Time Cloud metadata (annual marginal intensity, PUE).

Run: python experiments/region_ledgers.py  → docs/results/region_ledgers.md
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from joulethief.signals.regions import REGIONS, google_region_carbon, gsf_region_metadata  # noqa: E402

FOCUS = ["us-east1", "us-west1", "northamerica-northeast1", "europe-west2", "europe-north1", "europe-southwest1",
         "europe-west4", "europe-west1", "europe-north2"]


def main() -> None:
    google = google_region_carbon()
    gsf = gsf_region_metadata()
    lines = ["# Average vs marginal by region (generated)", "",
             "Location-based average intensity (Google, 2024) answers *how clean is the electricity here?* "
             "Annual marginal intensity (GSF Real Time Cloud, WattTime-derived) answers *what does one more kWh "
             "here cause?* Joule Thief reports the first and decides on the second — and only claims savings "
             "for load moved into surplus hours, where the marginal kWh is renewable that would be curtailed.", "",
             "| Region | City | Google CFE | Avg gCO₂/kWh | Marginal gCO₂/kWh (annual) | Marginal ÷ average |",
             "|---|---|---:|---:|---:|---:|"]
    for name in FOCUS:
        g = google.get(name)
        m = gsf.get(name, {}).get("marginal_annual")
        city = REGIONS[name].city if name in REGIONS else ""
        if not g:
            continue
        ratio = f"{m / g.grid_intensity_avg:.1f}×" if m and g.grid_intensity_avg else "—"
        lines.append(f"| `{name}` | {city} | {g.google_cfe:.0%} | {g.grid_intensity_avg:.0f} | "
                     f"{m:.0f} | {ratio} |" if m else f"| `{name}` | {city} | {g.google_cfe:.0%} | {g.grid_intensity_avg:.0f} | — | — |")
    lines += ["", "Reading: Montréal and Finland look almost carbon-free on average, but extra demand there is met "
              "on the margin by generation (or lost exports) that is far dirtier. Average-based scheduling would "
              "call any hour there 'clean'; marginal-based dispatch waits for genuine surplus."]
    out = ROOT / "docs" / "results" / "region_ledgers.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
