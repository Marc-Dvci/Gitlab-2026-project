"""Low / likely / high estimates.

Every environmental number Joule Thief reports carries a range, because almost none of
them are measured directly (cloud VMs hide RAPL, LLM providers do not publish energy
per request). Arithmetic is interval arithmetic for non-negative quantities.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Union

Number = Union[int, float]


@dataclass(frozen=True)
class Estimate:
    low: float
    likely: float
    high: float

    def __post_init__(self) -> None:
        if not (self.low <= self.likely <= self.high):
            raise ValueError(f"expected low <= likely <= high, got {self.low}, {self.likely}, {self.high}")

    @classmethod
    def exact(cls, value: Number) -> "Estimate":
        return cls(float(value), float(value), float(value))

    @classmethod
    def from_range(cls, low: Number, high: Number, likely: Number | None = None) -> "Estimate":
        lo, hi = float(min(low, high)), float(max(low, high))
        mid = (lo + hi) / 2 if likely is None else float(likely)
        return cls(lo, min(max(mid, lo), hi), hi)

    @classmethod
    def zero(cls) -> "Estimate":
        return cls(0.0, 0.0, 0.0)

    def _coerce(self, other: "Estimate | Number") -> "Estimate":
        if isinstance(other, Estimate):
            return other
        if isinstance(other, Real):
            return Estimate.exact(other)
        return NotImplemented  # type: ignore[return-value]

    def __add__(self, other: "Estimate | Number") -> "Estimate":
        o = self._coerce(other)
        if o is NotImplemented:
            return NotImplemented
        return Estimate(self.low + o.low, self.likely + o.likely, self.high + o.high)

    __radd__ = __add__

    def __sub__(self, other: "Estimate | Number") -> "Estimate":
        """Difference of two uncertain quantities: the range widens on both sides."""
        o = self._coerce(other)
        if o is NotImplemented:
            return NotImplemented
        return Estimate(self.low - o.high, self.likely - o.likely, self.high - o.low)

    def __mul__(self, other: "Estimate | Number") -> "Estimate":
        o = self._coerce(other)
        if o is NotImplemented:
            return NotImplemented
        products = (self.low * o.low, self.low * o.high, self.high * o.low, self.high * o.high)
        return Estimate(min(products), self.likely * o.likely, max(products))

    __rmul__ = __mul__

    def __truediv__(self, other: Number) -> "Estimate":
        if not isinstance(other, Real) or other == 0:
            raise ValueError("can only divide an Estimate by a non-zero number")
        if other > 0:
            return Estimate(self.low / other, self.likely / other, self.high / other)
        return Estimate(self.high / other, self.likely / other, self.low / other)

    def to_dict(self, digits: int = 6) -> dict[str, float]:
        return {"low": round(self.low, digits), "likely": round(self.likely, digits), "high": round(self.high, digits)}

    def __format__(self, spec: str) -> str:
        spec = spec or ".3g"
        return f"{self.likely:{spec}} [{self.low:{spec}}–{self.high:{spec}}]"


def total(estimates: list[Estimate]) -> Estimate:
    acc = Estimate.zero()
    for e in estimates:
        acc = acc + e
    return acc
