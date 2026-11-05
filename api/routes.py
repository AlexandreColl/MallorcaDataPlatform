"""Version 1 of the API: read-only endpoints over the gold marts."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api import __version__
from api.repository import Warehouse
from api.schemas import (
    AirQualityNow,
    AnomaliesDay,
    Anomaly,
    Aquifer,
    ClimateMonth,
    Correction,
    Earthquake,
    ErrorResponse,
    Health,
    Location,
    MobilityDay,
    ModelBias,
    Municipality,
    Observation,
    Page,
    PopulationYear,
    QualityRule,
    ResourcesMonth,
    SeaHour,
    Source,
    StationDay,
    StopService,
    TourismMonth,
    WarningZone,
    WaterReservesMonth,
    WeatherEpisode,
    WeatherSourceDay,
    WeatherWarning,
)

router = APIRouter(prefix="/v1", responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})

DEFAULT_PAGE_SIZE = 100
DEFAULT_DAYS = 7
WARNINGS_AHEAD_DAYS = 3


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
FromDay = Annotated[date | None, Query(alias="from", description="First local day (included).")]
ToDay = Annotated[date | None, Query(alias="to", description="Last local day (included). Default: today.")]


def _window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    """Default window (the last 7 days); instants without a time zone are read as UTC."""
    end = end or datetime.now(UTC)
    end = end if end.tzinfo else end.replace(tzinfo=UTC)
    start = start or end - timedelta(days=DEFAULT_DAYS)
    start = start if start.tzinfo else start.replace(tzinfo=UTC)
    if start >= end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "`start` must be before `end`")
    return start, end


def _days(start: date | None, end: date | None, default_days: int) -> tuple[date, date]:
    """A range of local days, both included: by default the last ``default_days`` days up to today."""
    end = end or datetime.now(UTC).date()
    start = start or end - timedelta(days=default_days - 1)
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "`from` must not be after `to`")
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


@router.get("/locations", tags=["platform"])
def locations(
    warehouse: WarehouseDep,
    source: Annotated[str | None, Query(description="Only this source.")] = None,
) -> list[Location]:
    """Every place with coordinates: stations, model points and stops. Series without a place are left out."""
    return [Location(**row) for row in warehouse.locations(source)]


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
    rows = warehouse.anomalies(source=source, detector=detector, start=start, end=end, limit=limit + 1, offset=offset)
    return _page([Anomaly(**row) for row in rows], limit, offset)


@router.get("/corrections", tags=["series"])
def corrections(  # noqa: PLR0913 - one query parameter per filter
    request: Request,
    warehouse: WarehouseDep,
    source: Annotated[str | None, Query(description="Only this source: `socib` or `eea_air_quality`.")] = None,
    entity: Annotated[str | None, Query(description="Only this station.")] = None,
    method: Annotated[Literal["interpolation", "support"] | None, Query(description="Only this method.")] = None,
    start: Start = None,
    end: End = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> Page[Correction]:
    """Proposed values for station hours without a valid one, newest first, paginated."""
    _check_limit(limit, get_max_page_size(request))
    start, end = _window(start, end)
    rows = warehouse.corrections(
        source=source, entity=entity, method=method, start=start, end=end, limit=limit + 1, offset=offset
    )
    return _page([Correction(**row) for row in rows], limit, offset)


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


@router.get("/mobility/daily", tags=["mobility"])
def mobility_daily(warehouse: WarehouseDep, from_: FromDay = None, to: ToDay = None) -> list[MobilityDay]:
    """Scheduled service per day of the EMT Palma and CTM networks (default: the last 90 days)."""
    start, end = _days(from_, to, 90)
    return [MobilityDay(**row) for row in warehouse.mobility_daily(start, end)]


@router.get("/mobility/stops", tags=["mobility"])
def mobility_stops(
    warehouse: WarehouseDep,
    network: Annotated[Literal["emt_palma", "ctm"] | None, Query(description="Only this network.")] = None,
) -> list[StopService]:
    """Every stop with its scheduled departures and lines on the latest day of its network, busiest first."""
    return [StopService(**row) for row in warehouse.mobility_stops(network)]


@router.get("/weather/daily", tags=["environment"])
def weather_daily(warehouse: WarehouseDep, from_: FromDay = None, to: ToDay = None) -> list[WeatherSourceDay]:
    """Island-wide daily weather per source: the mean of its stations or model points (default: the last 30 days)."""
    start, end = _days(from_, to, 30)
    return [WeatherSourceDay(**row) for row in warehouse.weather_daily(start, end)]


@router.get("/weather/stations", tags=["environment"])
def weather_stations(
    warehouse: WarehouseDep,
    source: Annotated[
        Literal["aemet", "socib", "open_meteo"],
        Query(description="`aemet` (33 official stations), `socib` or `open_meteo` (the model)."),
    ] = "aemet",
) -> list[StationDay]:
    """Every station of a source on its latest day with temperatures (AEMET publishes 2-3 days late)."""
    return [StationDay(**row) for row in warehouse.weather_stations(source)]


@router.get("/warnings", tags=["environment"])
def warnings(warehouse: WarehouseDep, start: Start = None, end: End = None) -> list[WeatherWarning]:
    """AEMET warnings of the zones of Mallorca that overlap the range (default: in force now or in the next 3 days)."""
    now = datetime.now(UTC)
    start, end = _window(start or now, end or now + timedelta(days=WARNINGS_AHEAD_DAYS))
    return [WeatherWarning(**row) for row in warehouse.warnings(start, end)]


@router.get("/warnings/zones", tags=["environment"])
def warning_zones(warehouse: WarehouseDep) -> list[WarningZone]:
    """The AEMET warning zones of Mallorca (land and coastal waters) with their polygons."""
    return [WarningZone(**{**row, "polygon": json.loads(row["polygon"])}) for row in warehouse.warning_zones()]


@router.get("/population", tags=["population"])
def population(
    warehouse: WarehouseDep,
    from_year: Annotated[int | None, Query(alias="from", ge=1996, description="First year (included).")] = None,
    to_year: Annotated[int | None, Query(alias="to", le=2100, description="Last year (included).")] = None,
) -> list[PopulationYear]:
    """Population of every municipality of Mallorca on 1 January (INE municipal register; default: every year)."""
    first, last = from_year or 1996, to_year or 2100
    if first > last:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "`from` must not be after `to`")
    return [PopulationYear(**row) for row in warehouse.population(first, last)]


@router.get("/municipalities", tags=["population"])
def municipalities(warehouse: WarehouseDep) -> list[Municipality]:
    """The 53 municipalities of Mallorca with their area and boundary (IGN)."""
    return [Municipality(**{**row, "polygon": json.loads(row["polygon"])}) for row in warehouse.municipalities()]


@router.get("/weather/episodes", tags=["environment"])
def weather_episodes(warehouse: WarehouseDep, from_: FromDay = None, to: ToDay = None) -> list[WeatherEpisode]:
    """Episodes of heavy rain, strong wind or high waves, newest first (default: the last 365 days)."""
    start, end = _days(from_, to, 365)
    return [WeatherEpisode(**row) for row in warehouse.episodes(start, end)]


@router.get("/weather/model-bias", tags=["environment"])
def weather_model_bias(warehouse: WarehouseDep) -> list[ModelBias]:
    """How far the weather model is from each official station, worst first."""
    return [ModelBias(**row) for row in warehouse.model_bias()]


@router.get("/air-quality/latest", tags=["environment"])
def air_quality_latest(warehouse: WarehouseDep) -> list[AirQualityNow]:
    """The latest hour of each air quality station and model point, with its European AQI band."""
    return [AirQualityNow(**row) for row in warehouse.air_quality_latest()]


@router.get("/sea/hourly", tags=["environment"])
def sea_hourly(warehouse: WarehouseDep, start: Start = None, end: End = None) -> list[SeaHour]:
    """Hourly waves and sea temperature at the coastal points (default: the last 7 days)."""
    start, end = _window(start, end)
    return [SeaHour(**row) for row in warehouse.sea_hourly(start, end)]


@router.get("/earthquakes", tags=["environment"])
def earthquakes(warehouse: WarehouseDep, from_: FromDay = None, to: ToDay = None) -> list[Earthquake]:
    """Earthquakes located by the IGN in and around Mallorca, newest first (default: the last 10 years)."""
    start, end = _days(from_, to, 3650)
    return [Earthquake(**row) for row in warehouse.earthquakes(start, end)]


@router.get("/quality/rules", tags=["platform"])
def quality_rules(warehouse: WarehouseDep) -> list[QualityRule]:
    """The latest check of every quality rule on every source, failing ones first."""
    return [QualityRule(**row) for row in warehouse.quality_rules()]


@router.get("/anomalies/daily", tags=["series"])
def anomalies_daily(warehouse: WarehouseDep, start: Start = None, end: End = None) -> list[AnomaliesDay]:
    """Flagged values per local day and detector (default: the last 7 days)."""
    start, end = _window(start, end)
    return [AnomaliesDay(**row) for row in warehouse.anomalies_daily(start, end)]
