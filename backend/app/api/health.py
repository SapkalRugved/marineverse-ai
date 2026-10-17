"""Liveness and readiness endpoints."""

from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.health import (
    HealthResponse,
    ReadinessResponse,
)
from backend.app.services.health import database_is_ready


API_SERVICE_NAME = "marineverse-api"
API_VERSION = "0.1.0"

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check API liveness",
)
def get_health() -> HealthResponse:
    """Return API process health without external dependencies."""
    return HealthResponse(
        status="ok",
        service=API_SERVICE_NAME,
        version=API_VERSION,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Check API readiness",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "PostgreSQL is unavailable.",
        },
    },
)
def get_readiness() -> ReadinessResponse:
    """Return readiness after checking PostgreSQL."""
    if not database_is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready.",
        )

    return ReadinessResponse(
        status="ready",
        database="postgresql",
    )
