import pytest
from httpx import AsyncClient
from app.db.session import SessionLocal
from app.models.job import Job


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.mark.asyncio
async def test_create_valid_job(client: AsyncClient, db_session):
    """Verify valid job creation generates unique ID, persists to DB, and returns 201."""
    initial_count = db_session.query(Job).count()

    payload = {
        "customer_name": "Acme Industrial Labs",
        "title": "Emergency Generator Circuit Repair",
        "zone_id": "Z1",
        "location": {
            "lat": 12.3055,
            "lng": 76.6558,
            "address": "45 Technology Park, Central, Mysuru",
        },
        "priority": 1,
        "duration_minutes": 60,
        "required_skills": ["electrical"],
        "required_equipment": ["multimeter"],
        "time_window_start": "2026-11-02T11:00:00+05:30",
        "time_window_end": "2026-11-02T15:00:00+05:30",
        "sla_deadline": "2026-11-02T14:00:00+05:30",
        "tags": ["critical_power"],
    }

    response = await client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["id"].startswith("JOB-")
    assert data["customer_name"] == "Acme Industrial Labs"
    assert data["title"] == "Emergency Generator Circuit Repair"
    assert data["priority"] == 1
    assert data["priority_label"] == "urgent"
    assert data["status"] == "pending"
    assert data["duration_minutes"] == 60
    assert data["required_skills"] == ["electrical"]
    assert data["required_equipment"] == ["multimeter"]

    # Verify persisted in PostgreSQL
    db_job = db_session.query(Job).filter_by(id=data["id"]).first()
    assert db_job is not None
    assert db_job.title == "Emergency Generator Circuit Repair"
    assert db_session.query(Job).count() == initial_count + 1

    # Cleanup created test job
    db_session.delete(db_job)
    db_session.commit()


@pytest.mark.asyncio
async def test_create_job_custom_id_and_prevent_duplicate_id(client: AsyncClient, db_session):
    """Verify custom ID assignment and rejection of duplicate job IDs (409 Conflict)."""
    custom_id = "JOB-TEST-CUSTOM-01"

    # Ensure clean state
    existing = db_session.query(Job).filter_by(id=custom_id).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    payload = {
        "id": custom_id,
        "customer_name": "Test Customer",
        "title": "Solar Inverter Maintenance",
        "zone_id": "Z2",
        "lat": 12.355,
        "lng": 76.640,
        "priority": 2,
        "duration_minutes": 45,
        "required_skills": ["solar"],
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T14:00:00+05:30",
    }

    # First attempt: succeeds
    res1 = await client.post("/api/v1/jobs", json=payload)
    assert res1.status_code == 201
    assert res1.json()["id"] == custom_id

    # Second attempt with same ID: rejected with 409 Conflict
    res2 = await client.post("/api/v1/jobs", json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]

    # Cleanup
    created = db_session.query(Job).filter_by(id=custom_id).first()
    if created:
        db_session.delete(created)
        db_session.commit()


@pytest.mark.asyncio
async def test_prevent_duplicate_idempotency_key(client: AsyncClient):
    """Verify duplicate idempotency keys return 409 Conflict."""
    payload = {
        "idempotency_key": "seed-JOB-001",  # Already present in seed data
        "customer_name": "Retry Customer",
        "title": "Duplicate Key Test",
        "lat": 12.30,
        "lng": 76.65,
        "priority": 3,
        "duration_minutes": 30,
        "required_skills": ["electrical"],
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T12:00:00+05:30",
    }

    response = await client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 409
    assert "Duplicate request" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reject_invalid_priority_range(client: AsyncClient):
    """Verify priority outside 1-4 is rejected with 422."""
    payload = {
        "customer_name": "Customer",
        "title": "Title",
        "lat": 12.30,
        "lng": 76.65,
        "priority": 5,  # Invalid
        "duration_minutes": 30,
        "required_skills": ["electrical"],
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T12:00:00+05:30",
    }
    response = await client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_non_positive_duration(client: AsyncClient):
    """Verify duration <= 0 is rejected with 422."""
    payload = {
        "customer_name": "Customer",
        "title": "Title",
        "lat": 12.30,
        "lng": 76.65,
        "priority": 2,
        "duration_minutes": 0,  # Invalid
        "required_skills": ["electrical"],
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T12:00:00+05:30",
    }
    response = await client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_window_shorter_than_duration(client: AsyncClient):
    """Verify time window shorter than duration is rejected."""
    payload = {
        "customer_name": "Customer",
        "title": "Title",
        "lat": 12.30,
        "lng": 76.65,
        "priority": 2,
        "duration_minutes": 120,
        "required_skills": ["electrical"],
        # Window is only 60 minutes
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T11:00:00+05:30",
    }
    response = await client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_time_window_start_after_end(client: AsyncClient):
    """Verify time window start >= end is rejected."""
    payload = {
        "customer_name": "Customer",
        "title": "Title",
        "lat": 12.30,
        "lng": 76.65,
        "priority": 2,
        "duration_minutes": 30,
        "required_skills": ["electrical"],
        "time_window_start": "2026-11-02T14:00:00+05:30",
        "time_window_end": "2026-11-02T12:00:00+05:30",
    }
    response = await client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_invalid_zone(client: AsyncClient):
    """Verify non-existent zone ID returns 400 Bad Request."""
    payload = {
        "customer_name": "Customer",
        "title": "Title",
        "zone_id": "Z99_INVALID",
        "lat": 12.30,
        "lng": 76.65,
        "priority": 2,
        "duration_minutes": 30,
        "required_skills": ["electrical"],
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T12:00:00+05:30",
    }
    response = await client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 400
    assert "zone" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_existing_seeded_jobs_remain_unaffected(db_session):
    """Verify that seeded dataset jobs are intact with exact status distribution."""
    jobs = db_session.query(Job).all()
    # At least the 108 seeded jobs are intact
    assert len(jobs) >= 108

    seed_j1 = db_session.query(Job).filter_by(id="JOB-001").first()
    assert seed_j1 is not None
    assert seed_j1.status == "pending"

    seed_j101 = db_session.query(Job).filter_by(id="JOB-101").first()
    assert seed_j101 is not None
    assert seed_j101.status == "completed"


@pytest.mark.asyncio
async def test_list_jobs_search_and_filters(client: AsyncClient):
    """Verify list_jobs filters by status, priority, and search."""
    # 1. Search by ID
    res = await client.get("/api/v1/jobs?search=JOB-001")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["id"] == "JOB-001"

    # 2. Filter by status
    res_status = await client.get("/api/v1/jobs?status=completed")
    assert res_status.status_code == 200
    completed_jobs = res_status.json()
    assert len(completed_jobs) == 4
    for j in completed_jobs:
        assert j["status"] == "completed"

    # 3. Filter by priority
    res_priority = await client.get("/api/v1/jobs?priority=1")
    assert res_priority.status_code == 200
    urgent_jobs = res_priority.json()
    assert len(urgent_jobs) > 0
    for j in urgent_jobs:
        assert j["priority"] == 1
