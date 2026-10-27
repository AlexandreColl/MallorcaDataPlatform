"""Synthetic faults injected into real series: the ground truth that real data lacks.

Real anomalies are unlabelled, so a detector's precision and recall cannot be measured on them. Corrupting a
series on purpose gives exactly that: every injected value is known to be wrong and everything else is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

# Scales the MAD to the standard deviation of normally distributed data.
_MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class FaultSpec:
    """How many faults of one kind each series gets, how long and how big.

    ``length`` is in values and ``size`` in robust standard deviations of the series, both drawn uniformly
    from their ``(min, max)`` range.
    """

    count: int
    length: tuple[int, int] = (1, 1)
    size: tuple[float, float] = (0.0, 0.0)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FaultSpec:
        """Build from a YAML mapping such as ``{count: 1, length: [6, 24]}``."""
        length = data.get("length", 1)
        size = data.get("size", 0.0)
        return cls(
            count=int(data["count"]),
            length=tuple(length) if isinstance(length, list) else (int(length), int(length)),
            size=tuple(size) if isinstance(size, list) else (float(size), float(size)),
        )


def robust_sigma(values: np.ndarray) -> float:
    """MAD-based standard deviation (falls back to the plain one for mostly constant series)."""
    mad = float(np.median(np.abs(values - np.median(values))))
    return _MAD_TO_SIGMA * mad if mad > 0 else float(np.std(values))


class FaultInjector:
    """Corrupts a series with non-overlapping faults of three kinds.

    * ``spike``: one value pushed up or down by ``size`` sigmas (a glitch, a decimal-point error).
    * ``frozen``: ``length`` values stuck at the last good reading (a frozen sensor or a repeated payload).
    * ``drift``: ``length`` values with a linear offset growing to ``size`` sigmas (a sensor losing calibration).
    """

    KINDS = ("spike", "frozen", "drift")

    def __init__(self, specs: dict[str, FaultSpec], margin: int = 6, max_attempts: int = 200) -> None:
        unknown = sorted(set(specs) - set(self.KINDS))
        if unknown:
            msg = f"unknown fault kinds {unknown}; available {list(self.KINDS)}"
            raise ValueError(msg)
        self.specs = specs
        self.margin = margin  # clean values kept between two faults so each one is judged on its own
        self.max_attempts = max_attempts

    def inject(self, series: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
        """Return a copy of ``series`` (``ts``, ``value``) with the faults applied.

        Adds ``fault`` (kind, or None for clean values) and ``event`` (id of the fault, -1 for clean values).
        A constant series is returned unchanged: no fault size can be defined on it.
        """
        out = series.reset_index(drop=True).copy()
        values = out["value"].to_numpy(dtype=float).copy()
        fault = np.full(len(values), None, dtype=object)
        event = np.full(len(values), -1)
        sigma = robust_sigma(values) if len(values) else 0.0
        if sigma > 0:
            taken = np.zeros(len(values), dtype=bool)
            event_id = 0
            for kind in self.KINDS:
                spec = self.specs.get(kind)
                for _ in range(spec.count if spec else 0):
                    span = self._place(spec, taken, rng)
                    if span is None:
                        break  # series too short for more faults
                    start, stop = span
                    self._apply(kind, values[start:stop], values[start - 1], sigma * rng.uniform(*spec.size), rng)
                    fault[start:stop] = kind
                    event[start:stop] = event_id
                    taken[max(0, start - self.margin) : stop + self.margin] = True
                    event_id += 1
        out["value"] = values
        out["fault"] = fault
        out["event"] = event
        return out

    def _place(self, spec: FaultSpec, taken: np.ndarray, rng: np.random.Generator) -> tuple[int, int] | None:
        """Random free span of the spec's length, never at the very start (frozen needs a previous value)."""
        length = int(rng.integers(spec.length[0], spec.length[1] + 1))
        if length + 1 >= len(taken):
            return None
        for _ in range(self.max_attempts):
            start = int(rng.integers(1, len(taken) - length + 1))
            if not taken[start : start + length].any():
                return start, start + length
        return None

    @staticmethod
    def _apply(kind: str, span: np.ndarray, previous: float, size: float, rng: np.random.Generator) -> None:
        """Modify ``span`` (a view of the series) in place; ``previous`` is the value just before it."""
        sign = rng.choice((-1.0, 1.0))
        if kind == "spike":
            span += sign * size
        elif kind == "frozen":
            span[:] = previous
        else:  # drift
            span += sign * size * np.linspace(1 / len(span), 1, len(span))
