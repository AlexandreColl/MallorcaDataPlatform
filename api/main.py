"""FastAPI application factory: ``uvicorn --factory api.main:create_app`` (tests pass a fake database)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import __version__
from api.database import Database, PooledDatabase
from api.middleware import RateLimit, ResponseCache
from api.repository import Warehouse
from api.routes import CACHED_PATHS, router
from api.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

DESCRIPTION = """
Read-only access to the gold layer of the Mallorca Data Platform: the data behind the Grafana dashboards.

* **Platform**: health of the API and of every data source.
* **Series**: any observation in the common schema (source, entity, metric, time, value, quality), the values
  flagged by the anomaly detectors and the proposed corrections of the station gaps, paginated.
* **Monthly**: groundwater reserves, climate, tourism and the combined resources mart, each month with its anomaly
  against the same calendar month.

The marts rebuilt once a day are cached for an hour and carry an `ETag`. Each client may make 300 requests a minute
(`RateLimit-*` headers; 429 with `Retry-After` beyond that). `/v1/observations/export` gives a series as CSV or
Parquet.

Every response comes from a dbt mart with an enforced contract, so column names and types are stable.
"""

_CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    422: "invalid_request",
    429: "rate_limited",
    503: "unavailable",
}


def _error(status_code: int, message: str) -> JSONResponse:
    code = _CODES.get(status_code, "error")
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    """Build the application. Without ``database`` it opens a connection pool to the warehouse at start-up."""
    settings = settings or Settings.from_env()
    # The pool is opened and closed with the app; a database passed in (the tests) is the caller's.
    pooled: PooledDatabase | None = None
    if database is None:
        database = pooled = PooledDatabase(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if pooled is not None:
            pooled.open()
        yield
        if pooled is not None:
            pooled.close()

    app = FastAPI(
        title="Mallorca Data Platform API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "platform", "description": "API and data source health."},
            {"name": "series", "description": "Observations, anomalies and corrections, paginated."},
            {"name": "monthly", "description": "Monthly marts: water, climate, tourism and resources."},
        ],
    )
    app.state.settings = settings
    app.state.warehouse = Warehouse(database)
    # The last one added runs first: CORS headers also reach the 429s, and a cached answer still costs a token.
    app.add_middleware(ResponseCache, seconds=settings.cache_seconds, paths=CACHED_PATHS)
    app.add_middleware(RateLimit, per_minute=settings.rate_limit_per_minute, exempt=("/v1/health",))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET"],
        expose_headers=["ETag", "Retry-After", "RateLimit-Limit", "RateLimit-Remaining", "X-Cache", "X-Total-Count"],
    )
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return _error(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first.get("loc", ()) if part != "query")
        return _error(422, f"{where}: {first.get('msg', 'invalid value')}")

    return app
