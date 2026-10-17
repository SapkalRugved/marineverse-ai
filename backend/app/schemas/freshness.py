"""Data-freshness API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


FreshnessStatus = Literal["fresh", "stale", "missing"]


class DatasetFreshnessResponse(BaseModel):
    """Freshness information for one dataset."""

    dataset: str
    status: FreshnessStatus
    latest_valid_time: datetime | None
    latest_ingested_at: datetime | None
    last_successful_run_at: datetime | None
    age_seconds: float | None
    maximum_age_seconds: int


class FreshnessResponse(BaseModel):
    """Freshness report for all marine datasets."""

    status: FreshnessStatus
    checked_at: datetime
    datasets: list[DatasetFreshnessResponse]