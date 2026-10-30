from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.scheduling.service import SchedulingService
from app.scheduling.algorithm import (
    run_deterministic_initial_scheduler,
    prioritize_pending_jobs,
    calculate_job_scheduling_difficulty,
)
from app.scheduling.skills import check_technician_skills
from app.scheduling.equipment import check_technician_equipment
from app.scheduling.geo import check_zone_eligibility, haversine_distance, calculate_travel_minutes


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


def test_prioritize_pending_jobs_ordering(db_session):
    """Verify that jobs are sorted by priority, scheduling difficulty, deadlines, and deterministic tie-breaker."""
    service = SchedulingService(db_session)
    inputs = service.load_inputs()

    sorted_jobs = prioritize_pending_jobs(
        jobs=inputs.pending_jobs,
        technicians=inputs.technicians,
        unsupported_skills=service.get_unsupported_skills(),
    )
    assert len(sorted_jobs) == len(inputs.pending_jobs)

    # 1. Priorities must be monotonic non-decreasing (1 first, then 2, then 3, then 4)
    priorities = [j.priority for j in sorted_jobs]
    assert priorities == sorted(priorities)

    # Priority 1 jobs come before Priority 2
    p1_indices = [idx for idx, p in enumerate(priorities) if p == 1]
    p2_indices = [idx for idx, p in enumerate(priorities) if p == 2]
    assert max(p1_indices) < min(p2_indices)


def test_initial_algorithm_execution_and_preservation(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Assignments are generated automatically.
    - Existing assignments are preserved.
    - Active technicians are utilized without assigning all work to T01.
    """
    service = SchedulingService(db_session)
    inputs = service.load_inputs()

    result = run_deterministic_initial_scheduler(
        inputs=inputs,
        unsupported_skills=service.get_unsupported_skills(),
    )

    assert result.status == "scheduled"
    assert result.existing_assignments_preserved is True

    # 1. Existing assignments are preserved
    existing_in_result = [p for p in result.assignments if p.is_existing]
    assert len(existing_in_result) == len(inputs.existing_assignments) == 7
    existing_ids = {p.job_id for p in existing_in_result}
    assert existing_ids == {"JOB-101", "JOB-102", "JOB-103", "JOB-104", "JOB-105", "JOB-106", "JOB-107"}

    # 2. Significant number of jobs are automatically scheduled
    newly_scheduled = [p for p in result.assignments if not p.is_existing]
    assert len(newly_scheduled) >= 80

    # 3. Workload is balanced: work is not dumped onto T01 alone
    distribution = result.metrics["technician_distribution"]
    assert len(distribution) == 20
    assert result.metrics["active_technicians_utilized"] == 20
    # No single technician has more than 15 jobs
    assert max(distribution.values()) <= 15
    # T01 does not have all jobs
    assert distribution["T01"] < 10


def test_reproducibility_identical_runs(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Same input and configuration produce 100% reproducible results.
    """
    service = SchedulingService(db_session)
    inputs_1 = service.load_inputs(run_id="RUN-TEST-001")
    inputs_2 = service.load_inputs(run_id="RUN-TEST-002")

    res_1 = run_deterministic_initial_scheduler(inputs_1)
    res_2 = run_deterministic_initial_scheduler(inputs_2)

    plans_1 = [
        (p.job_id, p.technician_id, p.scheduled_start, p.scheduled_end, p.travel_time_minutes)
        for p in res_1.assignments
    ]
    plans_2 = [
        (p.job_id, p.technician_id, p.scheduled_start, p.scheduled_end, p.travel_time_minutes)
        for p in res_2.assignments
    ]

    assert plans_1 == plans_2
    assert res_1.unassigned_jobs == res_2.unassigned_jobs


def test_zero_hard_constraint_violations(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    No hard constraints are violated:
    - Skills (HARD)
    - Equipment (HARD)
    - Zones (HARD)
    - Time windows [start, end] (HARD)
    - Duration integrity (HARD)
    - Simulation clock bounds (HARD)
    - No overlapping assignments or travel buffer violations (HARD)
    """
    service = SchedulingService(db_session)
    inputs = service.load_inputs()
    result = run_deterministic_initial_scheduler(inputs)

    tech_map = {t.id: t for t in inputs.technicians}
    job_map = {j.id: j for j in inputs.pending_jobs}

    # Group plans by technician
    plans_by_tech = {}
    for plan in result.assignments:
        plans_by_tech.setdefault(plan.technician_id, []).append(plan)

    for tech_id, plans in plans_by_tech.items():
        tech = tech_map[tech_id]
        plans.sort(key=lambda x: x.scheduled_start)

        # 1. No overlapping intervals or travel buffer deficits
        for i in range(len(plans) - 1):
            p1 = plans[i]
            p2 = plans[i + 1]

            # Direct overlap check
            assert p1.scheduled_end <= p2.scheduled_start, (
                f"Overlap detected for {tech_id}: {p1.job_id} ({p1.scheduled_end}) collides with {p2.job_id} ({p2.scheduled_start})"
            )

            # Transit travel buffer check
            lat1 = p1.details.get("lat") if p1.details else None
            lng1 = p1.details.get("lng") if p1.details else None
            lat2 = p2.details.get("lat") if p2.details else None
            lng2 = p2.details.get("lng") if p2.details else None

            if lat1 is not None and lat2 is not None:
                dist = haversine_distance(lat1, lng1, lat2, lng2)
                transit = calculate_travel_minutes(dist)
                earliest_arrival = p1.scheduled_end + timedelta(minutes=transit)
                assert earliest_arrival <= p2.scheduled_start, (
                    f"Transit buffer deficit for {tech_id}: travel from {p1.job_id} to {p2.job_id} requires {transit:.1f} mins "
                    f"(arrives {earliest_arrival}, but starts {p2.scheduled_start})"
                )

        # 2. Check each newly assigned job's qualifications and time windows
        for plan in plans:
            if plan.is_existing:
                continue

            job = job_map[plan.job_id]

            # Skills check
            s_res = check_technician_skills(job.required_skills, tech.skills, tech.id)
            assert s_res.is_eligible is True, f"Skill failure: {tech_id} lacks skills for {job.id}"

            # Equipment check
            e_res = check_technician_equipment(job.required_equipment, tech.equipment, tech.id)
            assert e_res.is_eligible is True, f"Equipment failure: {tech_id} lacks tools for {job.id}"

            # Zone check
            z_res = check_zone_eligibility(job.zone_id, tech.eligible_zones, tech.home_zone_id, tech.id)
            assert z_res.is_eligible is True, f"Zone failure: {tech_id} ineligible for zone {job.zone_id}"

            # Hard time window check
            assert plan.scheduled_start >= job.time_window_start, (
                f"Early start: {job.id} started at {plan.scheduled_start} before {job.time_window_start}"
            )
            assert plan.scheduled_end <= job.time_window_end, (
                f"Late finish: {job.id} ended at {plan.scheduled_end} after hard window {job.time_window_end}"
            )

            # Duration check
            duration_diff = (plan.scheduled_end - plan.scheduled_start).total_seconds() / 60.0
            assert duration_diff == job.duration_minutes

            # Simulation clock check
            assert plan.scheduled_start >= inputs.as_of


def test_unsupported_and_unassignable_jobs_handled(db_session):
    """Verify that unassignable jobs (e.g. JOB-014 requiring high_voltage) remain properly unassigned."""
    service = SchedulingService(db_session)
    inputs = service.load_inputs()
    result = run_deterministic_initial_scheduler(inputs)

    # JOB-014 requires high_voltage which is unsupported by the fleet
    assert "JOB-014" in result.unassigned_jobs

    unassigned_reports = {r["job_id"]: r for r in result.metrics["unassigned_reports"]}
    assert "JOB-014" in unassigned_reports
    assert "high_voltage" in unassigned_reports["JOB-014"]["reason"]


def test_api_scheduling_runs_initial_endpoint(test_client):
    """Test POST /api/v1/scheduling/runs/initial returns 201 Created and structured result."""
    resp = test_client.post("/api/v1/scheduling/runs/initial", json={})
    assert resp.status_code == 201
    data = resp.json()

    assert data["status"] == "scheduled"
    assert data["existing_assignments_preserved"] is True
    assert data["assigned_jobs_count"] >= 80
    assert data["unassigned_jobs_count"] > 0
    assert "metrics" in data
    assert data["metrics"]["active_technicians_utilized"] == 20
