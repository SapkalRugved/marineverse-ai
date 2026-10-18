"""AIS vessel API response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class VesselPositionResponse(BaseModel):
    """Latest known position for one vessel."""

    position_id: int
    observed_at: datetime | None
    latitude: float | None
    longitude: float | None
    speed_mps: float | None
    course_deg: float | None
    heading_deg: float | None
    navigation_status: str | None
    source: str | None
    ingested_at: datetime | None


class VesselResponse(BaseModel):
    """One vessel and its latest known position."""

    vessel_id: int
    mmsi: int | None
    imo: int | None
    name: str | None
    ship_type: str | None
    length_m: float | None
    width_m: float | None
    source: str | None
    updated_at: datetime | None
    latest_position: VesselPositionResponse | None


class VesselListResponse(BaseModel):
    """Collection of vessels with latest positions."""

    count: int
    vessels: list[VesselResponse]
