"""
Phase 24: Priority-Aware Optimisation, Scarcity Scoring, and Conflict Resolution Tests.

Verifies:
1. Priority-aware job ordering (Urgent P1 > High P2 > Medium P3 > Low P4).
2. Technician scarcity (fewer qualified technicians prioritized earlier).
3. Window tightness ratio and slack buffer prioritization.
4. Soft SLA target deadlines and hard window boundaries.
5. Deterministic tie-breaking rules.
6. Conflict pair resolution on supplied dataset pairs (JOB-004 vs JOB-083, JOB-093 vs JOB-004, etc.).
7. Candidate assignment comparison avoiding arbitrary dispatch decisions.
8. API endpoints for priority profiles, conflict pair resolution, and prioritized queue.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.technician import Technician
from app.models.job import Job
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.service import SchedulingService
from app.scheduling.priority import (
    calculate_job_priority_profile,
    prioritize_jobs_with_scarcity,
    resolve_competing_jobs,
    compare_candidate_assignments,
)
from app.scheduling.schemas import (
    JobPriorityProfile,
    CompetingJobResolution,
    ConflictPairEvaluationRequest,
)


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


def test_job_priority_profile_calculation(db_session):
    """Verify detailed multi-criteria priority profile computation."""
    service = SchedulingService(db_session)
    job_004 = db_session.query(Job).filter_by(id="JOB-004").first()
    assert job_004 is not None
    technicians = db_session.query(Technician).all()

    profile = calculate_job_priority_profile(
        job=JobResponse.model_validate(job_004),
        technicians=[TechnicianResponse.model_validate(t) for t in technicians],
        unsupported_skills=service.get_unsupported_skills(),
    )

    assert profile.job_id == "JOB-004"
    assert profile.priority == 1
    assert profile.priority_label.lower() == "urgent"
    assert profile.qualified_technicians_count == 5
    assert set(profile.qualified_technician_ids) == {"T02", "T07", "T12", "T14", "T20"}
    assert profile.window_duration_ratio > 0.0
    assert profile.window_slack_minutes >= 0.0
    assert profile.tie_breaker_key.startswith("P1-S05-")


def test_conflict_resolution_tier1_priority_level(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Tier 1: Priority 1 (Urgent) ALWAYS outranks Priority 2 (High).
    Dataset test: JOB-004 (P1, HVAC, Z4) vs JOB-083 (P2, HVAC, Z4).
    Both share identical required skills, zone, and time window.
    """
    service = SchedulingService(db_session)
    resolution = service.resolve_competing_jobs("JOB-004", "JOB-083")

    assert resolution.winner_job_id == "JOB-004"
    assert resolution.loser_job_id == "JOB-083"
    assert resolution.deciding_factor == "PRIORITY_LEVEL"
    assert "outranks Job JOB-083" in resolution.explanation
    assert resolution.job_a_profile.priority == 1
    assert resolution.job_b_profile.priority == 2

    # Reverse argument order must yield identical winner
    reverse_res = service.resolve_competing_jobs("JOB-083", "JOB-004")
    assert reverse_res.winner_job_id == "JOB-004"
    assert reverse_res.loser_job_id == "JOB-083"
    assert reverse_res.deciding_factor == "PRIORITY_LEVEL"


def test_conflict_resolution_tier2_technician_scarcity(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Tier 2: When operational priority is equal, fewer qualified technicians wins.
    Dataset test: JOB-093 (P1, 1 qualified tech: T04) vs JOB-004 (P1, 5 qualified techs).
    """
    service = SchedulingService(db_session)
    resolution = service.resolve_competing_jobs("JOB-093", "JOB-004")

    assert resolution.winner_job_id == "JOB-093"
    assert resolution.loser_job_id == "JOB-004"
    assert resolution.deciding_factor == "TECHNICIAN_SCARCITY"
    assert resolution.job_a_profile.qualified_technicians_count == 1
    assert resolution.job_b_profile.qualified_technicians_count == 5
    assert "higher technician scarcity" in resolution.explanation


def test_conflict_resolution_tier3_window_tightness(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Tier 3: When priority and scarcity are equal, tighter window wins.
    Dataset test: JOB-055 vs JOB-011 (Both P1, both 3 qualified techs).
    JOB-055 has tighter window / less slack.
    """
    service = SchedulingService(db_session)
    resolution = service.resolve_competing_jobs("JOB-055", "JOB-011")

    assert resolution.winner_job_id == "JOB-055"
    assert resolution.loser_job_id == "JOB-011"
    assert resolution.deciding_factor == "WINDOW_TIGHTNESS"
    assert resolution.job_a_profile.window_duration_ratio > resolution.job_b_profile.window_duration_ratio
    assert "tighter scheduling window constraints" in resolution.explanation


def test_conflict_resolution_tier4_sla_deadline(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Tier 4: When priority, scarcity, and tightness are equal, earlier SLA deadline wins.
    Dataset test: JOB-011 vs JOB-039 (Both P1, 3 techs, tightness ~0.67).
    JOB-011 has earlier SLA target.
    """
    service = SchedulingService(db_session)
    resolution = service.resolve_competing_jobs("JOB-011", "JOB-039")

    assert resolution.winner_job_id == "JOB-011"
    assert resolution.loser_job_id == "JOB-039"
    assert resolution.deciding_factor == "SLA_DEADLINE"
    assert resolution.job_a_profile.sla_deadline < resolution.job_b_profile.sla_deadline
    assert "earlier soft SLA deadline" in resolution.explanation


def test_conflict_resolution_tier7_deterministic_tie_breaker(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Tier 7: When all operational constraints and deadlines match, deterministic alphanumeric ID decides.
    Dataset test: JOB-011 vs JOB-032 (Both P1, 3 techs, identical window and SLA).
    JOB-011 wins because 'JOB-011' < 'JOB-032'.
    Dataset test: JOB-048 vs JOB-093 (Both P1, 1 tech, identical window and SLA).
    JOB-048 wins because 'JOB-048' < 'JOB-093'.
    """
    service = SchedulingService(db_session)

    # 1. JOB-011 vs JOB-032
    res_1 = service.resolve_competing_jobs("JOB-011", "JOB-032")
    assert res_1.winner_job_id == "JOB-011"
    assert res_1.loser_job_id == "JOB-032"
    assert res_1.deciding_factor == "DETERMINISTIC_ID"
    assert "deterministic alphanumeric tie-breaker" in res_1.explanation

    # 2. JOB-048 vs JOB-093
    res_2 = service.resolve_competing_jobs("JOB-048", "JOB-093")
    assert res_2.winner_job_id == "JOB-048"
    assert res_2.loser_job_id == "JOB-093"
    assert res_2.deciding_factor == "DETERMINISTIC_ID"


def test_prioritize_jobs_with_scarcity_ordering(db_session):
    """
    Verify complete fleet priority ordering adheres strictly to priority tiers and scarcity.
    """
    service = SchedulingService(db_session)
    inputs = service.load_inputs()

    ordered = prioritize_jobs_with_scarcity(
        jobs=inputs.pending_jobs,
        technicians=inputs.technicians,
        unsupported_skills=service.get_unsupported_skills(),
    )

    assert len(ordered) == len(inputs.pending_jobs)

    # 1. Priority tiers must be monotonically non-decreasing
    priorities = [j.priority for j in ordered]
    assert priorities == sorted(priorities)

    # 2. Urgent jobs (P1) all come before High jobs (P2)
    p1_indices = [idx for idx, p in enumerate(priorities) if p == 1]
    p2_indices = [idx for idx, p in enumerate(priorities) if p == 2]
    assert max(p1_indices) < min(p2_indices)


def test_compare_candidate_assignments(db_session):
    """
    Verify principled candidate assignment comparison eliminates arbitrary technician choices.
    """
    t1 = db_session.query(Technician).filter_by(id="T01").first()
    t2 = db_session.query(Technician).filter_by(id="T02").first()
    mock_tech_a = TechnicianResponse.model_validate(t1)
    mock_tech_b = TechnicianResponse.model_validate(t2)

    # Case 1: Ranking score decides
    cand_1 = {"technician": mock_tech_a, "ranking_score": 10.0, "proposed_start": datetime.now(timezone.utc), "travel_minutes": 15.0}
    cand_2 = {"technician": mock_tech_b, "ranking_score": 25.0, "proposed_start": datetime.now(timezone.utc), "travel_minutes": 10.0}
    w, l, exp = compare_candidate_assignments(cand_1, cand_2)
    assert w["technician"].id == "T01"
    assert "lower objective cost" in exp

    # Case 2: Equal score, earlier start decides
    t_early = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    t_late = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    cand_3 = {"technician": mock_tech_a, "ranking_score": 20.0, "proposed_start": t_early, "travel_minutes": 15.0}
    cand_4 = {"technician": mock_tech_b, "ranking_score": 20.0, "proposed_start": t_late, "travel_minutes": 15.0}
    w, l, exp = compare_candidate_assignments(cand_3, cand_4)
    assert w["technician"].id == "T01"
    assert "earlier dispatch start" in exp

    # Case 3: Equal score and start, lower transit decides
    cand_5 = {"technician": mock_tech_a, "ranking_score": 20.0, "proposed_start": t_early, "travel_minutes": 25.0}
    cand_6 = {"technician": mock_tech_b, "ranking_score": 20.0, "proposed_start": t_early, "travel_minutes": 10.0}
    w, l, exp = compare_candidate_assignments(cand_5, cand_6)
    assert w["technician"].id == "T02"
    assert "requires less transit" in exp

    # Case 4: Complete tie, deterministic technician ID decides
    cand_7 = {"technician": mock_tech_a, "ranking_score": 20.0, "proposed_start": t_early, "travel_minutes": 10.0}
    cand_8 = {"technician": mock_tech_b, "ranking_score": 20.0, "proposed_start": t_early, "travel_minutes": 10.0}
    w, l, exp = compare_candidate_assignments(cand_7, cand_8)
    assert w["technician"].id == "T01"
    assert "Deterministic tie-breaker" in exp


def test_priority_api_endpoints(test_client):
    """Verify FastAPI endpoints for priority profiles and conflict pair arbitration."""
    # 1. GET /jobs/{job_id}/priority-profile
    resp_prof = test_client.get("/api/v1/jobs/JOB-004/priority-profile")
    assert resp_prof.status_code == 200
    pdata = resp_prof.json()
    assert pdata["job_id"] == "JOB-004"
    assert pdata["priority"] == 1
    assert pdata["qualified_technicians_count"] == 5

    # 2. POST /schedule/priority/resolve (JOB-004 vs JOB-083)
    resp_res = test_client.post(
        "/api/v1/schedule/priority/resolve",
        json={"job_id_a": "JOB-004", "job_id_b": "JOB-083"},
    )
    assert resp_res.status_code == 200
    rdata = resp_res.json()
    assert rdata["winner_job_id"] == "JOB-004"
    assert rdata["loser_job_id"] == "JOB-083"
    assert rdata["deciding_factor"] == "PRIORITY_LEVEL"

    # 3. GET /schedule/priority/ordered
    resp_ord = test_client.get("/api/v1/schedule/priority/ordered")
    assert resp_ord.status_code == 200
    odata = resp_ord.json()
    assert len(odata) > 0
    # First job must be Priority 1 Urgent
    assert odata[0]["priority"] == 1

    # 4. Error on non-existent job
    resp_err = test_client.get("/api/v1/jobs/JOB-NONEXISTENT/priority-profile")
    assert resp_err.status_code == 404
