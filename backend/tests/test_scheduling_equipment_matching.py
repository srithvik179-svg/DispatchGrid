import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.assignment import Assignment
from app.scheduling.equipment import (
    check_technician_equipment,
    check_technician_qualification,
    filter_candidates_for_job,
    filter_all_jobs_candidates,
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


def test_check_technician_equipment_single_item_match():
    """Verify single equipment match when technician kit contains the required item."""
    result = check_technician_equipment(
        required_equipment=["multimeter"],
        technician_equipment=["multimeter", "ladder"],
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert result.is_eligible is True
    assert result.matched_equipment == ["multimeter"]
    assert result.missing_equipment == []
    assert result.rejection_reason is None
    assert result.has_unsupported_equipment is False


def test_check_technician_equipment_single_item_missing():
    """Verify missing equipment detection and structured rejection message."""
    result = check_technician_equipment(
        required_equipment=["fiber_splicer"],
        technician_equipment=["ladder"],
        technician_id="T15",
        technician_name="Farah Sheikh",
    )
    assert result.is_eligible is False
    assert result.matched_equipment == []
    assert result.missing_equipment == ["fiber_splicer"]
    assert "Farah Sheikh lacks required equipment: fiber_splicer" in result.rejection_reason
    assert "onboard kit: ladder" in result.rejection_reason


def test_check_technician_equipment_multiple_items_full_match():
    """Verify multi-equipment requirement where technician kit contains all required items."""
    result = check_technician_equipment(
        required_equipment=["multimeter", "ladder"],
        technician_equipment=["ladder", "multimeter"],
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert result.is_eligible is True
    assert set(result.matched_equipment) == {"multimeter", "ladder"}
    assert result.missing_equipment == []
    assert result.rejection_reason is None


def test_check_technician_equipment_multiple_items_partial_match():
    """Verify multi-equipment requirement where technician kit contains only a subset of required items."""
    result = check_technician_equipment(
        required_equipment=["multimeter", "ladder"],
        technician_equipment=["multimeter"],
        technician_id="T05",
        technician_name="Suresh Kumar",
    )
    assert result.is_eligible is False
    assert result.matched_equipment == ["multimeter"]
    assert result.missing_equipment == ["ladder"]
    assert "Suresh Kumar lacks required equipment: ladder" in result.rejection_reason
    assert "onboard kit: multimeter" in result.rejection_reason


def test_check_technician_equipment_unsupported_fleet_item():
    """Verify handling of equipment items missing from the fleet inventory (e.g. crane)."""
    result = check_technician_equipment(
        required_equipment=["crane"],
        technician_equipment=["multimeter", "ladder"],
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert result.is_eligible is False
    assert result.has_unsupported_equipment is True
    assert result.unsupported_equipment == ["crane"]
    assert "Job requires equipment: crane" in result.rejection_reason


def test_check_technician_qualification_distinguishes_failures():
    """
    CRITICAL ACCEPTANCE TEST:
    Verify that skill failures and equipment failures are independently distinguishable.
    """
    # 1. Matching skill AND matching equipment -> Qualified
    q_both_pass = check_technician_qualification(
        required_skills=["networking"],
        required_equipment=["fiber_splicer"],
        technician_skills=["networking", "cctv"],
        technician_equipment=["fiber_splicer", "ladder"],
        technician_id="T04",
        technician_name="Divya Shetty",
    )
    assert q_both_pass.is_eligible is True
    assert q_both_pass.skill_eligible is True
    assert q_both_pass.equipment_eligible is True
    assert q_both_pass.failure_categories == []
    assert q_both_pass.combined_rejection_reason is None

    # 2. Matching skill BUT missing equipment -> Equipment failure only
    q_skill_only = check_technician_qualification(
        required_skills=["networking"],
        required_equipment=["fiber_splicer"],
        technician_skills=["networking"],
        technician_equipment=[],
        technician_id="T08",
        technician_name="Priya Menon",
    )
    assert q_skill_only.is_eligible is False
    assert q_skill_only.skill_eligible is True
    assert q_skill_only.equipment_eligible is False
    assert q_skill_only.failure_categories == ["equipment"]
    assert q_skill_only.missing_skills == []
    assert q_skill_only.missing_equipment == ["fiber_splicer"]
    assert "lacks required equipment: fiber_splicer" in q_skill_only.combined_rejection_reason
    assert "lacks required skill" not in q_skill_only.combined_rejection_reason

    # 3. Missing skill BUT matching equipment -> Skill failure only
    q_equip_only = check_technician_qualification(
        required_skills=["hvac"],
        required_equipment=["multimeter"],
        technician_skills=["electrical"],
        technician_equipment=["multimeter"],
        technician_id="T05",
        technician_name="Suresh Kumar",
    )
    assert q_equip_only.is_eligible is False
    assert q_equip_only.skill_eligible is False
    assert q_equip_only.equipment_eligible is True
    assert q_equip_only.failure_categories == ["skills"]
    assert q_equip_only.missing_skills == ["hvac"]
    assert q_equip_only.missing_equipment == []
    assert "lacks required skill(s): hvac" in q_equip_only.combined_rejection_reason
    assert "lacks required equipment" not in q_equip_only.combined_rejection_reason

    # 4. Missing skill AND missing equipment -> Both failure categories
    q_both_fail = check_technician_qualification(
        required_skills=["hvac"],
        required_equipment=["fiber_splicer"],
        technician_skills=["plumbing"],
        technician_equipment=["pipe_wrench"],
        technician_id="T03",
        technician_name="Karthik Gowda",
    )
    assert q_both_fail.is_eligible is False
    assert q_both_fail.skill_eligible is False
    assert q_both_fail.equipment_eligible is False
    assert set(q_both_fail.failure_categories) == {"skills", "equipment"}
    assert "lacks required skill(s): hvac" in q_both_fail.combined_rejection_reason
    assert "lacks required equipment: fiber_splicer" in q_both_fail.combined_rejection_reason


def test_filter_candidates_for_job_001_skill_and_equipment_filtering(db_session):
    """
    Verify JOB-001 (networking + fiber_splicer):
    - 5 technicians have networking skill
    - Only 2 technicians (T04, T13) have both networking skill AND fiber_splicer
    - 3 technicians (T08, T15, T19) have matching skill but lack equipment
    """
    service = SchedulingService(db_session)
    evaluation = service.get_candidates_for_job("JOB-001")

    assert evaluation.job_id == "JOB-001"
    assert evaluation.required_skills == ["networking"]
    assert evaluation.required_equipment == ["fiber_splicer"]
    assert evaluation.is_assignable is True
    assert evaluation.candidate_count == 2

    eligible_ids = {c.id for c in evaluation.eligible_candidates}
    assert eligible_ids == {"T04", "T13"}

    # Technicians with matching skill but missing equipment
    assert set(evaluation.skill_only_matching_candidates) == {"T08", "T15", "T19"}

    # Rejection summary distinguishes failure reasons
    assert "lacks required equipment: fiber_splicer" in evaluation.rejection_summary["T08"]
    assert "lacks required skill" not in evaluation.rejection_summary["T08"]


def test_filter_candidates_for_job_013_crane_unsupported(db_session):
    """
    Verify JOB-013 (electrical + crane):
    - crane is not present in any technician kit
    - 7 technicians possess the electrical skill
    - None possess crane -> candidate_count == 0, is_assignable == False
    """
    service = SchedulingService(db_session)
    evaluation = service.get_candidates_for_job("JOB-013")

    assert evaluation.job_id == "JOB-013"
    assert evaluation.required_skills == ["electrical"]
    assert evaluation.required_equipment == ["crane"]
    assert evaluation.candidate_count == 0
    assert evaluation.is_assignable is False
    assert evaluation.has_unsupported_requirements is True
    assert "crane" in evaluation.unsupported_requirements
    assert len(evaluation.skill_only_matching_candidates) == 7
    assert "crane" in evaluation.reason_if_unassignable


def test_filter_all_jobs_candidates(db_session):
    """Verify combined evaluation across all 100 pending jobs."""
    service = SchedulingService(db_session)
    all_evals = service.get_all_job_candidates()

    assert len(all_evals) >= 100
    assert "JOB-001" in all_evals
    assert "JOB-013" in all_evals
    assert "JOB-014" in all_evals

    assert all_evals["JOB-001"].is_assignable is True
    assert all_evals["JOB-013"].is_assignable is False
    assert all_evals["JOB-014"].is_assignable is False


def test_api_get_job_candidates(test_client):
    """Test GET /api/v1/scheduling/candidates endpoint."""
    resp = test_client.get("/api/v1/scheduling/candidates?job_id=JOB-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == "JOB-001"
    assert data["candidate_count"] == 2
    assert len(data["eligible_candidates"]) == 2
    assert set(data["skill_only_matching_candidates"]) == {"T08", "T15", "T19"}

    # Non-existent job
    resp_404 = test_client.get("/api/v1/scheduling/candidates?job_id=JOB-999")
    assert resp_404.status_code == 404


def test_api_post_combined_qualification_filter(test_client):
    """Test POST /api/v1/scheduling/candidates/filter endpoint."""
    payload = {
        "required_skills": ["electrical"],
        "required_equipment": ["multimeter", "ladder"],
        "technician_ids": ["T01", "T05"],
    }
    resp = test_client.post("/api/v1/scheduling/candidates/filter", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # T01 has electrical + [ladder, multimeter] -> eligible
    # T05 has electrical + [multimeter] -> lacks ladder
    assert data["candidate_count"] == 1
    assert data["eligible_candidates"][0]["id"] == "T01"
    assert "T05" in data["skill_only_matching_candidates"]
    assert "T05" in data["rejection_summary"]
    assert "lacks required equipment: ladder" in data["rejection_summary"]["T05"]


def test_existing_scheduling_features_unaffected(test_client, db_session):
    """Verify pre-existing assignments and run initialization remain completely intact."""
    initial_assignment_count = db_session.query(Assignment).count()
    assert initial_assignment_count == 7

    resp = test_client.post("/api/v1/scheduling/runs/init")
    assert resp.status_code == 201
    data = resp.json()
    assert data["existing_assignments_preserved"] is True
    assert data["assigned_jobs_count"] == 7
    assert "fleet_equipment_inventory" in data["metrics"]
    assert "crane" not in data["metrics"]["fleet_equipment_inventory"]

    post_count = db_session.query(Assignment).count()
    assert post_count == initial_assignment_count
