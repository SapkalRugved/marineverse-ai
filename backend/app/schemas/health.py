"""Health and readiness response schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Describe the running API service."""

    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Describe API dependency readiness."""

    status: str
    database: str
