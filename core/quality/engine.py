"""Applies a list of rules to a silver DataFrame and labels each row."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from core.models import Quality, TimeWindow
from core.quality.rules import (
    DatasetRule,
    DuplicateRule,
    GapRule,
    NotNullRule,
    RangeRule,
    RowRule,
    Rule,
    RuleResult,
    SourceQcRule,
)

if TYPE_CHECKING:
    from datetime import timedelta

    from core.connectors.base import ConnectorConfig


class QualityEngine:
    """Runs row rules and dataset rules over a silver DataFrame."""

    def __init__(self, rules: list[Rule]) -> None:
        self.row_rules = [r for r in rules if isinstance(r, RowRule)]
        self.dataset_rules = [r for r in rules if isinstance(r, DatasetRule)]

    def run(self, df: DataFrame) -> tuple[DataFrame, list[RuleResult]]:
        """Label every row (``quality``, ``quality_reasons``) and return the rule results.

        Values are never modified or dropped: flagging and correcting are separate steps.
        """
        flag_cols = []
        for i, rule in enumerate(self.row_rules):
            failed_col, scope_col = f"_qf_{i}", f"_qs_{i}"
            df = df.withColumn(failed_col, F.coalesce(rule.failed(), F.lit(False)))
            df = df.withColumn(scope_col, F.coalesce(rule.scope(), F.lit(False)))
            flag_cols.append((rule, failed_col, scope_col))

        results: list[RuleResult] = []
        if flag_cols:
            aggs = []
            for _, failed_col, scope_col in flag_cols:
                aggs.append(F.sum(F.col(failed_col).cast("long")).alias(failed_col))
                aggs.append(F.sum(F.col(scope_col).cast("long")).alias(scope_col))
            counts = df.agg(*aggs).first()
            results.extend(
                RuleResult(
                    rule=rule.name,
                    target=rule.target,
                    checked=int(counts[scope_col] or 0),
                    failed=int(counts[failed_col] or 0),
                )
                for rule, failed_col, scope_col in flag_cols
            )

        for rule in self.dataset_rules:
            results.extend(rule.evaluate(df))

        # Reasons exclude not_null: a null value is already labelled `missing`.
        reason_exprs = [
            F.when(F.col(failed_col), F.lit(rule.name))
            for rule, failed_col, _ in flag_cols
            if not isinstance(rule, NotNullRule)
        ]
        reasons = F.concat_ws(";", *reason_exprs) if reason_exprs else F.lit("")
        df = df.withColumn("quality_reasons", F.when(reasons != "", reasons))
        df = df.withColumn(
            "quality",
            F.when(F.col("value").isNull(), F.lit(Quality.MISSING))
            .when(F.col("quality_reasons").isNotNull(), F.lit(Quality.SUSPECT))
            .otherwise(F.lit(Quality.OK)),
        )
        temp = [c for _, f, s in flag_cols for c in (f, s)]
        return df.drop(*temp), results


def rules_for(config: ConnectorConfig, window: TimeWindow) -> list[Rule]:
    """Default rule set derived from a connector's YAML.

    One gaps rule per sampling frequency, so hourly and daily datasets of the same
    connector are each checked against their own expected number of steps. Event
    datasets have no expected steps and get no gaps rule.
    """
    span = window.end_dt_exclusive() - window.start_dt()
    by_frequency: dict[timedelta, set[str]] = defaultdict(set)
    for metric in config.metrics.values():
        freq = config.frequency_for(metric.dataset)
        if freq is not None:
            by_frequency[freq].add(metric.name)
    if not by_frequency and not config.is_event_source:  # no declared metrics: check all at the default frequency
        by_frequency[config.frequency_delta] = set()

    rules: list[Rule] = [NotNullRule(), SourceQcRule(), DuplicateRule()]
    rules.extend(
        GapRule(int(span / freq), freq, frozenset(metrics) or None) for freq, metrics in sorted(by_frequency.items())
    )
    rules.extend(
        RangeRule(metric.name, metric.min, metric.max)
        for metric in config.metrics.values()
        if metric.min is not None or metric.max is not None
    )
    return rules
