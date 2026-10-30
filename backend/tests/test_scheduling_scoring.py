from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.assignment import Assignment
from app.scheduling.service import SchedulingService
from app.scheduling.schemas import (
    ObjectiveWeightsConfig,
    ScheduleAssignmentItem,
    ScheduleScoreResult,
)
from app.scheduling.scoring import (
    calculate_sla_lateness_penalty,
    calculate_travel_time_penalty,
    calculate_unassigned_penalty,
    calculate_overtime_penalty,
    calculate_assignment_churn_penalty,
    validate_schedule_hard_constraints,
    evaluate_schedule_score,
    SCORING_UNITS,
    SCORING_ASSUMPTIONS,
)
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse, LocationSchema, OvertimeSchema


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        service = SchedulingService(session)
        service.reset_schedule_to_baseline()
        session.close()


@pytest.fixture
def test_client():
    client = TestClient(app)
    yield client
    session = SessionLocal()
    try:
        service = SchedulingService(session)
        service.reset_schedule_to_baseline()
    finally:
        session.close()


def test_sla_lateness_penalty_calculation():
    """Verify SLA lateness penalty is calculated linearly past soft deadline and 0 on-time."""
    now = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    job_delayed = JobResponse(
        id="JOB-DELAYED",
        customer_name="Cust",
        title="Delayed Job",
        lat=12.0,
        lng=76.0,
        address="Addr",
        priority=2,
        priority_label="high",
        duration_minutes=60,
        required_skills=["electrical"],
        required_equipment=[],
        time_window_start=now,
        time_window_end=now + timedelta(hours=5),
        sla_deadline=now + timedelta(hours=1),  # Deadline is 11:00
        status="assigned",
        created_at=now,
    )
    job_ontime = JobResponse(
        id="JOB-ONTIME",
        customer_name="Cust",
        title="Ontime Job",
        lat=12.0,
        lng=76.0,
        address="Addr",
        priority=3,
        priority_label="medium",
        duration_minutes=60,
        required_skills=["electrical"],
        required_equipment=[],
        time_window_start=now,
        time_window_end=now + timedelta(hours=5),
        sla_deadline=now + timedelta(hours=3),  # Deadline is 13:00
        status="assigned",
        created_at=now,
    )

    jobs_map = {"JOB-DELAYED": job_delayed, "JOB-ONTIME": job_ontime}

    # Delayed completes at 11:30 (30 mins past 11:00 deadline)
    assign_delayed = ScheduleAssignmentItem(
        job_id="JOB-DELAYED",
        technician_id="T01",
        start_time=now + timedelta(minutes=30),
        end_time=now + timedelta(minutes=90),  # 11:30
        duration_minutes=60,
    )
    # Ontime completes at 11:30 (before 13:00 deadline)
    assign_ontime = ScheduleAssignmentItem(
        job_id="JOB-ONTIME",
        technician_id="T02",
        start_time=now + timedelta(minutes=30),
        end_time=now + timedelta(minutes=90),  # 11:30
        duration_minutes=60,
    )

    # Weight = 2.0
    sla_result = calculate_sla_lateness_penalty(
        jobs_map=jobs_map,
        assignments=[assign_delayed, assign_ontime],
        weight=2.0,
    )

    assert sla_result.total_delayed_jobs == 1
    assert sla_result.total_lateness_minutes == 30
    assert sla_result.total_penalty == 60.0  # 30 mins * 2.0
    assert len(sla_result.delayed_jobs) == 1
    assert sla_result.delayed_jobs[0].job_id == "JOB-DELAYED"


def test_travel_time_penalty_calculation():
    """Verify transit penalty is computed across sequential stops including home base."""
    now = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    tech = TechnicianResponse(
        id="T01",
        name="Arjun Rao",
        home_zone_id="Z1",
        home_lat=12.30,
        home_lng=76.60,
        home_location=LocationSchema(lat=12.30, lng=76.60),
        eligible_zones=["Z1"],
        skills=["electrical"],
        equipment=[],
        shifts=[],
        unavailable_periods=[],
        overtime=OvertimeSchema(allowed=False, max_minutes_per_shift=0),
    )
    # Job 1 is ~5.5 km from home base
    job1 = JobResponse(
        id="JOB-1",
        customer_name="Cust1",
        title="Job 1",
        lat=12.35,
        lng=76.60,
        address="Addr1",
        priority=2,
        priority_label="high",
        duration_minutes=60,
        required_skills=["electrical"],
        required_equipment=[],
        time_window_start=now,
        time_window_end=now + timedelta(hours=4),
        sla_deadline=now + timedelta(hours=4),
        status="assigned",
        created_at=now,
    )

    techs_map = {"T01": tech}
    jobs_map = {"JOB-1": job1}

    assign1 = ScheduleAssignmentItem(
        job_id="JOB-1",
        technician_id="T01",
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=2),
        duration_minutes=60,
    )

    travel_result = calculate_travel_time_penalty(
        techs_map=techs_map,
        jobs_map=jobs_map,
        assignments_by_tech={"T01": [assign1]},
        weight=1.5,
    )

    assert travel_result.total_travel_minutes > 0
    assert travel_result.total_distance_km > 0
    assert travel_result.total_penalty == round(travel_result.total_travel_minutes * 1.5, 2)
    assert len(travel_result.technician_travel) == 1


def test_unassigned_priority_penalty_stratification():
    """Verify unassigned jobs are penalized according to their priority tier."""
    now = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    jobs = [
        JobResponse(id="J1", customer_name="C", title="T", lat=12.0, lng=76.0, address="A", priority=1, priority_label="urgent", duration_minutes=60, required_skills=["s"], required_equipment=[], time_window_start=now, time_window_end=now + timedelta(hours=4), sla_deadline=now + timedelta(hours=4), status="pending", created_at=now),
        JobResponse(id="J2", customer_name="C", title="T", lat=12.0, lng=76.0, address="A", priority=2, priority_label="high", duration_minutes=60, required_skills=["s"], required_equipment=[], time_window_start=now, time_window_end=now + timedelta(hours=4), sla_deadline=now + timedelta(hours=4), status="pending", created_at=now),
        JobResponse(id="J3", customer_name="C", title="T", lat=12.0, lng=76.0, address="A", priority=3, priority_label="medium", duration_minutes=60, required_skills=["s"], required_equipment=[], time_window_start=now, time_window_end=now + timedelta(hours=4), sla_deadline=now + timedelta(hours=4), status="pending", created_at=now),
        JobResponse(id="J4", customer_name="C", title="T", lat=12.0, lng=76.0, address="A", priority=4, priority_label="low", duration_minutes=60, required_skills=["s"], required_equipment=[], time_window_start=now, time_window_end=now + timedelta(hours=4), sla_deadline=now + timedelta(hours=4), status="pending", created_at=now),
    ]

    weights = ObjectiveWeightsConfig(
        w_unassigned_p1=1000.0,
        w_unassigned_p2=500.0,
        w_unassigned_p3=200.0,
        w_unassigned_p4=100.0,
    )

    unassigned_result = calculate_unassigned_penalty(jobs, weights)

    assert unassigned_result.unassigned_p1_count == 1
    assert unassigned_result.unassigned_p2_count == 1
    assert unassigned_result.unassigned_p3_count == 1
    assert unassigned_result.unassigned_p4_count == 1
    assert unassigned_result.p1_penalty == 1000.0
    assert unassigned_result.p2_penalty == 500.0
    assert unassigned_result.p3_penalty == 200.0
    assert unassigned_result.p4_penalty == 100.0
    assert unassigned_result.total_penalty == 1800.0


def test_overtime_penalty_calculation():
    """Verify overtime penalty is computed for service past shift end."""
    tech = TechnicianResponse(
        id="T01",
        name="Arjun Rao",
        home_zone_id="Z1",
        home_lat=12.30,
        home_lng=76.60,
        home_location=LocationSchema(lat=12.30, lng=76.60),
        eligible_zones=["Z1"],
        skills=["electrical"],
        equipment=[],
        shifts=[
            {
                "date": "2026-11-02",
                "start": datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc),
                "end": datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc),
            }
        ],
        unavailable_periods=[],
        overtime_allowed=True,
        max_overtime_minutes=120,
        overtime=OvertimeSchema(allowed=True, max_minutes_per_shift=120),
    )

    # Job finishes at 18:00 (60 mins overtime past 17:00)
    assign = ScheduleAssignmentItem(
        job_id="JOB-OT",
        technician_id="T01",
        start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc),
        duration_minutes=120,
    )

    ot_result = calculate_overtime_penalty(
        techs_map={"T01": tech},
        assignments_by_tech={"T01": [assign]},
        weight=3.0,
    )

    assert ot_result.total_overtime_minutes == 60
    assert ot_result.total_penalty == 180.0  # 60 mins * 3.0
    assert len(ot_result.technician_overtime) == 1


def test_assignment_churn_penalty():
    """Verify assignment churn penalty when pre-existing assignment is reassigned."""
    now = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    baseline_assign = ScheduleAssignmentItem(
        job_id="JOB-BASE",
        technician_id="T01",
        start_time=now,
        end_time=now + timedelta(hours=1),
        duration_minutes=60,
        is_existing=True,
    )
    # Reassigned to T02
    new_assign = ScheduleAssignmentItem(
        job_id="JOB-BASE",
        technician_id="T02",
        start_time=now,
        end_time=now + timedelta(hours=1),
        duration_minutes=60,
        is_existing=False,
    )

    churn_result = calculate_assignment_churn_penalty(
        baseline_assignments=[baseline_assign],
        candidate_assignments=[new_assign],
        weight=250.0,
    )

    assert churn_result.total_disrupted_jobs == 1
    assert churn_result.total_penalty == 250.0
    assert len(churn_result.churn_details) == 1
    assert churn_result.churn_details[0].baseline_technician_id == "T01"
    assert churn_result.churn_details[0].new_technician_id == "T02"


def test_hard_constraints_checked_independently():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Hard constraints cannot be overridden by a better score.
    - If double booking or skill mismatch occurs, is_feasible must be False.
    """
    now = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    tech = TechnicianResponse(
        id="T01",
        name="Arjun Rao",
        home_zone_id="Z1",
        home_lat=12.30,
        home_lng=76.60,
        home_location=LocationSchema(lat=12.30, lng=76.60),
        eligible_zones=["Z1"],
        skills=["electrical"],
        equipment=[],
        shifts=[],
        unavailable_periods=[],
        overtime=OvertimeSchema(allowed=False, max_minutes_per_shift=0),
    )
    # Job requires plumbing which T01 lacks
    job_unskilled = JobResponse(
        id="JOB-UNSKILLED",
        customer_name="Cust",
        title="Plumbing Job",
        lat=12.30,
        lng=76.60,
        address="A",
        priority=3,
        priority_label="medium",
        duration_minutes=60,
        required_skills=["plumbing"],
        required_equipment=[],
        time_window_start=now,
        time_window_end=now + timedelta(hours=5),
        sla_deadline=now + timedelta(hours=5),
        status="pending",
        created_at=now,
    )

    assign_illegal = ScheduleAssignmentItem(
        job_id="JOB-UNSKILLED",
        technician_id="T01",
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=2),
        duration_minutes=60,
        is_existing=False,
    )

    score_result = evaluate_schedule_score(
        jobs=[job_unskilled],
        technicians=[tech],
        assignments=[assign_illegal],
        as_of=now,
    )

    # Even though travel is 0 and SLA is 0, it MUST be marked infeasible!
    assert score_result.is_feasible is False
    assert score_result.hard_violations_count > 0
    violation_types = [v.violation_type for v in score_result.hard_violations]
    assert "SKILL_MISMATCH" in violation_types


def test_configurable_weights_and_traceability(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Every score component is traceable.
    - Weights are configurable.
    - Same schedule produces the exact same score.
    """
    service = SchedulingService(db_session)

    # 1. Evaluate with default weights
    score_default = service.get_schedule_score()
    assert score_default.total_score > 0
    assert score_default.units == SCORING_UNITS
    assert len(score_default.assumptions) > 0

    # Verify component summation equals total score
    expected_sum = round(
        score_default.sla_component.total_penalty
        + score_default.travel_component.total_penalty
        + score_default.unassigned_component.total_penalty
        + score_default.overtime_component.total_penalty
        + score_default.churn_component.total_penalty,
        2,
    )
    assert score_default.total_score == expected_sum

    # 2. Evaluate with modified custom weights
    custom_weights = ObjectiveWeightsConfig(
        w_travel_time=5.0,  # 5x default
        w_unassigned_p1=2000.0,
    )
    score_custom = service.get_schedule_score(weights=custom_weights)

    # Travel cost must be exactly 5x default travel cost (since travel mins is identical)
    assert score_custom.travel_component.total_penalty == round(
        score_default.travel_component.total_travel_minutes * 5.0, 2
    )
    assert score_custom.weights_used.w_travel_time == 5.0

    # 3. Deterministic repeatability check
    score_repeat = service.get_schedule_score(weights=custom_weights)
    assert score_repeat.total_score == score_custom.total_score
    assert score_repeat.is_feasible == score_custom.is_feasible


def test_schedule_score_api_endpoints(test_client):
    """Verify GET and POST /api/v1/schedule/score API endpoints."""
    # 1. GET /api/v1/schedule/score
    resp_get = test_client.get("/api/v1/schedule/score")
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert "total_score" in data_get
    assert "is_feasible" in data_get
    assert "sla_component" in data_get
    assert "travel_component" in data_get
    assert "unassigned_component" in data_get
    assert "units" in data_get

    # 2. POST /api/v1/schedule/score with custom weights
    custom_payload = {
        "weights": {
            "w_sla_lateness": 4.0,
            "w_travel_time": 2.5,
            "w_unassigned_p1": 1500.0,
        }
    }
    resp_post = test_client.post("/api/v1/schedule/score", json=custom_payload)
    assert resp_post.status_code == 200
    data_post = resp_post.json()
    assert data_post["weights_used"]["w_travel_time"] == 2.5
    assert data_post["weights_used"]["w_sla_lateness"] == 4.0
