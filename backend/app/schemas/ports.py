"""Port API response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PortResponse(BaseModel):
    """One port returned by the API."""

    port_id: int
    source_id: str | None
    name: str | None
    country: str | None
    port_type: str | None
    latitude: float | None
    longitude: float | None
    source: str | None
    updated_at: datetime | None


class PortListResponse(BaseModel):
    """Collection of matching ports."""

    count: int
    ports: list[PortResponse]
