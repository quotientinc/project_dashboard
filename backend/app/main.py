"""
FastAPI application entry point.

Configures CORS, mounts route modules under /api/v1, and optionally serves
the Vue frontend's built static files at the root path.
"""
import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logger import setup_logging
from app.api.routes import (
    allocations,
    analytics,
    data_management,
    employees,
    expenses,
    months,
    projects,
    time_entries,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
setup_logging(log_level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler — logs full tracebacks for unhandled exceptions
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# API v1 routes
# ---------------------------------------------------------------------------
API_PREFIX = "/api/v1"

app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(employees.router, prefix=API_PREFIX)
app.include_router(allocations.router, prefix=API_PREFIX)
app.include_router(time_entries.router, prefix=API_PREFIX)
app.include_router(expenses.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(data_management.router, prefix=API_PREFIX)
app.include_router(months.router, prefix=API_PREFIX)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static file serving for production (Vue frontend build)
# ---------------------------------------------------------------------------
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
    logger.info("Serving frontend static files from %s", _FRONTEND_DIST)
else:
    logger.info(
        "Frontend dist directory not found at %s -- static file serving disabled. "
        "API is available at %s/",
        _FRONTEND_DIST,
        API_PREFIX,
    )
