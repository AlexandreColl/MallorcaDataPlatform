"""Every endpoint against a real warehouse with the dbt marts: the SQL runs and the rows fit the response models.

Runs only with ``API_INTEGRATION=1`` (CI runs it after ``dbt build`` on the empty warehouse; locally it can point
at the stack's warehouse). Connection settings come from WAREHOUSE_* and API_DB_* as in the API itself.
"""

import os

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("API_INTEGRATION") != "1", reason="needs API_INTEGRATION=1 and a warehouse"),
]


@pytest.fixture(scope="module")
def api():
    with TestClient(create_app(Settings.from_env())) as client:  # the context manager opens the pool
        yield client


def test_health(api):
    assert api.get("/v1/health").json()["database"] == "ok"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/sources",
        "/v1/water/reserves",
        "/v1/water/aquifers",
        "/v1/climate/monthly",
        "/v1/tourism/monthly",
        "/v1/resources/monthly",
        "/v1/anomalies?start=2016-01-01T00:00:00Z&limit=5",
    ],
)
def test_every_endpoint_runs_its_sql(api, path):
    response = api.get(path)

    assert response.status_code == 200, response.text


def test_observations_of_every_source(api):
    for source in api.get("/v1/sources").json():
        response = api.get("/v1/observations", params={"source": source["source"], "limit": 3})
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) <= 3


def test_the_role_cannot_write(api):
    db = api.app.state.warehouse.db
    with pytest.raises(Exception, match=r"read-only|permission denied"):
        db.fetch_all("DELETE FROM gold.dim_sources")
