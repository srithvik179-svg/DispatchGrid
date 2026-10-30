"""
Phase 26: SLA Optimisation and Deadline-Aware Scheduling Tests.

Verifies:
1. Expected completion time and SLA lateness calculation accuracy.
2. The already-breached but assignable job (JOB-016): soft SLA breach does not block assignment,
   and customer hard time window is strictly protected.
3. Distinction between hard time windows and soft SLA deadlines.
4. Identification of at-risk jobs based on configurable slack thresholds.
5. Configurable lateness penalties applied correctly.
6. Deterministic arbitration between multiple competing SLA deadlines.
7. Fleet SLA performance metrics generation.
8. SLA schedule optimization execution preserving all hard constraints.
9. REST API endpoints for SLA metrics, job SLA details, competing resolution, and optimization.
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
from app.scheduling.algorithm import run_deterministic_initial_scheduler
from app.scheduling.scoring import validate_schedule_hard_constraints
from app.scheduling.sla_opt import (
    calculate_job_sla_detail,
    calculate_fleet_sla_metrics,
    resolve_competing_sla_deadlines,
    optimize_schedule_sla,
)
from app.scheduling.schemas import (
    AssignedJobPlan,
    JobSLADetail,
    FleetSLAMetrics,
    SLAOptimizationResult,
    CompetingSLAResolution,
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


def test_job_sla_detail_calculation():
    """
    TASKS:
    - Calculate expected completion time.
    - Calculate SLA lateness.
    - Apply configurable lateness penalties.
    """
    job_model = JobResponse(
        id="JOB-TEST-1",
        title="Emergency HVAC Test",
        customer_name="Acme Corp",
        address="100 Test St, Chennai",
        priority=1,
        priority_label="URGENT",
        zone="Z1",
        lat=13.0827,
        lng=80.2707,
        duration_minutes=60,
        required_skills=["HVAC"],
        required_equipment=[],
        time_window_start=datetime(2026, 11, 2, 9, 0, tzinfo=IST),
        time_window_end=datetime(2026, 11, 2, 14, 0, tzinfo=IST),
        sla_deadline=datetime(2026, 11, 2, 11, 0, tzinfo=IST),
        status="pending",
        created_at=datetime(2026, 11, 2, 8, 0, tzinfo=IST),
    )

    # 1. On-time assignment
    plan_on_time = AssignedJobPlan(
        assignment_id="ASG-TEST-1",
        job_id="JOB-TEST-1",
        technician_id="T01",
        scheduled_start=datetime(2026, 11, 2, 9, 30, tzinfo=IST),
        scheduled_end=datetime(2026, 11, 2, 10, 30, tzinfo=IST),
        status="scheduled",
    )
    detail_on_time = calculate_job_sla_detail(
        job=job_model,
        assignment=plan_on_time,
        as_of=datetime(2026, 11, 2, 9, 0, tzinfo=IST),
        lateness_weight=3.0,
        at_risk_threshold_minutes=20,
    )
    assert detail_on_time.expected_completion == plan_on_time.scheduled_end
    assert detail_on_time.sla_status == "ON_TIME"
    assert detail_on_time.lateness_minutes == 0.0
    assert detail_on_time.slack_buffer_minutes == 30.0  # 11:00 - 10:30 = 30m
    assert detail_on_time.lateness_penalty == 0.0

    # 2. Breached assignment (past SLA deadline 11:00, but within hard window 14:00)
    plan_breached = AssignedJobPlan(
        assignment_id="ASG-TEST-2",
        job_id="JOB-TEST-1",
        technician_id="T01",
        scheduled_start=datetime(2026, 11, 2, 11, 0, tzinfo=IST),
        scheduled_end=datetime(2026, 11, 2, 12, 0, tzinfo=IST),
        status="scheduled",
    )
    detail_breached = calculate_job_sla_detail(
        job=job_model,
        assignment=plan_breached,
        as_of=datetime(2026, 11, 2, 9, 0, tzinfo=IST),
        lateness_weight=2.5,
    )
    assert detail_breached.sla_status == "BREACHED"
    assert detail_breached.lateness_minutes == 60.0  # 12:00 - 11:00
    assert detail_breached.lateness_penalty == 150.0  # 60 * 2.5
    assert detail_breached.is_within_hard_window is True  # 12:00 <= 14:00


def test_already_breached_but_assignable_job_JOB_016(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Already-breached jobs can still be assigned when otherwise feasible.
    - Test the already-breached but assignable job (JOB-016).
    - Hard time windows remain protected.
    - SLA decisions are explainable.
    """
    job_db = db_session.query(Job).filter(Job.id == "JOB-016").first()
    assert job_db is not None
    job = JobResponse.model_validate(job_db)

    service = SchedulingService(db_session)
    as_of = service.get_clock()

    # Verify JOB-016 target deadline was prior to simulation start
    assert job.sla_deadline < as_of
    # Customer hard window is 09:00 to 13:00 (still open at 10:00)
    assert job.time_window_start <= as_of <= job.time_window_end

    # Run initial assignment algorithm
    inputs = service.load_inputs()
    result = run_deterministic_initial_scheduler(inputs)
    assigned_ids = {a.job_id for a in result.assignments}
    assert "JOB-016" in assigned_ids, "JOB-016 must be assigned despite already breached SLA"

    asg_016 = next(a for a in result.assignments if a.job_id == "JOB-016")
    detail = calculate_job_sla_detail(job=job, assignment=asg_016, as_of=as_of)

    assert detail.is_already_breached_at_as_of is True
    assert detail.sla_status == "BREACHED"
    assert detail.is_within_hard_window is True
    assert detail.expected_completion <= job.time_window_end
    assert detail.lateness_minutes > 0.0
    assert "already past its SLA target" in detail.explanation
    assert "safely within customer hard window" in detail.explanation


def test_distinguish_hard_time_windows_from_soft_sla(db_session):
    """
    ACCEPTANCE CRITERIA:
    - Distinguish hard time windows from soft SLA deadlines.
    - Hard time windows remain protected.
    """
    techs = [TechnicianResponse.model_validate(t) for t in db_session.query(Technician).all()]
    jobs = [JobResponse.model_validate(j) for j in db_session.query(Job).all()]
    techs_map = {t.id: t for t in techs}
    jobs_map = {j.id: j for j in jobs}
    as_of = datetime(2026, 11, 2, 10, 0, tzinfo=IST)

    # 1. Soft breach: scheduled end past sla_deadline, but within time_window_end -> Feasible
    soft_breach_plan = AssignedJobPlan(
        assignment_id="ASG-SOFT",
        job_id="JOB-016",
        technician_id="T02",
        scheduled_start=datetime(2026, 11, 2, 10, 30, tzinfo=IST),
        scheduled_end=datetime(2026, 11, 2, 11, 30, tzinfo=IST),
        status="scheduled",
    )
    violations = validate_schedule_hard_constraints(
        techs_map=techs_map,
        jobs_map=jobs_map,
        assignments_by_tech={"T02": [soft_breach_plan]},
        as_of=as_of,
    )
    assert len(violations) == 0, "Soft SLA breach must NOT violate hard constraints"

    # 2. Hard breach: scheduled end past customer time_window_end -> INFEASIBLE
    hard_breach_plan = AssignedJobPlan(
        assignment_id="ASG-HARD",
        job_id="JOB-016",
        technician_id="T02",
        scheduled_start=datetime(2026, 11, 2, 13, 30, tzinfo=IST),
        scheduled_end=datetime(2026, 11, 2, 14, 30, tzinfo=IST),
        status="scheduled",
    )
    violations_hard = validate_schedule_hard_constraints(
        techs_map=techs_map,
        jobs_map=jobs_map,
        assignments_by_tech={"T02": [hard_breach_plan]},
        as_of=as_of,
    )
    assert len(violations_hard) > 0
    assert any("TIME_WINDOW" in v.violation_type for v in violations_hard)


def test_identify_at_risk_jobs():
    """
    TASKS:
    - Identify at-risk jobs (slack buffer <= threshold).
    """
    job = JobResponse(
        id="JOB-RISK",
        title="Check Server",
        customer_name="Tech Hub",
        address="45 IT Park, Chennai",
        priority=2,
        priority_label="HIGH",
        zone="Z1",
        lat=13.0827,
        lng=80.2707,
        duration_minutes=30,
        required_skills=["Electrical"],
        required_equipment=[],
        time_window_start=datetime(2026, 11, 2, 9, 0, tzinfo=IST),
        time_window_end=datetime(2026, 11, 2, 17, 0, tzinfo=IST),
        sla_deadline=datetime(2026, 11, 2, 11, 0, tzinfo=IST),
        status="pending",
        created_at=datetime(2026, 11, 2, 8, 0, tzinfo=IST),
    )
    # Completion at 10:45 -> buffer is 15 minutes (<= 30 min threshold)
    plan = AssignedJobPlan(
        assignment_id="ASG-RISK",
        job_id="JOB-RISK",
        technician_id="T01",
        scheduled_start=datetime(2026, 11, 2, 10, 15, tzinfo=IST),
        scheduled_end=datetime(2026, 11, 2, 10, 45, tzinfo=IST),
        status="scheduled",
    )
    detail = calculate_job_sla_detail(job=job, assignment=plan, at_risk_threshold_minutes=30)
    assert detail.sla_status == "AT_RISK"
    assert detail.slack_buffer_minutes == 15.0
    assert "AT RISK" in detail.explanation


def test_competing_sla_deadlines_resolution(db_session):
    """
    TASKS:
    - Add tests for multiple competing SLA deadlines.
    - Prioritise jobs with approaching deadlines.
    - Tie-breaking rules documented and verified.
    """
    service = SchedulingService(db_session)
    as_of = service.get_clock()
    jobs_map = {j.id: JobResponse.model_validate(j) for j in db_session.query(Job).all()}

    # Pair 1: JOB-016 (SLA Nov 2 09:30) vs JOB-055 (SLA Nov 2 13:15)
    # JOB-016 deadline is earlier -> wins by SLA_DEADLINE_IMMINENCE
    res_1 = resolve_competing_sla_deadlines(jobs_map["JOB-016"], jobs_map["JOB-055"], as_of)
    assert res_1.winner_job_id == "JOB-016"
    assert res_1.deciding_factor == "SLA_DEADLINE_IMMINENCE"

    # Pair 2: JOB-055 (SLA Nov 2 13:15) vs JOB-048 (SLA Nov 3 11:15)
    # JOB-055 deadline is earlier -> wins by SLA_DEADLINE_IMMINENCE
    res_2 = resolve_competing_sla_deadlines(jobs_map["JOB-055"], jobs_map["JOB-048"], as_of)
    assert res_2.winner_job_id == "JOB-055"
    assert res_2.deciding_factor == "SLA_DEADLINE_IMMINENCE"

    # Pair 3: Equal SLA deadlines, but different priority tiers
    job_a = JobResponse(
        id="JOB-TIE-A",
        title="High Priority Job",
        customer_name="Corp A",
        address="100 A St",
        priority=1,
        priority_label="URGENT",
        zone="Z1",
        lat=13.0,
        lng=80.0,
        duration_minutes=30,
        required_skills=[],
        required_equipment=[],
        time_window_start=datetime(2026, 11, 2, 9, 0, tzinfo=IST),
        time_window_end=datetime(2026, 11, 2, 17, 0, tzinfo=IST),
        sla_deadline=datetime(2026, 11, 2, 12, 0, tzinfo=IST),
        status="pending",
        created_at=datetime(2026, 11, 2, 8, 0, tzinfo=IST),
    )
    job_b = JobResponse(
        id="JOB-TIE-B",
        title="Normal Priority Job",
        customer_name="Corp B",
        address="200 B St",
        priority=3,
        priority_label="MEDIUM",
        zone="Z1",
        lat=13.0,
        lng=80.0,
        duration_minutes=30,
        required_skills=[],
        required_equipment=[],
        time_window_start=datetime(2026, 11, 2, 9, 0, tzinfo=IST),
        time_window_end=datetime(2026, 11, 2, 17, 0, tzinfo=IST),
        sla_deadline=datetime(2026, 11, 2, 12, 0, tzinfo=IST),
        status="pending",
        created_at=datetime(2026, 11, 2, 8, 0, tzinfo=IST),
    )
    res_3 = resolve_competing_sla_deadlines(job_a, job_b, as_of)
    assert res_3.winner_job_id == "JOB-TIE-A"
    assert res_3.deciding_factor == "PRIORITY_LEVEL"


def test_fleet_sla_metrics_generation(db_session):
    """
    TASKS:
    - Generate SLA performance metrics across the entire fleet.
    """
    service = SchedulingService(db_session)
    as_of = service.get_clock()
    jobs = [JobResponse.model_validate(j) for j in db_session.query(Job).all()]
    inputs = service.load_inputs()
    initial_res = run_deterministic_initial_scheduler(inputs)

    details, metrics = calculate_fleet_sla_metrics(
        jobs=jobs,
        assignments=initial_res.assignments,
        as_of=as_of,
        lateness_weight=2.0,
        at_risk_threshold_minutes=30,
    )

    assert metrics.total_jobs_evaluated == len(jobs)
    assert metrics.assigned_jobs_count == len(initial_res.assignments)
    assert metrics.on_time_count + metrics.at_risk_count + metrics.breached_count == metrics.assigned_jobs_count
    assert metrics.already_breached_assigned_count >= 1
    assert metrics.on_time_percentage > 70.0
    assert metrics.total_sla_penalty >= 0.0


def test_sla_optimization_execution(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - SLA optimization never violates hard constraints.
    - Hard time windows remain protected.
    - Pre-existing assignments are protected.
    """
    service = SchedulingService(db_session)
    as_of = service.get_clock()
    jobs = [JobResponse.model_validate(j) for j in db_session.query(Job).all()]
    techs = [TechnicianResponse.model_validate(t) for t in db_session.query(Technician).all()]
    inputs = service.load_inputs()
    initial_res = run_deterministic_initial_scheduler(inputs)

    opt_result = optimize_schedule_sla(
        initial_assignments=initial_res.assignments,
        technicians=techs,
        jobs=jobs,
        as_of=as_of,
    )

    assert opt_result.is_feasible is True
    assert opt_result.hard_violations_count == 0
    assert opt_result.hard_violations == []
    assert len(opt_result.assignments) == len(initial_res.assignments)

    # Protect existing assignments
    existing_initial = {a.job_id: a for a in initial_res.assignments if a.is_existing}
    for p in opt_result.assignments:
        if p.job_id in existing_initial:
            orig = existing_initial[p.job_id]
            assert p.technician_id == orig.technician_id
            assert p.scheduled_start == orig.scheduled_start
            assert p.scheduled_end == orig.scheduled_end


def test_sla_rest_api_endpoints(test_client):
    """
    ACCEPTANCE CRITERIA:
    - Endpoints respond with valid schemas and accurate SLA metrics.
    """
    # 1. Job SLA Detail for JOB-016
    resp_job = test_client.get("/api/v1/jobs/JOB-016/sla")
    assert resp_job.status_code == 200
    data_job = resp_job.json()
    assert data_job["job_id"] == "JOB-016"
    assert data_job["is_already_breached_at_as_of"] is True
    assert data_job["sla_status"] == "BREACHED"
    assert data_job["is_within_hard_window"] is True

    # 2. Fleet SLA Metrics
    resp_metrics = test_client.get("/api/v1/schedule/sla-metrics")
    assert resp_metrics.status_code == 200
    data_metrics = resp_metrics.json()
    metrics = data_metrics.get("fleet_metrics", data_metrics)
    assert metrics["total_jobs_evaluated"] == 108
    assert metrics["assigned_jobs_count"] == 88
    assert metrics["already_breached_assigned_count"] >= 1

    # 3. Competing SLA Arbitration Endpoint
    resp_comp = test_client.post(
        "/api/v1/schedule/sla/resolve",
        json={"job_id_a": "JOB-016", "job_id_b": "JOB-055"},
    )
    assert resp_comp.status_code == 200
    data_comp = resp_comp.json()
    assert data_comp["winner_job_id"] == "JOB-016"
    assert data_comp["deciding_factor"] == "SLA_DEADLINE_IMMINENCE"

    # 4. SLA Optimization Endpoint
    resp_opt = test_client.post(
        "/api/v1/schedule/optimize/sla",
        json={"persist": False, "lateness_weight": 2.0},
    )
    assert resp_opt.status_code == 200
    data_opt = resp_opt.json()
    assert data_opt["is_feasible"] is True
    assert data_opt["hard_violations_count"] == 0
    assert "comparison" in data_opt
