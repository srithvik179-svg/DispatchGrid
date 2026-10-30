import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_overview_stats(client: AsyncClient):
    """Verify GET /api/v1/overview returns genuine database counts and records."""
    response = await client.get("/api/v1/overview")
    assert response.status_code == 200
    data = response.json()

    # Total counts
    assert data["total_jobs"] == 108
    assert data["total_technicians"] == 20
    assert data["total_assignments"] == 7
    assert data["total_zones"] == 6
    assert data["simulation_clock"] == "2026-11-02T10:00:00+05:30"

    # Status distribution matches authoritative dataset exactly
    status_counts = data["job_counts_by_status"]
    assert status_counts["pending"] == 100
    assert status_counts["completed"] == 4
    assert status_counts["in_progress"] == 3
    assert status_counts["cancelled"] == 1

    # Priority counts exist
    assert "urgent" in data["job_counts_by_priority"]
    assert "high" in data["job_counts_by_priority"]

    # Preview lists
    assert len(data["jobs"]) > 0
    first_job = data["jobs"][0]
    assert "id" in first_job
    assert "title" in first_job
    assert "status" in first_job
    assert "priority" in first_job

    assert len(data["technicians"]) == 20
    first_tech = data["technicians"][0]
    assert "id" in first_tech
    assert "name" in first_tech
    assert "skills" in first_tech
    assert "equipment" in first_tech
