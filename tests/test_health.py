import pytest
import httpx
from httpx import AsyncClient
from fastapi import status
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get("/api/health")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "trademk1-api"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_detailed_health_endpoint():
    async with AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get("/api/health/detailed")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["service"] == "trademk1-api"
    assert data["version"] == "0.1.0"
    assert data["postgres"] in ["healthy", "unhealthy"]
    assert data["redis"] == "healthy"
    assert "timestamp" in data
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get("/")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["message"] == "Trademk1 API"
    assert data["version"] == "0.1.0"