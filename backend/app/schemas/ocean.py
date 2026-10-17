"""Ocean API response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OceanResponse(BaseModel):
    """One ocean condition returned by the API."""

    ocean_id: int
    valid_time: datetime | None
    latitude: float | None
    longitude: float | None
    depth_m: float | None
    current_u_mps: float | None
    current_v_mps: float | None
    current_speed_mps: float | None
    current_direction_deg: float | None
    sea_surface_temperature_c: float | None
    wave_height_m: float | None
    wave_direction_deg: float | None
    wave_period_s: float | None
    is_forecast: bool | None
    source: str | None
    source_dataset: str | None
    ingested_at: datetime | None


class OceanListResponse(BaseModel):
    """Collection of matching ocean conditions."""

    count: int
    ocean: list[OceanResponse]