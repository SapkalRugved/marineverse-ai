"""MarineVerse Marine Data API."""

from fastapi import FastAPI

from backend.app.api.health import (
    API_VERSION,
    router as health_router,
)
from backend.app.api.ports import router as ports_router
from backend.app.api.weather import router as weather_router
from backend.app.api.vessels import router as vessels_router
from backend.app.api.ocean import router as ocean_router
from backend.app.api.freshness import router as freshness_router

app = FastAPI(
    title="MarineVerse Marine Data API",
    description=(
        "Unified API for ports, weather, ocean, and vessel data."
    ),
    version=API_VERSION,
)

app.include_router(health_router)
app.include_router(freshness_router)
app.include_router(ocean_router)
app.include_router(ports_router)
app.include_router(weather_router)
app.include_router(vessels_router)