from datetime import UTC, date, datetime, timedelta

import pytest

from core.connectors import registry
from core.models import Observation, Quality, TimeWindow

pytestmark = pytest.mark.spark

T0 = datetime(2026, 10, 23, tzinfo=UTC)
WINDOW = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))


def _obs(hour, value, metric="pm10", entity="palma"):
    return Observation("open_meteo", entity, metric, T0 + timedelta(hours=hour), value, "ug/m3")


def _frame(spark, observations):
    from core.pipeline import to_dataframe

    return to_dataframe(spark, observations, run_id="test")


@pytest.fixture
def connector():
    return registry.load("open_meteo")


def _results_by_rule(results):
    return {(r.rule, r.target): r for r in results}


def test_clean_series_passes_everything(spark, connector):
    from core.pipeline import apply_quality

    df = _frame(spark, [_obs(h, 10.0 + h) for h in range(24)])
    silver, results = apply_quality(df, connector, WINDOW)

    assert silver.count() == 24
    assert {r.quality for r in silver.collect()} == {Quality.OK}
    by_rule = _results_by_rule(results)
    assert by_rule[("range", "pm10")].passed
    assert by_rule[("duplicate", "*")].passed
    assert by_rule[("gaps", "pm10")].passed


def test_out_of_range_is_flagged_not_modified(spark, connector):
    from core.pipeline import apply_quality

    observations = [_obs(h, 10.0) for h in range(24)]
    observations[5] = _obs(5, -3.0)
    observations[6] = _obs(6, 5000.0)
    silver, results = apply_quality(_frame(spark, observations), connector, WINDOW)

    suspect = silver.where(f"quality = '{Quality.SUSPECT}'").collect()
    assert sorted(r.value for r in suspect) == [-3.0, 5000.0]  # value kept as-is
    assert {r.quality_reasons for r in suspect} == {"range"}
    assert _results_by_rule(results)[("range", "pm10")].failed == 2


def test_nulls_are_missing_and_count_as_gaps(spark, connector):
    from core.pipeline import apply_quality

    observations = [_obs(h, None if h in (1, 2) else 10.0) for h in range(24)]
    silver, results = apply_quality(_frame(spark, observations), connector, WINDOW)

    missing = silver.where(f"quality = '{Quality.MISSING}'").count()
    by_rule = _results_by_rule(results)
    assert missing == 2
    assert by_rule[("not_null", "value")].failed == 2
    assert by_rule[("gaps", "pm10")].failed == 2


def test_missing_hours_are_gaps(spark, connector):
    from core.pipeline import apply_quality

    observations = [_obs(h, 10.0) for h in range(24) if h not in (10, 11, 12)]
    _, results = apply_quality(_frame(spark, observations), connector, WINDOW)

    gaps = _results_by_rule(results)[("gaps", "pm10")]
    assert gaps.failed == 3
    assert gaps.checked == 24


def test_duplicates_are_detected_and_collapsed(spark, connector):
    from core.pipeline import apply_quality

    observations = [*(_obs(h, 10.0) for h in range(24)), _obs(0, 10.0), _obs(1, None)]
    silver, results = apply_quality(_frame(spark, observations), connector, WINDOW)

    assert silver.count() == 24
    assert _results_by_rule(results)[("duplicate", "*")].failed == 4
    # the duplicate with a null value never wins over the real value
    assert silver.where("value IS NULL").count() == 0


def test_rules_only_apply_to_their_metric(spark, connector):
    from core.pipeline import apply_quality

    # 1013 hPa is valid for pressure but would be out of range for pm10.
    observations = [_obs(h, 1013.0, metric="surface_pressure") for h in range(24)]
    silver, results = apply_quality(_frame(spark, observations), connector, WINDOW)

    assert silver.where(f"quality = '{Quality.OK}'").count() == 24
    assert _results_by_rule(results)[("range", "pm10")].checked == 0
