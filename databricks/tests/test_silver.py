from datetime import UTC, datetime

from core.models import Observation
from mdp_databricks.silver import newest_per_key


def _obs(entity: str, hour: int, value: float) -> Observation:
    return Observation("open_meteo", entity, "temperature_2m", datetime(2026, 11, 22, hour, tzinfo=UTC), value, "°C")


def test_the_latest_fetch_of_a_key_wins_over_older_payloads():
    older = [_obs("palma", 0, 10.0), _obs("palma", 1, 11.0)]  # windows of consecutive days overlap on hour 1
    newer = [_obs("palma", 1, 11.5), _obs("palma", 2, 12.0)]

    assert newest_per_key([older, newer]) == [[_obs("palma", 0, 10.0)], newer]


def test_a_key_repeated_inside_one_payload_is_kept_for_the_duplicate_rule():
    batch = [_obs("palma", 0, 10.0), _obs("palma", 0, 10.0)]

    assert newest_per_key([batch]) == [batch]


def test_a_refetched_window_contributes_nothing_from_its_older_copy():
    copy = [_obs("palma", 0, 10.0), _obs("alcudia", 0, 9.0)]

    assert newest_per_key([copy, list(copy)]) == [[], copy]
