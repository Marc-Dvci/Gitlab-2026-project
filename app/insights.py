"""Weekly profile comparison of two regions' signals for the dashboard.

SEEDED BACKLOG (disclosed): ``weekly_pairs`` is deliberately naive — for every point of
one series it scans every point of the other (O(n·m)) instead of grouping by hour-of-week
first (O(n+m)). It is the first hot spot the agents find through carbon blame in the
demo; see docs/DEMO.md. Leave it for the agents to fix.
"""

from __future__ import annotations

from joulethief.signals.base import Series


def weekly_pairs(a: Series, b: Series) -> dict[tuple[int, int], list[tuple[float, float]]]:
    pairs: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for pa in a.points:
        key = (pa.start.weekday(), pa.start.hour)
        for pb in b.points:  # seeded inefficiency: quadratic scan
            if (pb.start.weekday(), pb.start.hour) == key:
                pairs.setdefault(key, []).append((pa.value, pb.value))
    return pairs


def compare(a: Series, b: Series) -> dict:
    pairs = weekly_pairs(a, b)
    profile = []
    for (weekday, hour), values in sorted(pairs.items()):
        mean_a = sum(x for x, _ in values) / len(values)
        mean_b = sum(y for _, y in values) / len(values)
        profile.append({"weekday": weekday, "hour": hour, "a": round(mean_a, 1), "b": round(mean_b, 1)})
    cleaner = sum(1 for p in profile if p["a"] < p["b"])
    return {"points": len(profile), "a_cleaner_share": cleaner / len(profile) if profile else None,
            "a_metric": a.metric, "b_metric": b.metric, "profile": profile}
