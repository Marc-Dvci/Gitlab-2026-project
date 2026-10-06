"""Split-conformal prediction intervals for grid forecasts, per lead time.

NESO publishes a 48 h carbon-intensity forecast but no error bars. From the archived
forecast history we calibrate, for each lead time, the (1 − α) quantile of the absolute
forecast error; that quantile gives intervals with distribution-free coverage guarantees
(on exchangeable data). The dispatcher can then plan on the pessimistic bound for
deadline-critical work. Day-ahead *prices* need no interval once published: they are
market clearing results, not forecasts — one reason the price signal is preferred.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime


def conformal_quantile(residuals: list[float], alpha: float) -> float:
    if not residuals:
        raise ValueError("no residuals")
    ordered = sorted(residuals)
    k = math.ceil((len(ordered) + 1) * (1 - alpha))
    return ordered[min(k, len(ordered)) - 1]


@dataclass
class ConformalIntervals:
    alpha: float
    q_by_lead: dict[int, float]

    @classmethod
    def fit(cls, errors_by_lead: dict[int, list[tuple[datetime, float, float]]], alpha: float = 0.1) -> "ConformalIntervals":
        return cls(alpha, {lead: conformal_quantile([abs(a - f) for _, f, a in rows], alpha)
                           for lead, rows in errors_by_lead.items() if rows})

    def bucket(self, lead_hours: float) -> int:
        """Smallest calibrated lead >= the requested one (never uses fresher information than available)."""
        leads = sorted(self.q_by_lead)
        for lead in leads:
            if lead >= lead_hours:
                return lead
        return leads[-1]

    def interval(self, forecast: float, lead_hours: float) -> tuple[float, float]:
        q = self.q_by_lead[self.bucket(lead_hours)]
        return max(0.0, forecast - q), forecast + q

    def coverage(self, errors_by_lead: dict[int, list[tuple[datetime, float, float]]]) -> dict[int, float]:
        out = {}
        for lead, rows in errors_by_lead.items():
            if lead in self.q_by_lead and rows:
                q = self.q_by_lead[lead]
                out[lead] = sum(1 for _, f, a in rows if abs(a - f) <= q) / len(rows)
        return out


def chronological_split(errors_by_lead: dict[int, list[tuple[datetime, float, float]]], fraction: float = 0.6):
    calib, test = {}, {}
    for lead, rows in errors_by_lead.items():
        rows = sorted(rows)
        cut = int(len(rows) * fraction)
        calib[lead], test[lead] = rows[:cut], rows[cut:]
    return calib, test


def rolling_coverage(errors_by_lead: dict[int, list[tuple[datetime, float, float]]], alpha: float = 0.1,
                     window_days: int = 14) -> dict[int, float]:
    """Coverage when the interval is re-calibrated every day on the trailing ``window_days`` only.

    Grid forecast errors drift with the season; recalibrating on a trailing window keeps the
    empirical coverage close to nominal where a single static calibration under-covers.
    """
    from datetime import timedelta

    out = {}
    for lead, rows in errors_by_lead.items():
        rows = sorted(rows)
        hits = total = 0
        for t, f, a in rows:
            past = [abs(aa - ff) for tt, ff, aa in rows if t - timedelta(days=window_days) <= tt < t - timedelta(hours=lead)]
            if len(past) < 48:
                continue
            q = conformal_quantile(past, alpha)
            hits += abs(a - f) <= q
            total += 1
        if total:
            out[lead] = hits / total
    return out
