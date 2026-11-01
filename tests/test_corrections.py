from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

import core.corrections.runner as runner
from core.corrections.evaluation import evaluate, hide_gaps
from core.corrections.methods import (
    ABSENT,
    INTERPOLATION,
    SUPPORT,
    Candidate,
    InterpolationParams,
    SupportParams,
    calibrate,
    correct_series,
)
from core.corrections.runner import CorrectionConfig, Neighbours, correct_all, haversine_km
from core.models import Quality, TimeWindow

INTERPOLATE = InterpolationParams(max_gap_hours=3, confidence_scale_hours=6)
SUPPORT_PARAMS = SupportParams(
    max_distance_km=30,
    min_correlation=0.6,
    min_pairs=168,
    min_hour_pairs=7,
    distance_scale_km=100,
    gap_scale_hours=168,
)
START = pd.Timestamp("2026-10-01", tz="UTC")
HOURS = pd.date_range(START - pd.Timedelta(days=20), periods=30 * 24, freq="h")  # 20 days of history, 10 to correct
WINDOW_START = START
WINDOW_END = START + pd.Timedelta(days=10)


def _daily_cycle(hours: pd.DatetimeIndex, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 20 + 5 * np.sin(2 * np.pi * (hours.hour - 9) / 24) + rng.normal(0, 0.3, len(hours))


STATION = pd.Series(_daily_cycle(HOURS), index=HOURS)
# The support is 2 degrees warmer at night and 4 at midday (a model point at sea level, a station uphill).
SUPPORT_VALUES = STATION + 2 + 2 * (HOURS.hour.isin(range(10, 16)))


def _observations(values: pd.Series, *, missing=(), suspect=(), absent=()) -> pd.DataFrame:
    frame = pd.DataFrame({"ts": values.index, "value": values.to_numpy(), "quality": Quality.OK})
    frame.loc[frame["ts"].isin(missing), ["value", "quality"]] = [None, Quality.MISSING]
    frame.loc[frame["ts"].isin(suspect), "quality"] = Quality.SUSPECT
    return frame[~frame["ts"].isin(absent)].reset_index(drop=True)


def _hours(first: str, n: int) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(first, tz="UTC"), periods=n, freq="h")


def _correct(observations, candidates=()):
    return correct_series(
        observations,
        list(candidates),
        start=WINDOW_START,
        end=WINDOW_END,
        interpolation=INTERPOLATE,
        support=SUPPORT_PARAMS,
    )


def test_short_gaps_are_interpolated_between_the_station_values():
    gap = _hours("2026-10-03 10:00", 2)
    corrected, support = _correct(_observations(STATION, absent=gap))

    assert support is None
    assert list(corrected["ts"]) == list(gap)
    assert set(corrected["method"]) == {INTERPOLATION}
    before, after = STATION[gap[0] - pd.Timedelta(hours=1)], STATION[gap[-1] + pd.Timedelta(hours=1)]
    assert corrected["corrected_value"].iloc[0] == pytest.approx(before + (after - before) / 3, abs=1e-3)
    assert corrected["confidence"].iloc[0] == pytest.approx(np.exp(-2 / 6), abs=1e-3)
    assert set(corrected["original_quality"]) == {ABSENT}
    assert corrected["support_source"].isna().all()


def test_long_gaps_take_the_support_shifted_by_its_bias_per_hour():
    gap = _hours("2026-10-04 00:00", 24)
    candidate = Candidate("open_meteo", "palma", 8.5, SUPPORT_VALUES.drop(gap[:0]))
    corrected, support = _correct(_observations(STATION, missing=gap), [candidate])

    assert support is not None
    assert support.correlation > 0.9
    assert set(corrected["method"]) == {SUPPORT}
    assert set(corrected["support_entity"]) == {"palma"}
    errors = (corrected.set_index("ts")["corrected_value"] - STATION[gap]).abs()
    assert errors.max() < 1.5  # noise of both series, the bias itself is recovered
    midday = corrected.set_index("ts").loc[pd.Timestamp("2026-10-04 12:00", tz="UTC")]
    assert midday["bias"] == pytest.approx(-4, abs=0.3)
    assert corrected.set_index("ts").loc[gap[0], "bias"] == pytest.approx(-2, abs=0.3)
    assert set(corrected["original_quality"]) == {Quality.MISSING}
    expected = support.correlation**2 * np.exp(-8.5 / 100) * np.exp(-24 / 168)
    assert corrected["confidence"].iloc[0] == pytest.approx(expected, abs=1e-3)


def test_suspect_values_are_corrected_and_keep_their_original_value():
    hour = _hours("2026-10-05 08:00", 1)
    corrected, _ = _correct(_observations(STATION, suspect=hour))

    row = corrected.iloc[0]
    assert row["ts"] == hour[0]
    assert row["original_quality"] == Quality.SUSPECT
    assert row["original_value"] == pytest.approx(STATION[hour[0]])


def test_a_long_gap_without_a_correlated_support_stays_uncorrected():
    gap = _hours("2026-10-04 00:00", 24)
    noise = pd.Series(np.random.default_rng(1).normal(0, 1, len(HOURS)), index=HOURS)
    corrected, support = _correct(_observations(STATION, missing=gap), [Candidate("socib", "muro", 5, noise)])

    assert support is None
    assert corrected.empty


def test_the_best_correlated_candidate_wins():
    gap = _hours("2026-10-04 00:00", 24)
    worse = SUPPORT_VALUES + np.random.default_rng(2).normal(0, 2, len(HOURS))
    candidates = [Candidate("open_meteo", "far", 25, worse), Candidate("socib", "near", 12, SUPPORT_VALUES)]
    _, support = _correct(_observations(STATION, missing=gap), candidates)

    assert support.candidate.entity == "near"


def test_only_the_window_is_corrected_and_history_calibrates():
    before = _hours("2026-09-25 00:00", 2)
    corrected, _ = _correct(_observations(STATION, missing=before))

    assert corrected.empty


def test_calibration_needs_enough_shared_hours():
    short = Candidate("open_meteo", "palma", 5, SUPPORT_VALUES.iloc[:100])
    assert calibrate(STATION, short, SUPPORT_PARAMS) is None


def test_a_series_with_fewer_than_two_valid_values_is_left_alone():
    one = _observations(STATION.iloc[:1])
    corrected, support = _correct(one)
    assert corrected.empty
    assert support is None


CONFIG = CorrectionConfig(
    window_days=10,
    calibration_days=20,
    targets={"socib": ("socib", "open_meteo")},
    interpolation=INTERPOLATE,
    support=SUPPORT_PARAMS,
    evaluation={"gap_hours": [1, 3, 24], "gaps_per_series": 3},
)


def _silver(series: dict[tuple[str, str, str], pd.Series], coords: dict[tuple[str, str], tuple[float, float]]):
    frames = []
    for (source, entity, metric), values in series.items():
        lat, lon = coords[(source, entity)]
        frames.append(_observations(values).assign(source=source, entity=entity, metric=metric, lat=lat, lon=lon))
    return pd.concat(frames, ignore_index=True)[list(runner.OBSERVATION_COLUMNS)]


COORDS = {
    ("socib", "parcbit"): (39.635, 2.631),
    ("open_meteo", "palma"): (39.570, 2.650),  # 7 km
    ("open_meteo", "pollenca"): (39.877, 3.016),  # 43 km: too far
}


def test_neighbours_pick_series_of_the_same_metric_within_the_distance():
    silver = _silver(
        {
            ("socib", "parcbit", "temperature_2m"): STATION,
            ("open_meteo", "palma", "temperature_2m"): SUPPORT_VALUES,
            ("open_meteo", "palma", "wind_speed_10m"): SUPPORT_VALUES,
            ("open_meteo", "pollenca", "temperature_2m"): SUPPORT_VALUES,
        },
        COORDS,
    )
    candidates = Neighbours(runner.with_utc(silver), CONFIG).candidates("socib", "parcbit", "temperature_2m")

    assert [(c.source, c.entity) for c in candidates] == [("open_meteo", "palma")]
    assert candidates[0].distance_km == pytest.approx(haversine_km(39.635, 2.631, 39.570, 2.650), abs=0.1)
    assert Neighbours(runner.with_utc(silver), CONFIG).candidates("socib", "unknown", "temperature_2m") == []


def test_correct_all_corrects_only_the_targets_and_names_their_supports():
    gap = _hours("2026-10-04 00:00", 24)
    silver = _silver(
        {
            ("socib", "parcbit", "temperature_2m"): STATION.drop(gap),
            ("open_meteo", "palma", "temperature_2m"): SUPPORT_VALUES.drop(_hours("2026-10-06 00:00", 5)),
        },
        COORDS,
    )
    corrections, supports = correct_all(silver, CONFIG, WINDOW_START, WINDOW_END)

    assert set(corrections["source"]) == {"socib"}  # the model's own gap is not corrected
    assert len(corrections) == 24
    assert list(supports) == ["socib/parcbit/temperature_2m"]
    assert supports["socib/parcbit/temperature_2m"].startswith("open_meteo/palma r=0.9")


def test_correct_all_without_targets_returns_no_rows():
    silver = _silver({("open_meteo", "palma", "temperature_2m"): SUPPORT_VALUES}, COORDS)
    corrections, supports = correct_all(silver, CONFIG, WINDOW_START, WINDOW_END)
    assert corrections.empty
    assert list(corrections.columns) == list(runner.STORED_COLUMNS)
    assert supports == {}


def test_hidden_gaps_have_the_requested_length_and_clean_neighbours():
    masked, truth = hide_gaps(
        _observations(STATION), [1, 3, 24], 3, WINDOW_START, WINDOW_END, np.random.default_rng(0)
    )

    assert truth["gap_hours"].value_counts().to_dict() == {24: 72, 3: 9, 1: 3}
    hidden = masked[masked["quality"].eq(Quality.MISSING)]
    assert len(hidden) == len(truth)
    assert hidden["value"].isna().all()
    assert truth["truth"].to_numpy() == pytest.approx(STATION[truth["ts"]].to_numpy())


def test_benchmark_measures_the_error_with_and_without_the_bias():
    silver = _silver(
        {
            ("socib", "parcbit", "temperature_2m"): STATION,
            ("open_meteo", "palma", "temperature_2m"): SUPPORT_VALUES,
        },
        COORDS,
    )
    result = evaluate(silver, CONFIG, WINDOW_START, WINDOW_END, seed=0).set_index("gap_hours")

    assert list(result.index) == [1, 3, 24]
    assert (result["corrected"] == result["hidden"]).all()
    assert result.loc[1, "by_support"] == 0
    assert result.loc[24, "by_support"] == result.loc[24, "hidden"]
    assert result.loc[24, "mae"] < 0.6
    assert result.loc[24, "mae_without_bias"] > 2  # the raw model is 2-4 degrees off


def test_correct_values_replaces_the_window_with_plain_python_rows(monkeypatch, tmp_path):
    gap = _hours("2026-10-04 00:00", 2)
    silver = _silver({("socib", "parcbit", "temperature_2m"): STATION.drop(gap)}, COORDS)
    config_file = tmp_path / "corrections.yaml"
    config_file.write_text(
        """
window_days: 10
calibration_days: 20
targets: {socib: {supports: [socib, open_meteo]}, eea_air_quality: {supports: [eea_air_quality]}}
interpolation: {max_gap_hours: 3, confidence_scale_hours: 6}
support: {max_distance_km: 30, min_correlation: 0.6, min_pairs: 168, min_hour_pairs: 7,
          distance_scale_km: 100, gap_scale_hours: 168}
""",
        encoding="utf-8",
    )
    stored = {}

    class FakeSettings:
        corrections_config = config_file

    class FakeWarehouse:
        def __init__(self, settings):
            pass

        def ensure_schema(self):
            stored["schema"] = True

        def replace_corrections(self, sources, window, rows, run_id):
            stored.update(sources=sources, window=window, rows=rows, run_id=run_id)
            return len(rows)

    def fake_load(settings, sources, read_from, end):
        stored["read"] = (sources, read_from, end)
        return silver

    monkeypatch.setattr(runner, "Warehouse", FakeWarehouse)
    monkeypatch.setattr(runner, "load_observations", fake_load)
    monkeypatch.setattr(runner.TimeWindow, "last_days", classmethod(lambda cls, days: TimeWindow(
        date(2026, 10, 1), date(2026, 10, 10))))

    summary = runner.correct_values(1, sources=["socib", "aemet"], run_id="r1", settings=FakeSettings())

    assert summary.sources == ["socib"]
    assert summary.corrections == {INTERPOLATION: 2}
    assert summary.series == 1
    assert stored["read"][0] == ["open_meteo", "socib"]
    assert stored["read"][1] == pd.Timestamp("2026-09-11", tz="UTC")
    assert stored["sources"] == ["socib"]
    assert stored["run_id"] == "r1"
    row = stored["rows"][0]
    assert row[:4] == ("socib", "parcbit", "temperature_2m", datetime(2026, 10, 4, tzinfo=UTC))
    assert row[4] is None  # absent: no original value
    assert row[8:11] == (None, None, None)  # interpolation: no support, no bias
    assert type(row[3]) is datetime


def test_correct_values_without_configured_targets_does_nothing(monkeypatch, tmp_path):
    class FakeSettings:
        corrections_config = tmp_path / "c.yaml"

    FakeSettings.corrections_config.write_text(
        "window_days: 14\ncalibration_days: 30\ntargets: {socib: {supports: [open_meteo]}}\n"
        "interpolation: {max_gap_hours: 3, confidence_scale_hours: 6}\n"
        "support: {max_distance_km: 30, min_correlation: 0.6, min_pairs: 168, min_hour_pairs: 7,"
        " distance_scale_km: 100, gap_scale_hours: 168}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "load_observations", lambda *a: pytest.fail("nothing to read"))

    summary = runner.correct_values(1, sources=["aemet"], run_id="r2", settings=FakeSettings())

    assert summary.sources == []
    assert summary.corrections == {}


def test_the_repository_config_loads():
    from core.config import Settings

    config = CorrectionConfig.load(Settings.from_env().corrections_config)
    assert set(config.targets) == {"socib", "eea_air_quality"}
    assert config.read_sources() == ["eea_air_quality", "open_meteo", "socib"]
    assert config.only(["socib"]).targets == {"socib": ("socib", "open_meteo")}
