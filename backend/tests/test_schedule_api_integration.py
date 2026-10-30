import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.assignment import Assignment
from app.scheduling.service import SchedulingService


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        # Guarantee database is restored to baseline after tests
        service = SchedulingService(session)
        service.reset_schedule_to_baseline()
        session.close()


@pytest.fixture
def test_client():
    client = TestClient(app)
    yield client
    # Teardown: ensure baseline state
    session = SessionLocal()
    try:
        service = SchedulingService(session)
        service.reset_schedule_to_baseline()
    finally:
        session.close()


def test_get_current_schedule_baseline(test_client, db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Existing assignments are preserved.
    - Assignments are retrievable.
    - Baseline reflects 7 locked/in-progress assignments and 100 unassigned jobs.
    """
    # Test versioned API endpoint
    resp = test_client.get("/api/v1/schedule/current")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_jobs"] == 108
    assert data["assigned_count"] == 7
    assert data["unassigned_count"] == 100
    assert data["technicians_count"] == 20
    assert data["technicians_utilized"] == 6

    # Verify existing assignments are all flagged as is_existing=True
    for assign in data["assignments"]:
        assert assign["is_existing"] is True

    # Test root endpoint alias
    resp_root = test_client.get("/schedule/current")
    assert resp_root.status_code == 200
    assert resp_root.json()["assigned_count"] == 7


def test_post_schedule_generate_and_persistence(test_client, db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Users can trigger scheduling from the interface / API.
    - Generated schedules persist safely.
    - Existing assignments are preserved.
    - Unassigned explanations are visible with diagnostics.
    """
    # 1. Trigger schedule generation with persistence enabled
    payload = {
        "persist": True,
        "mode": "baseline",
        "respect_existing_assignments": True,
    }
    resp = test_client.post("/api/v1/schedule/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["persisted"] is True
    assert data["existing_assignments_preserved"] is True
    assert data["assigned_count"] == 88  # 81 newly assigned + 7 preserved
    assert data["unassigned_count"] == 19
    assert data["technicians_utilized"] == 20
    assert len(data["assignments"]) == 88
    assert len(data["unassigned_jobs"]) == 19

    # 2. Verify database persistence
    total_assignments_in_db = db_session.query(Assignment).count()
    assert total_assignments_in_db == 88
    existing_in_db = db_session.query(Assignment).filter_by(is_existing=True).count()
    assert existing_in_db == 7

    # 3. Verify unassigned jobs contain diagnostic feasibility explanations
    unassigned_by_id = {u["job_id"]: u for u in data["unassigned_jobs"]}

    # JOB-017 in Zone Z6
    assert "JOB-017" in unassigned_by_id
    job_17 = unassigned_by_id["JOB-017"]
    assert job_17["classification"] == "permanently_impossible"
    assert job_17["primary_category"] == "uncovered_zone"
    assert "Z6" in job_17["rejection_summary"]
    assert "Z6" in job_17["actionable_recommendation"]

    # JOB-014 with unsupported skill
    assert "JOB-014" in unassigned_by_id
    job_14 = unassigned_by_id["JOB-014"]
    assert job_14["classification"] == "permanently_impossible"
    assert job_14["primary_category"] == "unsupported_skill"
    assert "high_voltage" in job_14["rejection_summary"]

    # 4. Verify GET /schedule/current now returns the persisted 88 assignments
    curr_resp = test_client.get("/api/v1/schedule/current")
    assert curr_resp.status_code == 200
    curr_data = curr_resp.json()
    assert curr_data["assigned_count"] == 88
    assert curr_data["unassigned_count"] == 19
    assert curr_data["metrics"]["locked_existing_assignments"] == 7
    assert curr_data["metrics"]["scheduled_assignments"] == 81


def test_get_job_assignment_endpoint(test_client, db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Implement GET /jobs/{job_id}/assignment.
    - Assignments are retrievable.
    - Returns assignment details when assigned, or feasibility report when unassigned.
    """
    # Generate schedule first
    test_client.post("/api/v1/schedule/generate", json={"persist": True})

    # 1. Existing assigned job: JOB-101
    resp_101 = test_client.get("/api/v1/jobs/JOB-101/assignment")
    assert resp_101.status_code == 200
    data_101 = resp_101.json()
    assert data_101["job_id"] == "JOB-101"
    assert data_101["is_assigned"] is True
    assert data_101["status"] == "completed"
    assert data_101["assignment"]["technician_id"] == "T03"
    assert data_101["assignment"]["is_existing"] is True

    # 2. Newly scheduled job: JOB-001
    resp_001 = test_client.get("/api/v1/jobs/JOB-001/assignment")
    assert resp_001.status_code == 200
    data_001 = resp_001.json()
    assert data_001["job_id"] == "JOB-001"
    assert data_001["is_assigned"] is True
    assert data_001["status"] == "assigned"
    assert data_001["assignment"]["technician_id"] == "T13"
    assert data_001["assignment"]["is_existing"] is False

    # 3. Unassigned job: JOB-017 (returns 200 with feasibility diagnosis)
    resp_017 = test_client.get("/api/v1/jobs/JOB-017/assignment")
    assert resp_017.status_code == 200
    data_017 = resp_017.json()
    assert data_017["job_id"] == "JOB-017"
    assert data_017["is_assigned"] is False
    assert data_017["feasibility"] is not None
    assert data_017["feasibility"]["classification"] == "permanently_impossible"
    assert data_017["feasibility"]["primary_category"] == "uncovered_zone"

    # 4. Non-existent job
    resp_fake = test_client.get("/api/v1/jobs/JOB-NOTFOUND/assignment")
    assert resp_fake.status_code == 404


def test_get_technician_schedule_endpoint(test_client, db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Implement GET /technicians/{technician_id}/schedule.
    - Returns sequential itinerary with transit times and distance calculations.
    """
    # Generate schedule first
    test_client.post("/api/v1/schedule/generate", json={"persist": True})

    # Test T01 schedule
    resp = test_client.get("/api/v1/technicians/T01/schedule")
    assert resp.status_code == 200
    data = resp.json()

    assert data["technician_id"] == "T01"
    assert data["technician_name"] == "Arjun Rao"
    assert data["total_assigned_jobs"] > 0
    assert data["total_working_minutes"] > 0
    assert data["total_travel_minutes"] > 0
    assert len(data["itinerary"]) == data["total_assigned_jobs"]

    # Verify first stop travel from home depot
    first_stop = data["itinerary"][0]
    assert first_stop["travel_from_previous_minutes"] > 0
    assert first_stop["distance_from_previous_km"] > 0
    assert first_stop["start_time"] is not None
    assert first_stop["end_time"] is not None

    # Test non-existent technician
    resp_fake = test_client.get("/api/v1/technicians/T999/schedule")
    assert resp_fake.status_code == 404


def test_schedule_reset_endpoint(test_client, db_session):
    """Verify schedule reset endpoint clears newly created assignments and restores baseline."""
    # 1. Generate assignments
    test_client.post("/api/v1/schedule/generate", json={"persist": True})
    assert db_session.query(Assignment).count() == 88

    # 2. Reset schedule
    reset_resp = test_client.post("/api/v1/schedule/reset")
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()
    assert reset_data["deleted_assignments"] == 81
    assert reset_data["preserved_existing_assignments"] == 7

    # 3. Verify baseline in DB and via API
    assert db_session.query(Assignment).count() == 7
    curr_resp = test_client.get("/api/v1/schedule/current")
    assert curr_resp.json()["assigned_count"] == 7
    assert curr_resp.json()["unassigned_count"] == 100
