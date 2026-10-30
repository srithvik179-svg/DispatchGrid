from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.assignment import Assignment
from app.scheduling.availability import (
    check_shift_coverage,
    check_unavailability_collision,
    evaluate_technician_availability,
    DEFAULT_OVERTIME_PENALTY_PER_MINUTE,
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


def test_check_shift_coverage_regular_hours():
    """Verify proposed work wholly within standard shift boundaries requires 0 overtime."""
    shifts = [{
        "date": "2026-11-02",
        "start": "2026-11-02T09:00:00+05:30",
        "end": "2026-11-02T18:00:00+05:30",
    }]
    ot_config = {"allowed": True, "max_minutes_per_shift": 60}

    p_start = datetime(2026, 11, 2, 10, 0, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 12, 0, tzinfo=TZ_KOLKATA)

    res = check_shift_coverage(
        proposed_start=p_start,
        proposed_end=p_end,
        shifts=shifts,
        overtime_config=ot_config,
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert res.is_available is True
    assert res.is_within_regular_shift is True
    assert res.requires_overtime is False
    assert res.overtime_minutes == 0
    assert res.overtime_penalty_cost == 0.0
    assert res.rejection_reason is None


def test_check_shift_coverage_permitted_overtime():
    """Verify permitted overtime calculation and penalty cost when configured."""
    shifts = [{
        "date": "2026-11-02",
        "start": "2026-11-02T09:00:00+05:30",
        "end": "2026-11-02T18:00:00+05:30",
    }]
    ot_config = {"allowed": True, "max_minutes_per_shift": 60}

    # Work runs until 18:45 (45 minutes overtime)
    p_start = datetime(2026, 11, 2, 17, 0, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 18, 45, tzinfo=TZ_KOLKATA)

    res = check_shift_coverage(
        proposed_start=p_start,
        proposed_end=p_end,
        shifts=shifts,
        overtime_config=ot_config,
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert res.is_available is True
    assert res.is_within_regular_shift is False
    assert res.requires_overtime is True
    assert res.overtime_minutes == 45
    assert res.overtime_penalty_cost == 45 * DEFAULT_OVERTIME_PENALTY_PER_MINUTE
    assert res.rejection_reason is None


def test_check_shift_coverage_prohibited_overtime():
    """Verify strict rejection when overtime is not permitted for the technician."""
    shifts = [{
        "date": "2026-11-02",
        "start": "2026-11-02T09:00:00+05:30",
        "end": "2026-11-02T18:00:00+05:30",
    }]
    ot_config = {"allowed": False, "max_minutes_per_shift": 0}

    p_start = datetime(2026, 11, 2, 17, 30, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 18, 15, tzinfo=TZ_KOLKATA)

    res = check_shift_coverage(
        proposed_start=p_start,
        proposed_end=p_end,
        shifts=shifts,
        overtime_config=ot_config,
        technician_id="T02",
        technician_name="Meera Nair",
    )
    assert res.is_available is False
    assert "overtime work is strictly prohibited" in res.rejection_reason


def test_check_shift_coverage_overtime_cap_exceeded():
    """Verify strict rejection when required overtime exceeds maximum technician cap."""
    shifts = [{
        "date": "2026-11-02",
        "start": "2026-11-02T09:00:00+05:30",
        "end": "2026-11-02T18:00:00+05:30",
    }]
    ot_config = {"allowed": True, "max_minutes_per_shift": 30}

    # Needs 60 mins overtime, cap is only 30
    p_start = datetime(2026, 11, 2, 17, 0, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 19, 0, tzinfo=TZ_KOLKATA)

    res = check_shift_coverage(
        proposed_start=p_start,
        proposed_end=p_end,
        shifts=shifts,
        overtime_config=ot_config,
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert res.is_available is False
    assert "exceeds the maximum shift allowance cap of 30 mins" in res.rejection_reason


def test_check_shift_coverage_multi_dates_horizon():
    """Verify shift validation across multiple planning horizon dates."""
    shifts = [
        {
            "date": "2026-11-02",
            "start": "2026-11-02T09:00:00+05:30",
            "end": "2026-11-02T18:00:00+05:30",
        },
        {
            "date": "2026-11-03",
            "start": "2026-11-03T09:00:00+05:30",
            "end": "2026-11-03T18:00:00+05:30",
        },
    ]

    # Day 1 valid
    d1_start = datetime(2026, 11, 2, 11, 0, tzinfo=TZ_KOLKATA)
    d1_end = datetime(2026, 11, 2, 13, 0, tzinfo=TZ_KOLKATA)
    res_d1 = check_shift_coverage(d1_start, d1_end, shifts=shifts)
    assert res_d1.is_available is True
    assert res_d1.matched_shift_date == "2026-11-02"

    # Day 2 valid
    d2_start = datetime(2026, 11, 3, 11, 0, tzinfo=TZ_KOLKATA)
    d2_end = datetime(2026, 11, 3, 13, 0, tzinfo=TZ_KOLKATA)
    res_d2 = check_shift_coverage(d2_start, d2_end, shifts=shifts)
    assert res_d2.is_available is True
    assert res_d2.matched_shift_date == "2026-11-03"

    # Day 3 outside shifts
    d3_start = datetime(2026, 11, 4, 11, 0, tzinfo=TZ_KOLKATA)
    d3_end = datetime(2026, 11, 4, 13, 0, tzinfo=TZ_KOLKATA)
    res_d3 = check_shift_coverage(d3_start, d3_end, shifts=shifts)
    assert res_d3.is_available is False
    assert "no scheduled shift covering start time" in res_d3.rejection_reason


def test_check_unavailability_collision():
    """Verify collision detection against technician unavailable periods."""
    unavail = [{
        "start": "2026-11-02T14:00:00+05:30",
        "end": "2026-11-02T18:00:00+05:30",
        "reason": "training",
    }]

    # 1. Overlapping window -> Conflict
    p_start = datetime(2026, 11, 2, 15, 0, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 16, 30, tzinfo=TZ_KOLKATA)
    res_conflict = check_unavailability_collision(p_start, p_end, unavailable_periods=unavail)
    assert res_conflict.is_free is False
    assert len(res_conflict.conflicts) == 1
    assert "training" in res_conflict.rejection_reason

    # 2. Abutting boundary (ends right when unavail starts) -> Free
    p_start_free = datetime(2026, 11, 2, 12, 0, tzinfo=TZ_KOLKATA)
    p_end_free = datetime(2026, 11, 2, 14, 0, tzinfo=TZ_KOLKATA)
    res_free = check_unavailability_collision(p_start_free, p_end_free, unavailable_periods=unavail)
    assert res_free.is_free is True
    assert res_free.conflicts == []


def test_simulation_clock_past_rejection():
    """Verify proposed start time earlier than authoritative simulation clock is rejected."""
    sim_clock = datetime(2026, 11, 2, 10, 0, tzinfo=TZ_KOLKATA)

    tech_dict = {
        "id": "T01",
        "name": "Arjun Rao",
        "shifts": [{
            "date": "2026-11-02",
            "start": "2026-11-02T09:00:00+05:30",
            "end": "2026-11-02T18:00:00+05:30",
        }],
        "unavailable_periods": [],
        "overtime": {"allowed": True, "max_minutes_per_shift": 60},
    }

    # Start time at 09:30 is before simulation clock (10:00)
    p_past = datetime(2026, 11, 2, 9, 30, tzinfo=TZ_KOLKATA)
    eval_past = evaluate_technician_availability(
        technician=tech_dict,
        proposed_start=p_past,
        duration_minutes=60,
        simulation_clock=sim_clock,
        enforce_simulation_clock=True,
    )
    assert eval_past.is_available is False
    assert eval_past.is_before_simulation_clock is True
    assert "earlier than current simulation clock" in eval_past.combined_rejection_reason

    # Start time at 10:30 is after simulation clock (10:00)
    p_future = datetime(2026, 11, 2, 10, 30, tzinfo=TZ_KOLKATA)
    eval_future = evaluate_technician_availability(
        technician=tech_dict,
        proposed_start=p_future,
        duration_minutes=60,
        simulation_clock=sim_clock,
        enforce_simulation_clock=True,
    )
    assert eval_future.is_available is True
    assert eval_future.is_before_simulation_clock is False


def test_invalid_duration_and_boundaries():
    """Verify invalid start/end times are rejected."""
    shifts = [{
        "date": "2026-11-02",
        "start": "2026-11-02T09:00:00+05:30",
        "end": "2026-11-02T18:00:00+05:30",
    }]
    p_start = datetime(2026, 11, 2, 12, 0, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 11, 0, tzinfo=TZ_KOLKATA)  # end before start

    res = check_shift_coverage(p_start, p_end, shifts=shifts)
    assert res.is_available is False
    assert "Proposed start timestamp must be strictly earlier" in res.rejection_reason


def test_api_availability_evaluate_endpoint(test_client):
    """Test POST /api/v1/scheduling/availability/evaluate endpoint."""
    payload = {
        "technician_id": "T01",
        "proposed_start": "2026-11-02T17:00:00+05:30",
        "duration_minutes": 90,
        "enforce_simulation_clock": True,
    }
    resp = test_client.post("/api/v1/scheduling/availability/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["technician_id"] == "T01"
    assert data["is_available"] is True
    assert data["shift_result"]["requires_overtime"] is True
    assert data["overtime_minutes"] == 30
    assert data["overtime_penalty"] == 45.0

    # Test unavailable technician T02 during training
    payload_t02 = {
        "technician_id": "T02",
        "proposed_start": "2026-11-02T15:00:00+05:30",
        "duration_minutes": 60,
    }
    resp_t02 = test_client.post("/api/v1/scheduling/availability/evaluate", json=payload_t02)
    assert resp_t02.status_code == 200
    data_t02 = resp_t02.json()
    assert data_t02["is_available"] is False
    assert data_t02["unavailability_result"]["is_free"] is False


def test_api_technician_job_availability_endpoint(test_client):
    """Test GET /api/v1/scheduling/availability/technician/{technician_id}/job/{job_id} endpoint."""
    resp = test_client.get("/api/v1/scheduling/availability/technician/T01/job/JOB-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["technician_id"] == "T01"
    assert data["job_id"] == "JOB-001"
    assert data["is_available"] is True

    # Non-existent technician
    resp_404 = test_client.get("/api/v1/scheduling/availability/technician/T99/job/JOB-001")
    assert resp_404.status_code == 404


def test_existing_scheduling_features_unaffected(test_client, db_session):
    """Verify pre-existing assignments and run initialization remain completely intact."""
    initial_assignment_count = db_session.query(Assignment).count()
    assert initial_assignment_count == 7

    resp = test_client.post("/api/v1/scheduling/runs/init")
    assert resp.status_code == 201
    data = resp.json()
    assert data["existing_assignments_preserved"] is True
    assert data["assigned_jobs_count"] == 7

    post_count = db_session.query(Assignment).count()
    assert post_count == initial_assignment_count
