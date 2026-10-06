"""Time series of grid signals (prices, carbon intensity, weather)."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence


def utc(dt: datetime) -> datetime:
    """Return an aware UTC datetime (naive values are assumed to be UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_time(value: str) -> datetime:
    """Parse the ISO-ish timestamps used by NESO ("2026-10-06T12:30Z"), Open-Meteo and others."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return utc(datetime.fromisoformat(text))


@dataclass(frozen=True)
class Point:
    start: datetime
    value: float


@dataclass
class Series:
    """A regular time series. ``points[i]`` covers ``[start, start + resolution)``."""

    zone: str
    metric: str
    unit: str
    resolution: timedelta
    points: Sequence[Point]
    source: str
    kind: str = "actual"  # "actual" | "forecast" | "derived"
    notes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        pts = sorted((Point(utc(p.start), float(p.value)) for p in self.points), key=lambda p: p.start)
        self.points = tuple(pts)
        self._starts = [p.start for p in self.points]

    def __len__(self) -> int:
        return len(self.points)

    def __iter__(self):
        return iter(self.points)

    @property
    def start(self) -> datetime:
        return self.points[0].start

    @property
    def end(self) -> datetime:
        return self.points[-1].start + self.resolution

    def values(self) -> list[float]:
        return [p.value for p in self.points]

    def value_at(self, t: datetime) -> float | None:
        t = utc(t)
        i = bisect.bisect_right(self._starts, t) - 1
        if i < 0:
            return None
        p = self.points[i]
        if p.start <= t < p.start + self.resolution:
            return p.value
        return None

    def slice(self, start: datetime, end: datetime) -> "Series":
        start, end = utc(start), utc(end)
        pts = [p for p in self.points if start <= p.start < end]
        return self._with(pts, self.resolution)

    def resample(self, resolution: timedelta) -> "Series":
        """Mean-aggregate to a coarser grid, or repeat values onto a finer one."""
        if resolution == self.resolution:
            return self
        if resolution > self.resolution:
            buckets: dict[datetime, list[float]] = {}
            for p in self.points:
                epoch = p.start.timestamp()
                step = resolution.total_seconds()
                key = datetime.fromtimestamp(epoch - (epoch % step), tz=timezone.utc)
                buckets.setdefault(key, []).append(p.value)
            pts = [Point(k, sum(v) / len(v)) for k, v in sorted(buckets.items())]
            return self._with(pts, resolution)
        pts = []
        for p in self.points:
            t = p.start
            while t < p.start + self.resolution:
                pts.append(Point(t, p.value))
                t += resolution
        return self._with(pts, resolution)

    def on_grid(self, start: datetime, slots: int, slot: timedelta) -> list[float | None]:
        """Values sampled at ``start + i * slot`` (mid-slot lookup), ``None`` where missing."""
        start = utc(start)
        return [self.value_at(start + i * slot + slot / 2) for i in range(slots)]

    def percentile_rank(self, value: float) -> float:
        vals = sorted(self.values())
        if not vals:
            return float("nan")
        return bisect.bisect_left(vals, value) / len(vals)

    def mean(self) -> float:
        vals = self.values()
        return sum(vals) / len(vals) if vals else float("nan")

    def _with(self, pts: Iterable[Point], resolution: timedelta) -> "Series":
        return Series(self.zone, self.metric, self.unit, resolution, list(pts), self.source, self.kind, dict(self.notes))


def infer_resolution(starts: Sequence[datetime], default: timedelta = timedelta(hours=1)) -> timedelta:
    """Smallest positive gap between consecutive timestamps."""
    gaps = [b - a for a, b in zip(starts, starts[1:]) if b > a]
    return min(gaps) if gaps else default
