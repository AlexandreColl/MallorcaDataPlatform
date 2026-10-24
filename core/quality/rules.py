"""Reusable data-quality rules over the silver DataFrame.

Two kinds of rules:

* row rules  - return a boolean Column (True = row fails). Failing rows get the rule
  name appended to ``quality_reasons`` and are labelled ``suspect``. Rows are never
  dropped or modified: flagging and correcting are separate steps.
* dataset rules - inspect the whole frame (e.g. gaps in a time series) and only
  produce a ``RuleResult``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

KEY_COLUMNS = ("source", "entity", "metric", "ts")


@dataclass(frozen=True)
class RuleResult:
    rule: str
    target: str
    checked: int
    failed: int
    details: str = ""

    @property
    def passed(self) -> bool:
        return self.failed == 0


class Rule(ABC):
    name: str = "rule"
    target: str = "*"


class RowRule(Rule):
    @abstractmethod
    def failed(self) -> Column:
        """True when the row breaks the rule."""

    def scope(self) -> Column:
        """Rows the rule applies to (used for the `checked` count)."""
        return F.lit(True)


class DatasetRule(Rule):
    @abstractmethod
    def evaluate(self, df: DataFrame) -> list[RuleResult]: ...


class NotNullRule(RowRule):
    name = "not_null"

    def __init__(self, column: str = "value") -> None:
        self.column = column
        self.target = column

    def failed(self) -> Column:
        return F.col(self.column).isNull()


class RangeRule(RowRule):
    name = "range"

    def __init__(self, metric: str, min_value: float | None, max_value: float | None) -> None:
        if min_value is None and max_value is None:
            raise ValueError("RangeRule needs at least one bound")
        self.metric = metric
        self.target = metric
        self.min_value = min_value
        self.max_value = max_value

    def scope(self) -> Column:
        return (F.col("metric") == self.metric) & F.col("value").isNotNull()

    def failed(self) -> Column:
        below = F.col("value") < self.min_value if self.min_value is not None else F.lit(False)
        above = F.col("value") > self.max_value if self.max_value is not None else F.lit(False)
        return self.scope() & (below | above)


class DuplicateRule(RowRule):
    name = "duplicate"

    def __init__(self, keys: tuple[str, ...] = KEY_COLUMNS) -> None:
        self.keys = keys

    def failed(self) -> Column:
        return F.count(F.lit(1)).over(Window.partitionBy(*self.keys)) > 1


class GapRule(DatasetRule):
    """Missing time steps per (source, entity, metric) for the expected frequency."""

    name = "gaps"

    def __init__(self, expected_steps: int, frequency: timedelta) -> None:
        self.expected_steps = expected_steps
        self.frequency = frequency

    def evaluate(self, df: DataFrame) -> list[RuleResult]:
        present = (
            df.where(F.col("value").isNotNull())
            .groupBy("source", "entity", "metric")
            .agg(F.countDistinct("ts").alias("present"))
        )
        series = df.select("source", "entity", "metric").distinct()
        per_series = series.join(present, ["source", "entity", "metric"], "left").fillna(
            0, subset=["present"]
        )
        rows = (
            per_series.groupBy("metric")
            .agg(
                F.count(F.lit(1)).alias("n_series"),
                F.sum("present").alias("present"),
            )
            .collect()
        )
        results = []
        for row in rows:
            expected = int(row["n_series"]) * self.expected_steps
            present_n = int(row["present"] or 0)
            results.append(
                RuleResult(
                    rule=self.name,
                    target=row["metric"],
                    checked=expected,
                    failed=max(expected - present_n, 0),
                    details=f"expected={expected} present={present_n} freq={self.frequency}",
                )
            )
        return results
