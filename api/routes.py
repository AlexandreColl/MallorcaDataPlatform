"""Version 1 of the API: read-only endpoints over the gold marts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api import __version__
from api.repository import Warehouse
from api.schemas import (
    Anomaly,
    Aquifer,
    ClimateMonth,
    ErrorResponse,
    Health,
    Observation,
    Page,
    ResourcesMonth,
    Source,
    TourismMonth,
    WaterReservesMonth,
)

router = APIRouter(prefix="/v1", responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})

DEFAULT_PAGE_SIZE = 100
DEFAULT_DAYS = 7


def get_warehouse(request: Request) -> Warehouse:
    """The repository built at start-up (replaced by a fake in tests)."""
    return request.app.state.warehouse


def get_max_page_size(request: Request) -> int:
    """Largest ``limit`` a client may ask for."""
    return request.app.state.settings.max_page_size


WarehouseDep = Annotated[Warehouse, Depends(get_warehouse)]
Limit = Annotated[int, Query(ge=1, description="Items per page (at most API_MAX_PAGE_SIZE, 1000 by default).")]
Offset = Annotated[int, Query(ge=0, description="Items to skip: the `next_offset` of the previous page.")]
Start = Annotated[datetime | None, Query(description="From this instant (included). Default: `end` minus 7 days.")]
End = Annotated[datetime | None, Query(description="Until this instant (excluded). Default: now.")]
FromMonth = Annotated[date | None, Query(alias="from", description="First month, e.g. 2025-09-01 (included).")]
ToMonth = Annotated[date | None, Query(alias="to", description="Last month (included).")]


def _window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    """Default window (the last 7 days); instants without a time zone are read as UTC."""
    end = end or datetime.now(UTC)
    end = end if end.tzinfo else end.replace(tzinfo=UTC)
    start = start or end - timedelta(days=DEFAULT_DAYS)
    start = start if start.tzinfo else start.replace(tzinfo=UTC)
    if start >= end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "`start` must be before `end`")
    return start, end


def _page[T](items: list[T], limit: int, offset: int) -> Page[T]:
    """A page from ``limit + 1`` fetched rows: the extra row only says that there is a next page."""
    has_more = len(items) > limit
    return Page[T](items=items[:limit], limit=limit, offset=offset, next_offset=offset + limit if has_more else None)


def _check_limit(limit: int, max_page_size: int) -> None:
    if limit > max_page_size:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"`limit` must be at most {max_page_size}")


@router.get("/health", tags=["platform"])
def health(request: Request) -> Health:
    """Liveness of the API and of its connection to the warehouse (503 while the warehouse is down)."""
    ok = request.app.state.warehouse.db.ping()
    if not ok:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "warehouse unavailable")
    return Health(status="ok", database="ok", version=__version__)


@router.get("/sources", tags=["platform"])
def sources(warehouse: WarehouseDep) -> list[Source]:
    """Every data source with its last run, failure rate in the last 7 days and the age of its latest value."""
    return [Source(**row) for row in warehouse.sources()]


@router.get("/sources/{source}", tags=["platform"], responses={404: {"model": ErrorResponse}})
def source(source: str, warehouse: WarehouseDep) -> Source:
    """One data source and its health."""
    rows = warehouse.sources(source)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown source '{source}'")
    return Source(**rows[0])


@router.get("/observations", tags=["series"], responses={404: {"model": ErrorResponse}})
def observations(  # noqa: PLR0913 - one query parameter per filter
    request: Request,
    warehouse: WarehouseDep,
    source: Annotated[str, Query(description="Source, e.g. `aemet` (see /v1/sources).")],
    metric: Annotated[str | None, Query(description="Metric, e.g. `temperature_2m_mean`.")] = None,
    entity: Annotated[str | None, Query(description="Station, point, stop or aquifer.")] = None,
    start: Start = None,
    end: End = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> Page[Observation]:
    """Values of one source in a time range, oldest first, paginated."""
    _check_limit(limit, get_max_page_size(request))
    start, end = _window(start, end)
    if not warehouse.source_exists(source):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown source '{source}'")
    rows = warehouse.observations(
        source=source, metric=metric, entity=entity, start=start, end=end, limit=limit + 1, offset=offset
    )
    return _page([Observation(**row) for row in rows], limit, offset)


@router.get("/anomalies", tags=["series"])
def anomalies(  # noqa: PLR0913 - one query parameter per filter
    request: Request,
    warehouse: WarehouseDep,
    source: Annotated[str | None, Query(description="Only this source.")] = None,
    detector: Annotated[str | None, Query(description="`robust_zscore` or `isolation_forest`.")] = None,
    start: Start = None,
    end: End = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> Page[Anomaly]:
    """Values flagged by the anomaly detectors in a time range, newest first, paginated."""
    _check_limit(limit, get_max_page_size(request))
    start, end = _window(start, end)
    rows = warehouse.anomalies(
        source=source, detector=detector, start=start, end=end, limit=limit + 1, offset=offset
    )
    return _page([Anomaly(**row) for row in rows], limit, offset)


@router.get("/water/reserves", tags=["monthly"])
def water_reserves(warehouse: WarehouseDep, from_: FromMonth = None, to: ToMonth = None) -> list[WaterReservesMonth]:
    """Groundwater reserves of Mallorca per month, with the anomaly against the same calendar month."""
    return [WaterReservesMonth(**row) for row in warehouse.monthly("water", from_, to)]


@router.get("/water/aquifers", tags=["monthly"])
def water_aquifers(warehouse: WarehouseDep) -> list[Aquifer]:
    """The 18 aquifers of Mallorca in the latest published month, lowest first, with their change in 12 months."""
    return [Aquifer(**row) for row in warehouse.aquifers()]


@router.get("/climate/monthly", tags=["monthly"])
def climate_monthly(warehouse: WarehouseDep, from_: FromMonth = None, to: ToMonth = None) -> list[ClimateMonth]:
    """Rainfall and temperature of the AEMET stations per month, with anomalies and the hydrological year."""
    return [ClimateMonth(**row) for row in warehouse.monthly("climate", from_, to)]


@router.get("/tourism/monthly", tags=["monthly"])
def tourism_monthly(warehouse: WarehouseDep, from_: FromMonth = None, to: ToMonth = None) -> list[TourismMonth]:
    """Balearic tourism per month: international tourists and spending, hotels and Palma airport."""
    return [TourismMonth(**row) for row in warehouse.monthly("tourism", from_, to)]


@router.get("/resources/monthly", tags=["monthly"])
def resources_monthly(warehouse: WarehouseDep, from_: FromMonth = None, to: ToMonth = None) -> list[ResourcesMonth]:
    """Tourism, water, climate and electricity per month, each with its anomaly against the same calendar month."""
    return [ResourcesMonth(**row) for row in warehouse.monthly("resources", from_, to)]
