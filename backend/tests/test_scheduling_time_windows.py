from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.job import Job
from app.scheduling.time_windows import (
    validate_job_time_window,
    validate_job_instance_time_window,
    calculate_feasible_service_window,
)
from app.scheduling.service import SchedulingService

TZ_KOLKATA = timezone(timedelta(hours=5, minutes=30))


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


def test_time_window_exact_boundaries():
    """Verify exact boundary conditions: exact start on window_start and exact end on window_end."""
    w_start = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)
    w_end = datetime(2026, 11, 2, 14, 0, 0, tzinfo=TZ_KOLKATA)
    duration = 60

    # 1. Exact start at window_start
    res_start = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=w_start,
        enforce_simulation_clock=False,
    )
    assert res_start.is_eligible is True
    assert res_start.starts_too_early is False
    assert res_start.ends_too_late is False
    assert res_start.proposed_start == w_start
    assert res_start.proposed_end == w_start + timedelta(minutes=duration)

    # 2. Exact completion at window_end
    latest_start = w_end - timedelta(minutes=duration)
    res_end = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=latest_start,
        enforce_simulation_clock=False,
    )
    assert res_end.is_eligible is True
    assert res_end.ends_too_late is False
    assert res_end.proposed_end == w_end


def test_time_window_early_start_rejection():
    """Verify rejection when proposed start is even 1 minute earlier than window start."""
    w_start = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)
    w_end = datetime(2026, 11, 2, 14, 0, 0, tzinfo=TZ_KOLKATA)
    duration = 60

    p_start = w_start - timedelta(minutes=1)  # 09:59
    res = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=p_start,
        enforce_simulation_clock=False,
    )
    assert res.is_eligible is False
    assert res.starts_too_early is True
    assert "START_BEFORE_WINDOW_START" in res.rejection_codes
    assert "earlier than permissible window start" in res.rejection_reasons[0]


def test_time_window_late_finish_rejection():
    """Verify rejection when service completion is even 1 minute later than hard window end."""
    w_start = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)
    w_end = datetime(2026, 11, 2, 14, 0, 0, tzinfo=TZ_KOLKATA)
    duration = 60

    # Start at 13:01 -> ends at 14:01 (exceeds 14:00 by 1 min)
    p_start = datetime(2026, 11, 2, 13, 1, 0, tzinfo=TZ_KOLKATA)
    res = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=p_start,
        enforce_simulation_clock=False,
    )
    assert res.is_eligible is False
    assert res.ends_too_late is True
    assert "END_AFTER_WINDOW_END" in res.rejection_codes
    assert "exceeds hard time window end" in res.rejection_reasons[0]


def test_sla_lateness_distinguished_from_hard_rejection():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    SLA lateness does NOT automatically cause a hard rejection.
    If service finishes within hard window end but after SLA deadline:
    is_eligible remains True, but is_sla_violated = True with lateness recorded.
    """
    w_start = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)
    w_end = datetime(2026, 11, 2, 18, 0, 0, tzinfo=TZ_KOLKATA)  # hard window until 18:00
    sla_deadline = datetime(2026, 11, 2, 14, 0, 0, tzinfo=TZ_KOLKATA)  # SLA target is 14:00
    duration = 90  # 1.5 hours

    # 1. Finish before SLA deadline (e.g. 11:00 to 12:30 <= 14:00)
    p_start_on_time = datetime(2026, 11, 2, 11, 0, 0, tzinfo=TZ_KOLKATA)
    res_on_time = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=p_start_on_time,
        sla_deadline=sla_deadline,
        enforce_simulation_clock=False,
    )
    assert res_on_time.is_eligible is True
    assert res_on_time.is_sla_violated is False
    assert res_on_time.sla_lateness_minutes == 0
    assert res_on_time.sla_status == "on_time"

    # 2. Finish exactly at SLA deadline (12:30 to 14:00 == 14:00)
    p_start_exact_sla = datetime(2026, 11, 2, 12, 30, 0, tzinfo=TZ_KOLKATA)
    res_exact_sla = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=p_start_exact_sla,
        sla_deadline=sla_deadline,
        enforce_simulation_clock=False,
    )
    assert res_exact_sla.is_eligible is True
    assert res_exact_sla.is_sla_violated is False
    assert res_exact_sla.sla_status == "on_time"

    # 3. Finish AFTER SLA deadline but BEFORE hard window end (e.g. 14:00 to 15:30)
    p_start_late = datetime(2026, 11, 2, 14, 0, 0, tzinfo=TZ_KOLKATA)
    res_late = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=p_start_late,
        sla_deadline=sla_deadline,
        enforce_simulation_clock=False,
    )
    # MUST BE ELIGIBLE (Hard window satisfies [10:00 - 18:00])
    assert res_late.is_eligible is True
    assert res_late.ends_too_late is False
    assert res_late.starts_too_early is False
    # But SLA violation must be reported!
    assert res_late.is_sla_violated is True
    assert res_late.sla_lateness_minutes == 90  # 15:30 vs 14:00 = 90 mins
    assert res_late.sla_status == "late"
    assert "misses SLA deadline by 90 mins" in res_late.summary


def test_travel_time_inclusion_and_reachability():
    """Verify that required transit time from technician origin is strictly enforced."""
    w_start = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)
    w_end = datetime(2026, 11, 2, 16, 0, 0, tzinfo=TZ_KOLKATA)
    duration = 60

    origin_dep = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)
    travel_mins = 45.0  # Arrives at 10:45

    # Case A: Proposed start at 10:30 (before earliest arrival 10:45) -> Infeasible
    p_start_early = datetime(2026, 11, 2, 10, 30, 0, tzinfo=TZ_KOLKATA)
    res_early = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=p_start_early,
        origin_departure_time=origin_dep,
        travel_minutes=travel_mins,
        enforce_simulation_clock=False,
    )
    assert res_early.is_eligible is False
    assert res_early.travel_infeasible is True
    assert "TRAVEL_TIME_INFEASIBLE" in res_early.rejection_codes
    assert res_early.earliest_arrival_time == origin_dep + timedelta(minutes=45)

    # Case B: Proposed start at exact arrival 10:45 -> Feasible
    p_start_exact = datetime(2026, 11, 2, 10, 45, 0, tzinfo=TZ_KOLKATA)
    res_exact = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=p_start_exact,
        origin_departure_time=origin_dep,
        travel_minutes=travel_mins,
        enforce_simulation_clock=False,
    )
    assert res_exact.is_eligible is True
    assert res_exact.travel_infeasible is False


def test_simulation_clock_and_expired_window_rejection():
    """Verify that appointments scheduled in the past or expired windows are rejected."""
    as_of = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)

    # Case 1: Proposed start is in the past relative to as_of
    w_start = datetime(2026, 11, 2, 8, 0, 0, tzinfo=TZ_KOLKATA)
    w_end = datetime(2026, 11, 2, 12, 0, 0, tzinfo=TZ_KOLKATA)
    p_start_past = datetime(2026, 11, 2, 9, 30, 0, tzinfo=TZ_KOLKATA)

    res_past = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=60,
        proposed_start=p_start_past,
        as_of=as_of,
        enforce_simulation_clock=True,
    )
    assert res_past.is_eligible is False
    assert res_past.starts_before_simulation_clock is True
    assert "START_BEFORE_SIMULATION_CLOCK" in res_past.rejection_codes

    # Case 2: Window ended entirely before as_of
    w_start_exp = datetime(2026, 11, 1, 10, 0, 0, tzinfo=TZ_KOLKATA)
    w_end_exp = datetime(2026, 11, 1, 14, 0, 0, tzinfo=TZ_KOLKATA)
    res_exp = validate_job_time_window(
        time_window_start=w_start_exp,
        time_window_end=w_end_exp,
        duration_minutes=60,
        proposed_start=datetime(2026, 11, 1, 11, 0, 0, tzinfo=TZ_KOLKATA),
        as_of=as_of,
        enforce_simulation_clock=True,
    )
    assert res_exp.is_eligible is False
    assert res_exp.is_window_expired is True
    assert "WINDOW_EXPIRED" in res_exp.rejection_codes

    # Case 3: Window end is 10:30, but duration is 60 mins -> insufficient remaining time at as_of 10:00
    w_end_tight = datetime(2026, 11, 2, 10, 30, 0, tzinfo=TZ_KOLKATA)
    res_tight = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end_tight,
        duration_minutes=60,
        proposed_start=as_of,
        as_of=as_of,
        enforce_simulation_clock=True,
    )
    assert res_tight.is_eligible is False
    assert res_tight.is_window_expired is True
    assert "WINDOW_EXPIRED_FOR_DURATION" in res_tight.rejection_codes


def test_duration_mismatch_and_invalid_duration():
    """Verify duration integrity and detection of mismatched proposed intervals."""
    w_start = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)
    w_end = datetime(2026, 11, 2, 14, 0, 0, tzinfo=TZ_KOLKATA)

    # Interval is 90 mins but required duration is 60 mins
    res_mismatch = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=60,
        proposed_start=datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA),
        proposed_end=datetime(2026, 11, 2, 11, 30, 0, tzinfo=TZ_KOLKATA),
        enforce_simulation_clock=False,
    )
    assert res_mismatch.is_eligible is False
    assert res_mismatch.duration_mismatch is True
    assert "DURATION_MISMATCH" in res_mismatch.rejection_codes

    # Zero or negative duration
    res_zero = validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=0,
        proposed_start=w_start,
        enforce_simulation_clock=False,
    )
    assert res_zero.is_eligible is False
    assert "INVALID_DURATION" in res_zero.rejection_codes


def test_calculate_feasible_service_window():
    """Verify calculation of earliest and latest feasible boundaries for scheduling."""
    w_start = datetime(2026, 11, 2, 10, 0, 0, tzinfo=TZ_KOLKATA)
    w_end = datetime(2026, 11, 2, 16, 0, 0, tzinfo=TZ_KOLKATA)
    sla = datetime(2026, 11, 2, 14, 0, 0, tzinfo=TZ_KOLKATA)
    duration = 60
    as_of = datetime(2026, 11, 2, 10, 30, 0, tzinfo=TZ_KOLKATA)
    origin_dep = datetime(2026, 11, 2, 10, 30, 0, tzinfo=TZ_KOLKATA)
    travel = 30.0  # Arrives 11:00

    bounds = calculate_feasible_service_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        sla_deadline=sla,
        origin_departure_time=origin_dep,
        travel_minutes=travel,
        as_of=as_of,
        enforce_simulation_clock=True,
    )
    assert bounds.is_feasible is True
    # Earliest start must be 11:00 (due to 10:30 dep + 30 min travel)
    assert bounds.earliest_feasible_start == datetime(2026, 11, 2, 11, 0, 0, tzinfo=TZ_KOLKATA)
    # Latest start is 15:00 (16:00 window_end - 60 min duration)
    assert bounds.latest_feasible_start == datetime(2026, 11, 2, 15, 0, 0, tzinfo=TZ_KOLKATA)
    # On-time SLA latest start is 13:00 (14:00 SLA - 60 min duration)
    assert bounds.on_time_sla_latest_start == datetime(2026, 11, 2, 13, 0, 0, tzinfo=TZ_KOLKATA)


def test_service_db_job_validation(db_session):
    """Verify validation against actual database job records."""
    service = SchedulingService(db_session)
    job = db_session.query(Job).filter_by(id="JOB-001").first()
    assert job is not None

    # Evaluate within job's official time window
    res = service.validate_job_time_window(
        job_id="JOB-001",
        proposed_start=job.time_window_start,
        enforce_simulation_clock=False,
    )
    assert res.job_id == "JOB-001"
    assert res.is_eligible is True
    assert res.duration_minutes == job.duration_minutes
    assert res.time_window_start == job.time_window_start
    assert res.time_window_end == job.time_window_end


def test_api_time_window_validate_endpoint(test_client):
    """Test POST /api/v1/scheduling/time-windows/validate."""
    payload = {
        "job_id": "JOB-001",
        "proposed_start": "2026-11-02T10:00:00+05:30",
        "duration_minutes": 60,
        "time_window_start": "2026-11-02T09:00:00+05:30",
        "time_window_end": "2026-11-02T13:00:00+05:30",
        "sla_deadline": "2026-11-02T12:00:00+05:30",
        "travel_minutes": 15.0,
        "origin_departure_time": "2026-11-02T09:30:00+05:30",
        "enforce_simulation_clock": False,
    }
    resp = test_client.post("/api/v1/scheduling/time-windows/validate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_eligible"] is True
    assert data["job_id"] == "JOB-001"
    assert data["travel_minutes"] == 15.0
    assert data["sla_status"] == "on_time"


def test_api_job_time_window_get_endpoints(test_client):
    """Test GET endpoints for job time-window and feasible bounds."""
    # 1. GET /api/v1/scheduling/time-windows/job/JOB-001
    resp_val = test_client.get(
        "/api/v1/scheduling/time-windows/job/JOB-001?enforce_simulation_clock=false"
    )
    assert resp_val.status_code == 200
    val_data = resp_val.json()
    assert val_data["job_id"] == "JOB-001"
    assert val_data["is_eligible"] is True

    # 2. GET /api/v1/scheduling/time-windows/job/JOB-001/feasible
    resp_feas = test_client.get(
        "/api/v1/scheduling/time-windows/job/JOB-001/feasible?enforce_simulation_clock=false"
    )
    assert resp_feas.status_code == 200
    feas_data = resp_feas.json()
    assert feas_data["job_id"] == "JOB-001"
    assert feas_data["is_feasible"] is True
    assert "earliest_feasible_start" in feas_data
    assert "latest_feasible_start" in feas_data
