"""Virtual capacity curves, after Google's carbon-intelligent computing platform.

Google limits the capacity available to *flexible* work hour by hour, shaped by the
carbon forecast, while preserving enough total capacity for the day's flexible demand
(Radovanović et al., "Carbon-Aware Computing for Datacenters", IEEE Trans. Power Syst.
2023). Joule Thief applies the same idea to GitLab runner and agent concurrency: the
curve caps how many deferrable jobs may run per slot, which also stops every job from
piling into the single cleanest hour and creating a new demand peak.
"""

from __future__ import annotations

import math


def virtual_capacity_curve(signal: list[float | None], demand_slot_units: float, floor: int, ceiling: int,
                           headroom: float = 1.25) -> list[int]:
    """Concurrency limit per slot.

    ``demand_slot_units`` is the flexible work to fit (sum over jobs of duration in slots).
    Every slot gets ``floor`` (room for urgent work); the remaining demand × ``headroom`` is
    water-filled into the cleanest slots first, up to ``ceiling`` per slot. Unknown slots
    (``None``) are filled last.
    """
    if ceiling < floor:
        raise ValueError("ceiling must be >= floor")
    n = len(signal)
    cap = [floor] * n
    remaining = math.ceil(max(0.0, demand_slot_units * headroom - floor * n))
    order = sorted(range(n), key=lambda i: (signal[i] is None, signal[i] if signal[i] is not None else 0.0, i))
    for i in order:
        if remaining <= 0:
            break
        add = min(ceiling - floor, remaining)
        cap[i] += add
        remaining -= add
    return cap
