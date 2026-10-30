from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import settings
from app.db.session import check_db_health

router = APIRouter()


class DatabaseHealth(BaseModel):
    status: str
    database: str
    engine: str
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    simulation_clock: str
    database: DatabaseHealth
    timestamp: str


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def get_health() -> HealthResponse:
    """Return application and database health status."""
    db_health = check_db_health()
    overall_status = "ok" if db_health["status"] == "connected" else "degraded"
    
    return HealthResponse(
        status=overall_status,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        simulation_clock=settings.SIMULATION_CLOCK_DEFAULT,
        database=DatabaseHealth(**db_health),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/health/db", response_model=DatabaseHealth, tags=["Health"])
def get_database_health() -> DatabaseHealth:
    """Dedicated database connection health check."""
    return DatabaseHealth(**check_db_health())
