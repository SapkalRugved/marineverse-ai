"""MarineVerse Marine Data API."""

from fastapi import FastAPI

from backend.app.api.health import (
    API_VERSION,
    router as health_router,
)
from backend.app.api.ports import router as ports_router


app = FastAPI(
    title="MarineVerse Marine Data API",
    description=(
        "Unified API for ports, weather, ocean, and vessel data."
    ),
    version=API_VERSION,
)

app.include_router(health_router)
app.include_router(ports_router)
