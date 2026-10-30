from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.assignment import Assignment
from app.models.job import Job
from app.models.technician import Technician
from app.scheduling.service import SchedulingService, generate_run_id
from app.scheduling.schemas import SchedulingRunConfig


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client():
    return TestClient(app)


def test_generate_run_id():
    """Verify run ID format, custom prefix, and uniqueness across invocations."""
    run_id_1 = generate_run_id()
    run_id_2 = generate_run_id()

    assert run_id_1.startswith("RUN-")
    assert run_id_2.startswith("RUN-")
    assert run_id_1 != run_id_2
    assert len(run_id_1) > 15

    custom_run = generate_run_id(prefix="RECOVERY")
    assert custom_run.startswith("RECOVERY-")


def test_simulation_clock_and_horizon(db_session):
    """Verify simulation reference clock and planning horizon retrieval."""
    service = SchedulingService(db_session)
    clock = service.get_clock()
    assert clock is not None
    # Authoritative simulation clock in dataset is 2026-11-02 10:00:00+05:30
    assert clock.year == 2026
    assert clock.month == 11
    assert clock.day == 2
    assert clock.hour == 10
    assert clock.minute == 0

    h_start, h_end = service.get_horizon()
    assert h_start < h_end
    assert h_start.day == 2
    assert h_end.day == 4


def test_simulation_clock_override(db_session):
    """Verify clock override functionality."""
    service = SchedulingService(db_session)
    override_time = datetime(2026, 11, 2, 14, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    clock = service.get_clock(override=override_time)
    assert clock == override_time


def test_load_pending_jobs(db_session):
    """Verify loading pending jobs returns 100 jobs sorted by priority."""
    service = SchedulingService(db_session)
    inputs = service.load_inputs()

    assert inputs.pending_jobs_count >= 100
    assert len(inputs.pending_jobs) == inputs.pending_jobs_count

    # Check priority ordering (priority 1 is urgent and should appear before priority 4)
    priorities = [j.priority for j in inputs.pending_jobs]
    assert priorities == sorted(priorities)
    assert all(j.id.startswith("JOB-") for j in inputs.pending_jobs)


def test_load_eligible_technicians(db_session):
    """Verify loading active technicians returns all 20 seeded technicians."""
    service = SchedulingService(db_session)
    inputs = service.load_inputs()

    assert inputs.technicians_count == 20
    assert len(inputs.technicians) == 20
    tech_ids = {t.id for t in inputs.technicians}
    assert "T01" in tech_ids
    assert "T20" in tech_ids


def test_load_existing_assignments(db_session):
    """Verify loading existing assignments returns the 7 locked/in-progress assignments."""
    service = SchedulingService(db_session)
    inputs = service.load_inputs()

    assert inputs.existing_assignments_count == 7
    assert len(inputs.existing_assignments) == 7

    assigned_job_ids = {a.job_id for a in inputs.existing_assignments}
    expected_jobs = {"JOB-101", "JOB-102", "JOB-103", "JOB-104", "JOB-105", "JOB-106", "JOB-107"}
    assert assigned_job_ids == expected_jobs

    for a in inputs.existing_assignments:
        assert a.is_existing is True
        assert a.technician_id.startswith("T")
        assert a.job_title is not None
        assert a.technician_name is not None


def test_initialize_scheduling_run_preserves_assignments_and_leaves_db_unchanged(db_session):
    """
    Verify initialize_run preserves existing assignments, flags them as is_existing=True,
    leaves pending jobs in unassigned list, and strictly leaves database records intact.
    """
    initial_assignment_count = db_session.query(Assignment).count()
    initial_job_count = db_session.query(Job).count()

    service = SchedulingService(db_session)
    result = service.initialize_run()

    assert result.run_id.startswith("RUN-")
    assert result.status == "initialized"
    assert result.existing_assignments_preserved is True
    assert result.assigned_jobs_count == 7
    assert len(result.assignments) == 7
    assert result.unassigned_jobs_count >= 100
    assert len(result.unassigned_jobs) == result.unassigned_jobs_count

    # Check preserved assignments details
    for plan in result.assignments:
        assert plan.is_existing is True
        assert plan.job_id in {"JOB-101", "JOB-102", "JOB-103", "JOB-104", "JOB-105", "JOB-106", "JOB-107"}
        assert plan.details["technician_name"] is not None

    # CRITICAL ACCEPTANCE CHECK: No assignments or jobs were added or removed from PostgreSQL
    post_assignment_count = db_session.query(Assignment).count()
    post_job_count = db_session.query(Job).count()
    assert post_assignment_count == initial_assignment_count
    assert post_job_count == initial_job_count


def test_api_scheduling_clock(test_client):
    """Test GET /api/v1/scheduling/clock."""
    response = test_client.get("/api/v1/scheduling/clock")
    assert response.status_code == 200
    data = response.json()
    assert "as_of" in data
    assert "horizon_start" in data
    assert "horizon_end" in data
    assert data["time_zone"] == "Asia/Kolkata (+05:30)"


def test_api_scheduling_inputs(test_client):
    """Test GET /api/v1/scheduling/inputs."""
    response = test_client.get("/api/v1/scheduling/inputs")
    assert response.status_code == 200
    data = response.json()
    assert data["pending_jobs_count"] >= 100
    assert data["technicians_count"] == 20
    assert data["existing_assignments_count"] == 7
    assert len(data["pending_jobs"]) == data["pending_jobs_count"]
    assert len(data["technicians"]) == 20
    assert len(data["existing_assignments"]) == 7


def test_api_scheduling_run_init(test_client):
    """Test POST /api/v1/scheduling/runs/init."""
    payload = {
        "mode": "baseline",
        "respect_existing_assignments": True,
    }
    response = test_client.post("/api/v1/scheduling/runs/init", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["run_id"].startswith("RUN-")
    assert data["status"] == "initialized"
    assert data["existing_assignments_preserved"] is True
    assert data["assigned_jobs_count"] == 7
    assert data["unassigned_jobs_count"] >= 100
    assert len(data["assignments"]) == 7
    assert data["metrics"]["locked_assignments_count"] == 7
