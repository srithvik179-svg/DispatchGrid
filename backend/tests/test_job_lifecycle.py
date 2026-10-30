import pytest
from httpx import AsyncClient
from app.db.session import SessionLocal
from app.models.job import Job
from app.models.job_history import JobStateHistory


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.mark.asyncio
async def test_valid_job_update(client: AsyncClient, db_session):
    """Verify updating editable fields of a pending job."""
    # Create temporary job
    create_res = await client.post(
        "/api/v1/jobs",
        json={
            "id": "JOB-UPDATE-TEST-01",
            "customer_name": "Initial Name",
            "title": "Initial Title",
            "zone_id": "Z1",
            "lat": 12.30,
            "lng": 76.65,
            "priority": 3,
            "duration_minutes": 30,
            "required_skills": ["electrical"],
            "time_window_start": "2026-11-02T10:00:00+05:30",
            "time_window_end": "2026-11-02T12:00:00+05:30",
        },
    )
    assert create_res.status_code == 201

    # Update title and priority
    update_res = await client.patch(
        "/api/v1/jobs/JOB-UPDATE-TEST-01",
        json={
            "title": "Updated Diagnostic Title",
            "priority": 1,
            "duration_minutes": 45,
        },
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["title"] == "Updated Diagnostic Title"
    assert updated_data["priority"] == 1
    assert updated_data["priority_label"] == "urgent"
    assert updated_data["duration_minutes"] == 45

    # Cleanup
    j = db_session.query(Job).filter_by(id="JOB-UPDATE-TEST-01").first()
    if j:
        db_session.delete(j)
        db_session.commit()


@pytest.mark.asyncio
async def test_valid_state_transitions_and_history(client: AsyncClient, db_session):
    """Verify permitted transition chain: pending -> assigned -> in_progress -> completed."""
    test_id = "JOB-TRANSITION-TEST-01"
    create_res = await client.post(
        "/api/v1/jobs",
        json={
            "id": test_id,
            "customer_name": "Transition Customer",
            "title": "Transition Test Job",
            "zone_id": "Z1",
            "lat": 12.30,
            "lng": 76.65,
            "priority": 2,
            "duration_minutes": 30,
            "required_skills": ["electrical"],
            "time_window_start": "2026-11-02T10:00:00+05:30",
            "time_window_end": "2026-11-02T12:00:00+05:30",
        },
    )
    assert create_res.status_code == 201

    # 1. pending -> assigned
    r1 = await client.patch(f"/api/v1/jobs/{test_id}", json={"status": "assigned"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "assigned"

    # 2. assigned -> in_progress
    r2 = await client.patch(f"/api/v1/jobs/{test_id}", json={"status": "in_progress"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "in_progress"

    # 3. in_progress -> completed
    r3 = await client.patch(f"/api/v1/jobs/{test_id}", json={"status": "completed"})
    assert r3.status_code == 200
    assert r3.json()["status"] == "completed"

    # 4. Verify history endpoint records every change
    hist_res = await client.get(f"/api/v1/jobs/{test_id}/history")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) >= 4  # creation + 3 transitions
    statuses = [h["to_status"] for h in history]
    assert "pending" in statuses
    assert "assigned" in statuses
    assert "in_progress" in statuses
    assert "completed" in statuses

    # Cleanup
    j = db_session.query(Job).filter_by(id=test_id).first()
    if j:
        db_session.delete(j)
        db_session.commit()


@pytest.mark.asyncio
async def test_reject_invalid_state_transitions(client: AsyncClient, db_session):
    """Verify invalid transitions are rejected with 400 Bad Request."""
    test_id = "JOB-INVALID-TRANS-01"
    create_res = await client.post(
        "/api/v1/jobs",
        json={
            "id": test_id,
            "customer_name": "Customer",
            "title": "Title",
            "zone_id": "Z1",
            "lat": 12.30,
            "lng": 76.65,
            "priority": 2,
            "duration_minutes": 30,
            "required_skills": ["electrical"],
            "time_window_start": "2026-11-02T10:00:00+05:30",
            "time_window_end": "2026-11-02T12:00:00+05:30",
        },
    )
    assert create_res.status_code == 201

    # pending -> completed directly is invalid
    res_invalid = await client.patch(f"/api/v1/jobs/{test_id}", json={"status": "completed"})
    assert res_invalid.status_code == 400
    assert "Invalid state transition" in res_invalid.json()["detail"]

    # Cleanup
    j = db_session.query(Job).filter_by(id=test_id).first()
    if j:
        db_session.delete(j)
        db_session.commit()


@pytest.mark.asyncio
async def test_prevent_modification_and_cancellation_of_completed_job(client: AsyncClient):
    """Verify completed jobs (e.g. seeded JOB-101) cannot be modified or cancelled."""
    completed_job_id = "JOB-101"

    # Attempt update: fails
    update_res = await client.patch(
        f"/api/v1/jobs/{completed_job_id}",
        json={"title": "Hacked Title on Completed Job"},
    )
    assert update_res.status_code == 400
    assert "terminal state 'completed'" in update_res.json()["detail"]

    # Attempt cancel: fails
    cancel_res = await client.post(
        f"/api/v1/jobs/{completed_job_id}/cancel",
        json={"reason": "Should fail"},
    )
    assert cancel_res.status_code == 400
    assert "Cannot cancel job in 'completed' state" in cancel_res.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_pending_job_persists(client: AsyncClient, db_session):
    """Verify cancelling a pending job marks it cancelled and records history."""
    test_id = "JOB-CANCEL-TEST-01"
    create_res = await client.post(
        "/api/v1/jobs",
        json={
            "id": test_id,
            "customer_name": "Cancel Customer",
            "title": "Job To Be Cancelled",
            "zone_id": "Z1",
            "lat": 12.30,
            "lng": 76.65,
            "priority": 3,
            "duration_minutes": 30,
            "required_skills": ["electrical"],
            "time_window_start": "2026-11-02T10:00:00+05:30",
            "time_window_end": "2026-11-02T12:00:00+05:30",
        },
    )
    assert create_res.status_code == 201

    cancel_res = await client.post(
        f"/api/v1/jobs/{test_id}/cancel",
        json={"reason": "Customer called to cancel appointment"},
    )
    assert cancel_res.status_code == 200
    data = cancel_res.json()
    assert data["status"] == "cancelled"

    # Verify persisted in DB
    db_job = db_session.query(Job).filter_by(id=test_id).first()
    assert db_job.status == "cancelled"

    # Resurrecting cancelled job must be rejected
    resurrect_res = await client.patch(f"/api/v1/jobs/{test_id}", json={"status": "pending"})
    assert resurrect_res.status_code == 400

    # Cleanup
    db_session.delete(db_job)
    db_session.commit()
