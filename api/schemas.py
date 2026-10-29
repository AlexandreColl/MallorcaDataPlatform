"""Response models. They mirror the contracted dbt marts, so a contract change shows up here as well."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class Health(BaseModel):
    """Liveness of the API and of its warehouse connection."""

    status: str = Field(examples=["ok"])
    database: str = Field(examples=["ok"], description="`ok` or `unavailable`")
    version: str = Field(examples=["0.6.0"])


class Source(BaseModel):
    """One data source and its health (gold.source_health)."""

    source: str = Field(examples=["aemet"])
    label: str | None = Field(examples=["AEMET (estaciones oficiales)"])
    kind: str | None = Field(examples=["observation"])
    last_status: str | None = Field(examples=["success"])
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_loaded_day: date | None
    runs_7d: int
    failure_rate_7d: float | None = Field(description="Share of failed runs in the last 7 days (0-1).")
    latest_observation_ts: datetime | None
    data_age_hours: float | None
    observations: int


class Observation(BaseModel):
    """One value of a series in the common schema (gold.fct_observations)."""

    source: str = Field(examples=["aemet"])
    entity: str = Field(examples=["B278"])
    metric: str = Field(examples=["temperature_2m_mean"])
    ts: datetime
    value: float | None
    unit: str | None = Field(examples=["degC"])
    quality: str = Field(examples=["ok"], description="`ok`, `suspect` or `missing`")
    lat: float | None = None
    lon: float | None = None


class Anomaly(BaseModel):
    """A value flagged by an anomaly detector (silver.anomalies). Flags never change the observation."""

    source: str
    entity: str
    metric: str
    ts: datetime
    detector: str = Field(examples=["robust_zscore"])
    value: float | None
    expected: float | None
    score: float | None
    threshold: float | None


class Page[T](BaseModel):
    """A page of results. Ask for the next one with ``offset=next_offset`` while it is not null."""

    items: list[T]
    limit: int
    offset: int
    next_offset: int | None = Field(description="Offset of the next page, or null on the last one.")


class WaterReservesMonth(BaseModel):
    """Groundwater reserves of Mallorca in one month (gold.fct_water_reserves_monthly)."""

    month: date
    hydrological_year: int = Field(description="September to August, named after the year it ends in.")
    reserves_pct: float = Field(description="Share of a full aquifer, island-wide.")
    change_1m_pts: float | None
    change_12m_pts: float | None
    same_month_mean_pct: float | None
    anomaly_pts: float | None = Field(description="Reserves minus the mean of the same calendar month.")
    aquifers: int | None
    aquifers_below_30_pct: int | None
    lowest_aquifer: str | None
    lowest_aquifer_pct: float | None


class Aquifer(BaseModel):
    """One groundwater body of Mallorca in the latest published month."""

    entity: str = Field(examples=["aquifer_1805m1"])
    code: str = Field(examples=["1805M1"])
    aquifer: str = Field(examples=["Pollença"])
    hydrogeological_unit: str = Field(examples=["Almadrava"])
    month: date
    reserves_pct: float | None
    change_12m_pts: float | None


class ClimateMonth(BaseModel):
    """Climate of Mallorca in one month from the AEMET stations (gold.fct_climate_monthly)."""

    month: date
    hydrological_year: int
    rain_stations: int
    rain_mm: float | None
    rain_same_month_mean_mm: float | None
    rain_anomaly: float | None = Field(description="Against the mean of the same month (0.2 = 20 % more).")
    rain_hydrological_year_mm: float | None
    rain_hydrological_year_mean_mm: float | None
    wet_days: float | None
    temperature_stations: int
    temperature_mean_c: float | None
    temperature_anomaly_c: float | None
    temperature_max_c: float | None
    hot_days: float | None
    same_month_years: int


class TourismMonth(BaseModel):
    """Balearic tourism in one month (gold.fct_tourism_monthly, Dataestur)."""

    month: date
    international_tourists: float | None
    international_spending_eur: float | None
    international_tourist_nights: float | None
    spending_per_tourist_eur: float | None
    hotel_guests: float | None
    hotel_nights: float | None
    hotel_average_stay_nights: float | None
    hotel_bed_occupancy_pct: float | None
    hotels_open: float | None
    hotel_staff: float | None
    airport_passengers: float | None
    international_tourists_yoy: float | None
    airport_passengers_yoy: float | None


class ResourcesMonth(BaseModel):
    """Tourism, water, climate and electricity in one month, with anomalies (gold.fct_resources_monthly)."""

    month: date
    hydrological_year: int
    international_tourists: float | None
    tourists_anomaly: float | None
    international_spending_eur: float | None
    airport_passengers: float | None
    hotel_bed_occupancy_pct: float | None
    electricity_demand_gwh: float | None
    electricity_demand_anomaly: float | None
    reserves_pct: float | None
    reserves_change_1m_pts: float | None
    reserves_anomaly_pts: float | None
    rain_mm: float | None
    rain_hydrological_year_mm: float | None
    rain_anomaly: float | None
    temperature_mean_c: float | None
    temperature_anomaly_c: float | None
    hot_days: float | None


class Error(BaseModel):
    """Every error has the same shape."""

    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["unknown source 'foo'"])


class ErrorResponse(BaseModel):
    """Body of every 4xx and 5xx response."""

    error: Error
