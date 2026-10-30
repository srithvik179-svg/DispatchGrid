import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.assignment import Assignment
from app.models.job import Job
from app.scheduling.skills import (
    check_technician_skills,
    filter_technicians_by_skills,
    filter_all_jobs_by_skills,
)
from app.scheduling.service import SchedulingService


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


def test_check_technician_skills_single_skill_match():
    """Verify single-skill match when technician possesses the required skill."""
    result = check_technician_skills(
        required_skills=["plumbing"],
        technician_skills=["plumbing", "hvac"],
        technician_id="T16",
        technician_name="Gopal Krishna",
    )
    assert result.is_eligible is True
    assert result.matched_skills == ["plumbing"]
    assert result.missing_skills == []
    assert result.rejection_reason is None
    assert result.has_unsupported_skills is False


def test_check_technician_skills_single_skill_missing():
    """Verify missing skill detection and structured rejection explanation."""
    result = check_technician_skills(
        required_skills=["networking"],
        technician_skills=["electrical", "solar"],
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert result.is_eligible is False
    assert result.matched_skills == []
    assert result.missing_skills == ["networking"]
    assert "Arjun Rao lacks required skill(s): networking" in result.rejection_reason
    assert "holds: electrical, solar" in result.rejection_reason


def test_check_technician_skills_multiple_skills_full_match():
    """Verify multi-skill job requirement where technician possesses every skill."""
    result = check_technician_skills(
        required_skills=["electrical", "cctv"],
        technician_skills=["cctv", "electrical"],
        technician_id="T09",
        technician_name="Imran Khan",
    )
    assert result.is_eligible is True
    assert set(result.matched_skills) == {"electrical", "cctv"}
    assert result.missing_skills == []
    assert result.rejection_reason is None


def test_check_technician_skills_multiple_skills_partial_match():
    """Verify multi-skill job requirement where technician only has a subset of required skills."""
    result = check_technician_skills(
        required_skills=["elevator", "electrical", "hvac"],
        technician_skills=["elevator", "electrical"],
        technician_id="T11",
        technician_name="Vikram Singh",
    )
    assert result.is_eligible is False
    assert set(result.matched_skills) == {"elevator", "electrical"}
    assert result.missing_skills == ["hvac"]
    assert "lacks required skill(s): hvac" in result.rejection_reason


def test_check_technician_skills_unsupported_high_voltage():
    """Verify detection and explicit rejection reason for unsupported high_voltage skill."""
    result = check_technician_skills(
        required_skills=["high_voltage"],
        technician_skills=["electrical", "solar"],
        technician_id="T01",
        technician_name="Arjun Rao",
        unsupported_skills=["high_voltage"],
    )
    assert result.is_eligible is False
    assert result.has_unsupported_skills is True
    assert result.unsupported_skills == ["high_voltage"]
    assert "Job requires unsupported skill(s): high_voltage" in result.rejection_reason


def test_filter_technicians_by_skills_job_001_networking(db_session):
    """Verify JOB-001 (networking) filters down strictly to technicians with networking."""
    service = SchedulingService(db_session)
    cand = service.get_candidates_by_skill("JOB-001")

    assert cand.job_id == "JOB-001"
    assert cand.required_skills == ["networking"]
    assert cand.has_unsupported_skills is False
    assert cand.is_assignable is True

    eligible_ids = {c.id for c in cand.eligible_candidates}
    expected_networking_techs = {"T04", "T08", "T13", "T15", "T19"}
    assert eligible_ids == expected_networking_techs
    assert cand.candidate_count == 5

    # Technicians without networking must be rejected
    rejected_ids = {r.technician_id for r in cand.rejected_candidates}
    assert "T01" in rejected_ids
    assert "T01" in cand.rejection_summary
    assert "networking" in cand.rejection_summary["T01"]


def test_filter_technicians_by_skills_job_014_unsupported_high_voltage(db_session):
    """Verify JOB-014 (high_voltage) has zero candidates and is marked unassignable."""
    service = SchedulingService(db_session)
    cand = service.get_candidates_by_skill("JOB-014")

    assert cand.job_id == "JOB-014"
    assert cand.has_unsupported_skills is True
    assert cand.candidate_count == 0
    assert cand.is_assignable is False
    assert len(cand.eligible_candidates) == 0
    assert "high_voltage" in cand.reason_if_unassignable


def test_filter_technicians_by_skills_multi_skill_jobs(db_session):
    """Verify multi-skill candidate filtering on JOB-026 and JOB-057."""
    service = SchedulingService(db_session)

    # JOB-026 requires electrical + cctv -> only T09 has both
    cand_026 = service.get_candidates_by_skill("JOB-026")
    assert cand_026.candidate_count == 1
    assert cand_026.eligible_candidates[0].id == "T09"
    assert cand_026.is_assignable is True

    # JOB-057 requires elevator + electrical + hvac -> 0 technicians have all 3
    cand_057 = service.get_candidates_by_skill("JOB-057")
    assert cand_057.candidate_count == 0
    assert cand_057.is_assignable is False
    assert "Zero technicians possess all 3 required skills" in cand_057.reason_if_unassignable


def test_filter_all_jobs_by_skills(db_session):
    """Verify filtering all pending jobs correctly flags unassignable jobs."""
    service = SchedulingService(db_session)
    all_cands = service.get_all_skill_candidates()

    assert len(all_cands) >= 100
    assert "JOB-001" in all_cands
    assert "JOB-014" in all_cands
    assert "JOB-057" in all_cands

    assert all_cands["JOB-014"].is_assignable is False
    assert all_cands["JOB-057"].is_assignable is False
    assert all_cands["JOB-001"].is_assignable is True


def test_api_get_skill_candidates(test_client):
    """Test GET /api/v1/scheduling/candidates/skills endpoint."""
    # For a specific job
    resp = test_client.get("/api/v1/scheduling/candidates/skills?job_id=JOB-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == "JOB-001"
    assert data["candidate_count"] == 5
    assert len(data["eligible_candidates"]) == 5

    # For an unsupported skill job
    resp_hv = test_client.get("/api/v1/scheduling/candidates/skills?job_id=JOB-014")
    assert resp_hv.status_code == 200
    data_hv = resp_hv.json()
    assert data_hv["candidate_count"] == 0
    assert data_hv["is_assignable"] is False
    assert data_hv["has_unsupported_skills"] is True

    # For non-existent job
    resp_404 = test_client.get("/api/v1/scheduling/candidates/skills?job_id=NON-EXISTENT")
    assert resp_404.status_code == 404


def test_api_post_filter_custom_skills(test_client):
    """Test POST /api/v1/scheduling/candidates/skills/filter endpoint."""
    payload = {
        "required_skills": ["solar", "electrical"],
        "technician_ids": ["T01", "T02", "T10"],
    }
    resp = test_client.post("/api/v1/scheduling/candidates/skills/filter", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # T01 has electrical + solar, T10 has solar + electrical. T02 has hvac + appliance_repair
    eligible_ids = {c["id"] for c in data["eligible_candidates"]}
    assert eligible_ids == {"T01", "T10"}
    assert data["candidate_count"] == 2
    assert "T02" in data["rejection_summary"]


def test_existing_scheduling_features_unaffected(test_client, db_session):
    """Verify existing scheduling and database assignments remain intact."""
    initial_assignment_count = db_session.query(Assignment).count()
    assert initial_assignment_count == 7

    # Call init run API
    resp = test_client.post("/api/v1/scheduling/runs/init")
    assert resp.status_code == 201
    data = resp.json()
    assert data["existing_assignments_preserved"] is True
    assert data["assigned_jobs_count"] == 7
    assert data["metrics"]["unassignable_skills_jobs_count"] >= 2
    assert "JOB-014" in data["metrics"]["unassignable_skills_jobs"]

    # Verify no database assignments modified
    post_count = db_session.query(Assignment).count()
    assert post_count == 7
