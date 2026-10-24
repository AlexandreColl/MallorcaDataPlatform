"""Applies a list of rules to a silver DataFrame and labels each row."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from core.connectors.base import ConnectorConfig
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
)


class QualityEngine:
    def __init__(self, rules: list[Rule]) -> None:
        self.row_rules = [r for r in rules if isinstance(r, RowRule)]
        self.dataset_rules = [r for r in rules if isinstance(r, DatasetRule)]

    def run(self, df: DataFrame) -> tuple[DataFrame, list[RuleResult]]:
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
            for rule, failed_col, scope_col in flag_cols:
                results.append(
                    RuleResult(
                        rule=rule.name,
                        target=rule.target,
                        checked=int(counts[scope_col] or 0),
                        failed=int(counts[failed_col] or 0),
                    )
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
    """Default rule set derived from a connector's YAML."""
    freq = config.frequency_delta
    expected_steps = int((window.end_dt_exclusive() - window.start_dt()) / freq)
    rules: list[Rule] = [NotNullRule(), DuplicateRule(), GapRule(expected_steps, freq)]
    for metric in config.metrics.values():
        if metric.min is not None or metric.max is not None:
            rules.append(RangeRule(metric.name, metric.min, metric.max))
    return rules
