import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_root_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data
    assert "version" in data
    assert "simulation_clock" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_v1_endpoint(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "DispatchGrid"
    assert data["health_url"] == "/health"
