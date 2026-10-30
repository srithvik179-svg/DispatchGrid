from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.scheduling.service import SchedulingService
from app.scheduling.feasibility import (
    classify_job_feasibility,
    classify_fleet_feasibility,
)
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse, LocationSchema, OvertimeSchema


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


def test_job_14_unsupported_high_voltage(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Jobs requiring unsupported skills are explained accurately as permanently impossible.
    - JOB-014 requires 'high_voltage'.
    """
    service = SchedulingService(db_session)
    report = service.get_job_feasibility(job_id="JOB-014")

    assert report.job_id == "JOB-014"
    assert report.classification == "permanently_impossible"
    assert report.primary_category == "unsupported_skill"
    assert "high_voltage" in report.rejection_summary
    assert report.qualified_technician_count == 0
    assert len(report.technician_rejections) == 20
    # Every technician must be rejected with missing high_voltage
    for tech_rej in report.technician_rejections:
        assert "high_voltage" in tech_rej.missing_skills
    assert "high-voltage" in report.actionable_recommendation.lower() or "high_voltage" in report.actionable_recommendation.lower()


def test_job_17_uncovered_zone_z6(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Z6 jobs are explained using actual zone eligibility.
    - JOB-017 is in Zone Z6 where fleet coverage is 0.
    """
    service = SchedulingService(db_session)
    report = service.get_job_feasibility(job_id="JOB-017")

    assert report.job_id == "JOB-017"
    assert report.classification == "permanently_impossible"
    assert report.primary_category == "uncovered_zone"
    assert "Z6" in report.rejection_summary
    assert report.qualified_technician_count == 0
    assert len(report.technician_rejections) == 20
    # Zone Z6 must be flagged across rejections
    for tech_rej in report.technician_rejections:
        assert "Z6" in tech_rej.explanation
    assert "Z6" in report.actionable_recommendation


def test_job_13_missing_equipment_crane(db_session):
    """
    JOB-013 requires 'crane' which no technician possesses.
    Must be classified as permanently_impossible due to missing equipment.
    """
    service = SchedulingService(db_session)
    report = service.get_job_feasibility(job_id="JOB-013")

    assert report.job_id == "JOB-013"
    assert report.classification == "permanently_impossible"
    assert report.primary_category == "missing_equipment"
    assert "crane" in report.rejection_summary
    assert report.qualified_technician_count == 0
    for tech_rej in report.technician_rejections:
        assert "crane" in tech_rej.missing_equipment
    assert "crane" in report.actionable_recommendation


def test_job_57_missing_skill_combination(db_session):
    """
    JOB-057 requires elevator + electrical + hvac simultaneously.
    While each skill might exist in individual technicians, no technician holds the full combination.
    Must be permanently impossible due to missing_skill combination.
    """
    service = SchedulingService(db_session)
    report = service.get_job_feasibility(job_id="JOB-057")

    assert report.job_id == "JOB-057"
    assert report.classification == "permanently_impossible"
    assert report.primary_category == "missing_skill"
    assert report.qualified_technician_count == 0
    assert len(report.technician_rejections) == 20


def test_job_01_feasible(db_session):
    """
    JOB-001 has qualified technicians and valid time windows.
    Must be classified as feasible.
    """
    service = SchedulingService(db_session)
    report = service.get_job_feasibility(job_id="JOB-001")

    assert report.job_id == "JOB-001"
    assert report.classification == "feasible"
    assert report.primary_category == "none"
    assert report.qualified_technician_count > 0
    assert report.is_structurally_feasible is True
    assert len(report.qualified_technician_ids) > 0


def test_soft_sla_delay_distinguished_from_hard_infeasibility():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Distinguish already-breached soft SLA from hard infeasibility.
    - Soft SLA breach does not cause 'currently_infeasible' or 'permanently_impossible'.
    """
    now = datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc)
    # Service duration: 60 mins. Hard window end: 12:00. Soft SLA deadline: 08:30 (breached if starts at 08:00)
    job = JobResponse(
        id="JOB-TEST-SLA",
        customer_name="Test Customer",
        title="Soft SLA Delayed Job",
        zone_id="Z1",
        lat=40.7128,
        lng=-74.0060,
        address="123 Test St",
        priority=2,
        priority_label="high",
        duration_minutes=60,
        required_skills=["electrical"],
        required_equipment=[],
        time_window_start=datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc),
        time_window_end=datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc),
        sla_deadline=datetime(2026, 2, 2, 8, 30, tzinfo=timezone.utc),
        status="pending",
        created_at=now,
    )

    tech = TechnicianResponse(
        id="T99",
        name="Test Technician",
        home_zone_id="Z1",
        home_lat=40.7128,
        home_lng=-74.0060,
        home_location=LocationSchema(lat=40.7128, lng=-74.0060),
        eligible_zones=["Z1"],
        skills=["electrical"],
        equipment=[],
        shifts=[
            {
                "date": "2026-02-02",
                "start": datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc),
                "end": datetime(2026, 2, 2, 17, 0, tzinfo=timezone.utc),
            }
        ],
        unavailable_periods=[],
        overtime_allowed=False,
        max_overtime_minutes=0,
        overtime=OvertimeSchema(allowed=False, max_minutes_per_shift=0),
    )

    report = classify_job_feasibility(
        job=job,
        technicians=[tech],
        technician_itineraries={"T99": []},
        as_of=now,
    )

    # Must be classified as FEASIBLE because it finishes well before time_window_end (12:00)
    assert report.classification == "feasible"
    assert report.is_sla_delayed is True
    assert report.sla_lateness_minutes > 0
    assert "SLA" in report.rejection_summary or "delayed" in report.rejection_summary.lower()


def test_currently_infeasible_when_schedule_exhausted():
    """
    Temporary constraints are not incorrectly classified as permanent impossibility.
    If technician is qualified for the job (skills, equipment, zone), but shift has ended
    or window expired relative to evaluation clock, it is currently_infeasible.
    """
    as_of = datetime(2026, 2, 2, 18, 0, tzinfo=timezone.utc)
    now = datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc)
    job = JobResponse(
        id="JOB-TEST-EXPIRED",
        customer_name="Test Customer",
        title="Expired Window Job",
        zone_id="Z1",
        lat=40.7128,
        lng=-74.0060,
        address="123 Test St",
        priority=2,
        priority_label="high",
        duration_minutes=60,
        required_skills=["electrical"],
        required_equipment=[],
        time_window_start=datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc),
        time_window_end=datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc),
        sla_deadline=datetime(2026, 2, 2, 11, 0, tzinfo=timezone.utc),
        status="pending",
        created_at=now,
    )

    tech = TechnicianResponse(
        id="T99",
        name="Test Technician",
        home_zone_id="Z1",
        home_lat=40.7128,
        home_lng=-74.0060,
        home_location=LocationSchema(lat=40.7128, lng=-74.0060),
        eligible_zones=["Z1"],
        skills=["electrical"],
        equipment=[],
        shifts=[
            {
                "date": "2026-02-02",
                "start": datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc),
                "end": datetime(2026, 2, 2, 17, 0, tzinfo=timezone.utc),
            }
        ],
        unavailable_periods=[],
        overtime_allowed=False,
        max_overtime_minutes=0,
        overtime=OvertimeSchema(allowed=False, max_minutes_per_shift=0),
    )

    report = classify_job_feasibility(
        job=job,
        technicians=[tech],
        technician_itineraries={"T99": []},
        as_of=as_of,
    )

    assert report.classification == "currently_infeasible"
    assert report.is_structurally_feasible is True
    assert report.actionable_recommendation is not None


def test_fleet_feasibility_summary(db_session):
    """Verify fleet feasibility across the seeded backlog."""
    service = SchedulingService(db_session)
    inputs = service.load_inputs()
    pending_count = len(inputs.pending_jobs)
    fleet_summary = service.get_fleet_feasibility()

    assert fleet_summary.total_jobs == pending_count
    assert fleet_summary.feasible_count > 0
    assert fleet_summary.permanently_impossible_count > 0
    total_categorized = (
        fleet_summary.feasible_count
        + fleet_summary.currently_infeasible_count
        + fleet_summary.permanently_impossible_count
    )
    assert total_categorized == fleet_summary.total_jobs
    assert len(fleet_summary.job_reports) == pending_count


def test_feasibility_api_endpoints(test_client):
    """Verify FastAPI feasibility diagnostic endpoints."""
    # 1. GET /scheduling/feasibility/job/JOB-014
    resp = test_client.get("/api/v1/scheduling/feasibility/job/JOB-014")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == "JOB-014"
    assert data["classification"] == "permanently_impossible"
    assert data["primary_category"] == "unsupported_skill"

    # 2. GET /scheduling/feasibility/job/JOB-017
    resp = test_client.get("/api/v1/scheduling/feasibility/job/JOB-017")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == "JOB-017"
    assert data["classification"] == "permanently_impossible"
    assert data["primary_category"] == "uncovered_zone"

    # 3. GET /scheduling/feasibility/job/NON_EXISTENT
    resp = test_client.get("/api/v1/scheduling/feasibility/job/JOB-NONEXISTENT")
    assert resp.status_code == 404

    # 4. GET /scheduling/feasibility/fleet
    resp = test_client.get("/api/v1/scheduling/feasibility/fleet")
    assert resp.status_code == 200
    fleet_data = resp.json()
    assert fleet_data["total_jobs"] == 100
    assert fleet_data["feasible_count"] > 0
    assert fleet_data["permanently_impossible_count"] > 0

    # 5. POST /scheduling/feasibility/evaluate (single job)
    resp = test_client.post(
        "/api/v1/scheduling/feasibility/evaluate",
        json={"job_id": "JOB-014"},
    )
    assert resp.status_code == 200
    assert resp.json()["classification"] == "permanently_impossible"

    # 6. POST /scheduling/feasibility/evaluate (entire fleet)
    resp = test_client.post(
        "/api/v1/scheduling/feasibility/evaluate",
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["total_jobs"] == 100
