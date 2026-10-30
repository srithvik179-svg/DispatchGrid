"""
Phase 27: Schedule Stability and Assignment Preservation Tests.

Verifies:
1. Identification and strict protection of completed and in-progress work.
2. Prevention and detection of illegal mutations to protected assignments.
3. Measurable penalties for unnecessary changes (time shifts, reassignments, dropped jobs).
4. Principled comparison between old (baseline) and new (candidate) assignments.
5. Preservation of valid unaffected assignments during recalculation.
6. Downstream recalculation on affected technicians with zero hard constraint violations.
7. REST API endpoints for stability metrics, schedule comparison, and recalculation.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.technician import Technician
from app.models.job import Job
from app.models.assignment import Assignment
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.service import SchedulingService
from app.scheduling.algorithm import run_deterministic_initial_scheduler
from app.scheduling.stability import (
    is_assignment_protected,
    compare_schedules,
    recalculate_stable_schedule,
)
from app.scheduling.schemas import (
    AssignedJobPlan,
    AssignmentChangeDetail,
    ScheduleStabilityMetrics,
    StabilityRecalculationResult,
)

IST = timezone(timedelta(hours=5, minutes=30))


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


def test_identify_and_protect_completed_and_in_progress_work(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Identify existing assignments.
    - Completed and in-progress work is protected.
    - Illegal modifications to protected assignments are strictly flagged.
    """
    asgs = db_session.query(Assignment).all()
    assert len(asgs) == 7

    completed_asgs = [a for a in asgs if a.status == "completed"]
    in_prog_asgs = [a for a in asgs if a.status == "in_progress"]
    assert len(completed_asgs) == 4  # JOB-101, JOB-102, JOB-104, JOB-106
    assert len(in_prog_asgs) == 3   # JOB-103, JOB-105, JOB-107

    # 1. Protection helper check
    for a in completed_asgs:
        assert is_assignment_protected(a.status) is True
    for a in in_prog_asgs:
        assert is_assignment_protected(a.status) is True
    assert is_assignment_protected("scheduled") is False
    assert is_assignment_protected("pending") is False

    # 2. Baseline plans
    baseline_plans = [
        AssignedJobPlan(
            job_id=a.job_id,
            technician_id=a.technician_id,
            scheduled_start=a.start_time,
            scheduled_end=a.end_time,
            travel_time_minutes=0.0,
            is_existing=a.is_existing,
            status=a.status,
        )
        for a in asgs
    ]

    # Valid candidate with identical assignments -> protection satisfied
    candidate_valid = [p.model_copy() for p in baseline_plans]
    changes_valid, metrics_valid = compare_schedules(baseline_plans, candidate_valid)
    assert metrics_valid.is_protection_violated is False
    assert metrics_valid.completed_protected_count == 4
    assert metrics_valid.completed_preserved_count == 4
    assert metrics_valid.in_progress_protected_count == 3
    assert metrics_valid.in_progress_preserved_count == 3
    assert metrics_valid.unchanged_count == 7
    assert metrics_valid.unchanged_percentage == 100.0
    assert metrics_valid.total_churn_penalty == 0.0

    # 3. Illegal modification attempt: reassign completed job JOB-101
    candidate_illegal_reassign = [p.model_copy() for p in baseline_plans]
    job_101_plan = next(p for p in candidate_illegal_reassign if p.job_id == "JOB-101")
    job_101_plan.technician_id = "T99"

    changes_illegal, metrics_illegal = compare_schedules(baseline_plans, candidate_illegal_reassign)
    assert metrics_illegal.is_protection_violated is True
    assert len(metrics_illegal.violations) > 0
    assert any("ILLEGAL MUTATION" in v and "JOB-101" in v for v in metrics_illegal.violations)
    assert metrics_illegal.stability_score == 0.0

    # 4. Illegal modification attempt: shift in-progress job JOB-103
    candidate_illegal_shift = [p.model_copy() for p in baseline_plans]
    job_103_plan = next(p for p in candidate_illegal_shift if p.job_id == "JOB-103")
    job_103_plan.scheduled_start += timedelta(minutes=45)

    changes_shift, metrics_shift = compare_schedules(baseline_plans, candidate_illegal_shift)
    assert metrics_shift.is_protection_violated is True
    assert any("ILLEGAL MUTATION" in v and "JOB-103" in v for v in metrics_shift.violations)


def test_penalize_unnecessary_changes_to_future_assignments():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Penalise unnecessary changes to future assignments.
    - Change penalties are measurable.
    """
    start_dt = datetime(2026, 11, 2, 10, 0, tzinfo=IST)
    end_dt = datetime(2026, 11, 2, 11, 0, tzinfo=IST)

    baseline = [
        AssignedJobPlan(
            job_id="JOB-FUT-1",
            technician_id="T01",
            scheduled_start=start_dt,
            scheduled_end=end_dt,
            status="scheduled",
        ),
        AssignedJobPlan(
            job_id="JOB-FUT-2",
            technician_id="T01",
            scheduled_start=start_dt + timedelta(hours=2),
            scheduled_end=end_dt + timedelta(hours=2),
            status="scheduled",
        ),
        AssignedJobPlan(
            job_id="JOB-FUT-3",
            technician_id="T02",
            scheduled_start=start_dt,
            scheduled_end=end_dt,
            status="scheduled",
        ),
    ]

    # Candidate with:
    # JOB-FUT-1: Unchanged
    # JOB-FUT-2: Time shifted by 30 mins
    # JOB-FUT-3: Reassigned to T03
    # JOB-FUT-4: Newly added
    candidate = [
        AssignedJobPlan(
            job_id="JOB-FUT-1",
            technician_id="T01",
            scheduled_start=start_dt,
            scheduled_end=end_dt,
            status="scheduled",
        ),
        AssignedJobPlan(
            job_id="JOB-FUT-2",
            technician_id="T01",
            scheduled_start=start_dt + timedelta(hours=2, minutes=30),
            scheduled_end=end_dt + timedelta(hours=2, minutes=30),
            status="scheduled",
        ),
        AssignedJobPlan(
            job_id="JOB-FUT-3",
            technician_id="T03",  # Reassigned
            scheduled_start=start_dt,
            scheduled_end=end_dt,
            status="scheduled",
        ),
        AssignedJobPlan(
            job_id="JOB-FUT-4",  # Newly dispatched
            technician_id="T04",
            scheduled_start=start_dt,
            scheduled_end=end_dt,
            status="scheduled",
        ),
    ]

    changes, metrics = compare_schedules(
        baseline_assignments=baseline,
        candidate_assignments=candidate,
        w_reassign=250.0,
        w_shift_per_hour=30.0,
        w_unassign=500.0,
    )

    change_by_job = {c.job_id: c for c in changes}
    assert change_by_job["JOB-FUT-1"].change_type == "UNCHANGED"
    assert change_by_job["JOB-FUT-1"].penalty == 0.0

    assert change_by_job["JOB-FUT-2"].change_type == "TIME_SHIFTED"
    assert change_by_job["JOB-FUT-2"].time_shift_minutes == 30.0
    assert change_by_job["JOB-FUT-2"].penalty == 15.0  # (30/60) * 30.0 = 15.0

    assert change_by_job["JOB-FUT-3"].change_type == "REASSIGNED"
    assert change_by_job["JOB-FUT-3"].penalty == 250.0

    assert change_by_job["JOB-FUT-4"].change_type == "NEWLY_ASSIGNED"
    assert change_by_job["JOB-FUT-4"].penalty == 0.0

    assert metrics.unchanged_count == 1
    assert metrics.time_shifted_count == 1
    assert metrics.reassigned_count == 1
    assert metrics.newly_assigned_count == 1
    assert metrics.total_churn_penalty == 265.0  # 15.0 + 250.0


def test_preserve_valid_unaffected_assignments_during_recalculation(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Unaffected assignments remain unchanged.
    - Necessary changes are permitted.
    - Recalculate affected schedules when necessary.
    - Preserve valid assignments where practical.
    """
    service = SchedulingService(db_session)
    as_of = service.get_clock()
    inputs = service.load_inputs()
    initial_res = run_deterministic_initial_scheduler(inputs)

    jobs = [JobResponse.model_validate(j) for j in db_session.query(Job).all()]
    techs = [TechnicianResponse.model_validate(t) for t in db_session.query(Technician).all()]

    # Select a job on T10 to disrupt: JOB-032
    # Baseline assignments for T10: JOB-107 (in-progress), JOB-037, JOB-032, JOB-065
    t10_jobs = [p.job_id for p in initial_res.assignments if p.technician_id == "T10"]
    assert "JOB-032" in t10_jobs

    # Recalculate with a 20-minute delay on JOB-032
    recalc_result = recalculate_stable_schedule(
        baseline_assignments=initial_res.assignments,
        technicians=techs,
        jobs=jobs,
        as_of=as_of,
        disrupted_technician_id="T10",
        disrupted_job_id="JOB-032",
        delay_minutes=20,
    )

    assert recalc_result.is_feasible is True
    assert recalc_result.hard_violations_count == 0

    # 1. Unaffected technicians (e.g. T01, T02, T03, ...) remain 100% UNCHANGED
    baseline_lookup = {p.job_id: p for p in initial_res.assignments}
    for p in recalc_result.assignments:
        if p.technician_id != "T10":
            base = baseline_lookup[p.job_id]
            assert p.technician_id == base.technician_id
            assert p.scheduled_start == base.scheduled_start
            assert p.scheduled_end == base.scheduled_end

    # 2. Completed/In-progress work on T10 (JOB-107) remains 100% PRESERVED
    p_107 = next(p for p in recalc_result.assignments if p.job_id == "JOB-107")
    base_107 = baseline_lookup["JOB-107"]
    assert p_107.scheduled_start == base_107.scheduled_start
    assert p_107.scheduled_end == base_107.scheduled_end

    # 3. Affected job JOB-032 was delayed by exactly 20 minutes
    p_032 = next(p for p in recalc_result.assignments if p.job_id == "JOB-032")
    base_032 = baseline_lookup["JOB-032"]
    assert p_032.scheduled_start == base_032.scheduled_start + timedelta(minutes=20)

    # 4. High stability score and measured stability metrics
    metrics = recalc_result.stability_metrics
    assert metrics.unchanged_count >= 80  # 83 of 88 jobs completely untouched
    assert metrics.unchanged_percentage >= 90.0
    assert metrics.stability_score >= 90.0
    assert metrics.is_protection_violated is False


def test_stability_rest_api_endpoints(test_client):
    """
    ACCEPTANCE CRITERIA:
    - Endpoints respond with valid schemas and accurate stability metrics.
    """
    # 1. GET /api/v1/schedule/stability
    resp_get = test_client.get("/api/v1/schedule/stability")
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert "stability_metrics" in data_get
    assert "assignment_changes" in data_get
    metrics = data_get["stability_metrics"]
    assert metrics["completed_protected_count"] == 4
    assert metrics["completed_preserved_count"] == 4
    assert metrics["in_progress_protected_count"] == 3
    assert metrics["in_progress_preserved_count"] == 3
    assert metrics["is_protection_violated"] is False

    # 2. POST /api/v1/schedule/stability/compare
    resp_compare = test_client.post(
        "/api/v1/schedule/stability/compare",
        json={"w_reassign": 300.0, "w_shift_per_hour": 50.0},
    )
    assert resp_compare.status_code == 200
    data_compare = resp_compare.json()
    assert "stability_metrics" in data_compare

    # 3. POST /api/v1/schedule/stability/recalculate
    resp_recalc = test_client.post(
        "/api/v1/schedule/stability/recalculate",
        json={
            "disrupted_technician_id": "T10",
            "disrupted_job_id": "JOB-032",
            "delay_minutes": 15,
            "persist": False,
        },
    )
    assert resp_recalc.status_code == 200
    data_recalc = resp_recalc.json()
    assert data_recalc["is_feasible"] is True
    assert data_recalc["hard_violations_count"] == 0
    assert "JOB-032" in data_recalc["affected_jobs"]
    assert len(data_recalc["preserved_jobs"]) > 80
    assert data_recalc["stability_metrics"]["is_protection_violated"] is False
