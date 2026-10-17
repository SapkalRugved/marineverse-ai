"""Weather API response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WeatherResponse(BaseModel):
    """One weather condition returned by the API."""

    weather_id: int
    valid_time: datetime | None
    latitude: float | None
    longitude: float | None
    air_temperature_c: float | None
    pressure_hpa: float | None
    precipitation_mm: float | None
    wind_speed_mps: float | None
    wind_direction_deg: float | None
    wind_gust_mps: float | None
    is_forecast: bool | None
    source: str | None
    source_dataset: str | None
    ingested_at: datetime | None


class WeatherListResponse(BaseModel):
    """Collection of matching weather conditions."""

    count: int
    weather: list[WeatherResponse]