"""Response models. They mirror the contracted dbt marts, so a contract change shows up here as well."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class Health(BaseModel):
    """Liveness of the API and of its warehouse connection."""

    status: str = Field(examples=["ok"])
    database: str = Field(examples=["ok"], description="`ok` or `unavailable`")
    version: str = Field(examples=["0.9.0"])


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


class Location(BaseModel):
    """A place a source measures at (gold.dim_locations with its source from gold.dim_sources)."""

    source: str = Field(examples=["aemet"])
    label: str | None = Field(examples=["AEMET (estaciones oficiales)"])
    kind: str | None = Field(examples=["observation"], description="`observation`, `model`, `schedule`...")
    entity: str = Field(examples=["B278"])
    lat: float
    lon: float
    first_seen: datetime | None
    last_seen: datetime | None
    n_metrics: int


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


class Correction(BaseModel):
    """A proposed value for a station hour without a valid one (gold.fct_observations_corrected).

    Corrections never change the observation: the original value and quality come with the corrected one.
    """

    source: str = Field(examples=["socib"])
    entity: str = Field(examples=["parcbit"])
    metric: str = Field(examples=["temperature_2m"])
    ts: datetime
    unit: str | None = Field(examples=["degC"])
    original_quality: str = Field(examples=["missing"], description="`missing`, `suspect` or `absent` (no row)")
    original_value: float | None = Field(description="The suspect value; empty when it was missing or absent.")
    corrected_value: float
    method: str = Field(examples=["support"], description="`interpolation` (gaps up to 3 h) or `support`")
    support_source: str | None = Field(examples=["open_meteo"], description="Method `support`: the series used.")
    support_entity: str | None = Field(examples=["llucmajor"])
    bias: float | None = Field(description="Station minus support at that hour of the day, added to the support.")
    confidence: float = Field(ge=0, le=1, description="From the correlation, the distance and the gap length.")


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


class MobilityDay(BaseModel):
    """Scheduled public transport of one network in one day (gold.fct_bus_network_daily, fct_island_transit_daily)."""

    network: str = Field(examples=["emt_palma"], description="`emt_palma` (Palma buses) or `ctm` (the island)")
    local_date: date
    is_weekend: bool
    stops: int
    stops_with_service: int
    scheduled_stop_calls: float | None = Field(description="Vehicles calling at a stop, summed over every stop.")
    avg_lines_per_served_stop: float | None
    busiest_stop: str | None
    busiest_stop_departures: float | None


class StopService(BaseModel):
    """The scheduled service of one stop on the latest day of its network."""

    network: str = Field(examples=["ctm"])
    stop: str = Field(examples=["stop_452"])
    lat: float
    lon: float
    local_date: date
    departures: float | None
    lines: float | None


class WeatherSourceDay(BaseModel):
    """Island-wide weather of one source in one day: the mean of its stations or points (gold.fct_weather_daily)."""

    source: str = Field(examples=["aemet"])
    source_label: str | None
    source_kind: str | None = Field(examples=["observation"], description="`observation` or `model`")
    local_date: date
    entities: int
    temperature_mean: float | None
    temperature_max: float | None
    temperature_min: float | None
    precipitation_mean: float | None
    wind_gust_max: float | None


class StationDay(BaseModel):
    """The weather of one station or model point on the latest day of its source (gold.fct_weather_daily)."""

    source: str = Field(examples=["aemet"])
    entity: str = Field(examples=["B228"])
    lat: float
    lon: float
    local_date: date
    temperature_mean: float
    temperature_max: float | None
    temperature_min: float | None
    precipitation_sum: float | None
    wind_gust_max: float | None


class WeatherWarning(BaseModel):
    """An AEMET warning: one zone and phenomenon at one level for a period (gold.fct_weather_warnings)."""

    warning_id: str
    zone: str = Field(examples=["645403"])
    zone_name: str | None = Field(examples=["Interior de Mallorca"])
    zone_kind: str | None = Field(examples=["land"], description="`land` or `coast`")
    phenomenon: str = Field(examples=["rain"], description="`rain`, `storms`, `wind`, `coastal`, `max_temperature`...")
    level: int = Field(ge=1, le=3, description="1 yellow, 2 orange, 3 red.")
    start_ts: datetime
    end_ts: datetime


class WarningZone(BaseModel):
    """An AEMET warning zone of Mallorca with its polygon (gold.dim_warning_zones)."""

    zone: str = Field(examples=["645403"])
    name: str = Field(examples=["Interior de Mallorca"])
    kind: str = Field(examples=["land"])
    polygon: list[list[float]] = Field(description="[lon, lat] vertices.")


class WeatherEpisode(BaseModel):
    """Consecutive days of heavy rain, strong wind or high waves on the island (gold.fct_weather_episodes)."""

    episode_id: str
    start_date: date
    end_date: date
    days: int
    episode_type: str = Field(examples=["rain + wind + sea"])
    peak_rain_mm: float | None
    peak_rain_station: str | None
    peak_rain_day: date | None
    max_stations_over_rain_threshold: int | None
    peak_gust_kmh: float | None
    peak_wave_m: float | None


class ModelBias(BaseModel):
    """Error of the weather model against one station (gold.agg_model_bias_by_station): model minus station."""

    station_source: str
    station: str
    model_point: str
    distance_km: float | None
    days_compared: int
    temperature_bias_c: float | None
    temperature_mae_c: float | None
    temperature_rmse_c: float | None
    precipitation_bias_total_mm: float | None
    rain_day_agreement: float | None
    wind_speed_bias_kmh: float | None
    first_day: date | None
    last_day: date | None


class AirQualityNow(BaseModel):
    """The latest hour of one air quality station or model point (gold.air_quality_hourly)."""

    source: str = Field(examples=["eea_air_quality"])
    entity: str = Field(examples=["bellver"])
    lat: float | None
    lon: float | None
    ts: datetime
    pm2_5: float | None
    pm10: float | None
    no2: float | None
    o3: float | None
    eaqi_band: int = Field(description="European AQI band, 1 (good) to 6 (extremely poor), from the worst pollutant.")
    eaqi_label: str | None = Field(examples=["fair"])


class SeaHour(BaseModel):
    """Sea conditions at one coastal point in one hour (gold.fct_sea_conditions_hourly)."""

    point: str
    lat: float | None
    lon: float | None
    ts: datetime
    wave_height_m: float | None
    wave_period_s: float | None
    swell_height_m: float | None
    sea_temperature_c: float | None


class Earthquake(BaseModel):
    """One earthquake located by the IGN, in its latest revision (gold.fct_earthquakes)."""

    event_id: str
    ts: datetime
    lat: float
    lon: float
    magnitude: float | None
    depth_km: float | None
    distance_to_palma_km: float | None


class QualityRule(BaseModel):
    """The latest check of one quality rule on one source (gold.data_quality_summary)."""

    source: str
    rule: str = Field(examples=["range"])
    target: str = Field(examples=["temperature_2m_mean"])
    checked: int
    failed: int
    passed: bool
    failed_ratio: float | None
    checked_at: datetime | None


class AnomaliesDay(BaseModel):
    """How many values one detector flagged in one local day (silver.anomalies)."""

    local_date: date
    detector: str = Field(examples=["robust_zscore"])
    anomalies: int


class Error(BaseModel):
    """Every error has the same shape."""

    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["unknown source 'foo'"])


class ErrorResponse(BaseModel):
    """Body of every 4xx and 5xx response."""

    error: Error
