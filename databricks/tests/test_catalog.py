import pytest

from mdp_databricks.catalog import Names, setup_statements
from mdp_databricks.gold import gold_statements
from mdp_databricks.silver import merge_statement


def test_names_place_each_layer_in_its_schema():
    names = Names("mallorca")

    assert names.raw_volume == "/Volumes/mallorca/bronze/raw"
    assert names.bronze == "mallorca.bronze.payloads"
    assert names.silver == "mallorca.silver.observations"
    assert names.gold("weather_daily") == "mallorca.gold.weather_daily"


@pytest.mark.parametrize("catalog", ["", "Mallorca", "mallorca; DROP CATALOG x", "1st", "my-catalog"])
def test_names_reject_anything_but_a_plain_identifier(catalog):
    with pytest.raises(ValueError, match="identifier"):
        Names(catalog)


def test_setup_creates_before_it_grants():
    statements = setup_statements(Names("mallorca"), "account users")

    grants = [i for i, s in enumerate(statements) if s.startswith("GRANT")]
    assert statements[0].startswith("CREATE CATALOG IF NOT EXISTS mallorca")
    assert grants == [len(statements) - 2, len(statements) - 1]
    assert statements[-1] == "GRANT USE SCHEMA, SELECT ON SCHEMA mallorca.gold TO `account users`"


def test_setup_is_idempotent():
    for statement in setup_statements(Names("mallorca"), "account users"):
        assert statement.startswith("GRANT") or "IF NOT EXISTS" in statement


@pytest.mark.parametrize("readers", ["", "  ", "x` TO `everyone"])
def test_setup_rejects_a_principal_that_would_break_the_grant(readers):
    with pytest.raises(ValueError, match="principal"):
        setup_statements(Names("mallorca"), readers)


def test_merge_matches_on_the_key_and_skips_unchanged_rows():
    sql = merge_statement("mallorca.silver.observations")

    assert "ON t.source = s.source AND t.entity = s.entity AND t.metric = s.metric AND t.ts = s.ts" in sql
    assert "LEFT ANTI JOIN mallorca.silver.observations AS cur" in sql
    assert "u.value <=> cur.value" in sql  # a null value is a value too
    assert "u.quality_reasons <=> cur.quality_reasons" in sql


def test_gold_builds_the_pairs_before_the_bias_that_joins_them():
    tables = list(gold_statements(Names("mallorca")))

    assert tables.index("air_quality_daily") < tables.index("air_quality_model_bias_daily")
    assert tables.index("station_model_pairs") < tables.index("air_quality_model_bias_daily")
