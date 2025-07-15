from datetime import datetime, UTC
from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    service: str
    version: str


class DetailedHealthResponse(HealthResponse):
    database: str
    redis: str
    uptime_seconds: float


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC),
        service="trademk1-api",
        version="0.1.0"
    )


@router.get("/health/detailed", response_model=DetailedHealthResponse, status_code=status.HTTP_200_OK)
async def health_detailed():
    # TODO: Implement actual health checks for database and redis
    # TODO: Implement actual uptime tracking
    return DetailedHealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC),
        service="trademk1-api",
        version="0.1.0",
        database="healthy",  # TODO: Check actual DB connection
        redis="healthy",     # TODO: Check actual Redis connection
        uptime_seconds=0.0   # TODO: Track actual uptime
    )