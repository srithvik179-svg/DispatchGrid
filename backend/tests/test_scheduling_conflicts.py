from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.technician import Technician
from app.models.job import Job
from app.scheduling.conflicts import detect_scheduling_conflicts
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


def test_direct_overlap_double_booking():
    """Verify that scheduling a technician during an already booked interval triggers double-booking conflict."""
    existing = [{
        "job_id": "JOB-PREV",
        "assignment_id": 10,
        "technician_id": "T01",
        "start_time": datetime(2026, 11, 2, 10, 0, tzinfo=TZ_KOLKATA),
        "end_time": datetime(2026, 11, 2, 12, 0, tzinfo=TZ_KOLKATA),
        "status": "scheduled",
    }]

    # Proposed job overlaps from 11:00 to 13:00
    p_start = datetime(2026, 11, 2, 11, 0, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 13, 0, tzinfo=TZ_KOLKATA)

    res = detect_scheduling_conflicts(
        technician_id="T01",
        proposed_start=p_start,
        proposed_end=p_end,
        job_id="JOB-NEW",
        existing_assignments=existing,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is True
    assert res.is_eligible is False
    assert len(res.conflicts) == 1
    assert res.conflicts[0].code == "DOUBLE_BOOKING_OVERLAP"
    assert res.conflicts[0].conflicting_job_id == "JOB-PREV"


def test_in_progress_assignment_protection():
    """Verify that active in-progress assignments are strictly protected and cannot be double-booked."""
    existing = [{
        "job_id": "JOB-ACTIVE",
        "assignment_id": 11,
        "technician_id": "T05",
        "start_time": datetime(2026, 11, 2, 9, 30, tzinfo=TZ_KOLKATA),
        "end_time": datetime(2026, 11, 2, 11, 30, tzinfo=TZ_KOLKATA),
        "status": "in_progress",
    }]

    # Try scheduling over active job at 10:00 - 11:00
    p_start = datetime(2026, 11, 2, 10, 0, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 11, 0, tzinfo=TZ_KOLKATA)

    res = detect_scheduling_conflicts(
        technician_id="T05",
        proposed_start=p_start,
        proposed_end=p_end,
        job_id="JOB-NEW",
        existing_assignments=existing,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is True
    assert res.is_eligible is False
    assert any(c.code == "IN_PROGRESS_ASSIGNMENT_COLLISION" for c in res.conflicts)
    assert "in-progress" in res.summary


def test_completed_assignment_consideration():
    """Verify that retroactive appointments cannot overlap with completed assignments."""
    existing = [{
        "job_id": "JOB-DONE",
        "assignment_id": 12,
        "technician_id": "T03",
        "start_time": datetime(2026, 11, 2, 8, 0, tzinfo=TZ_KOLKATA),
        "end_time": datetime(2026, 11, 2, 9, 15, tzinfo=TZ_KOLKATA),
        "status": "completed",
    }]

    # Retroactive collision: 08:30 - 09:30
    p_start = datetime(2026, 11, 2, 8, 30, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 9, 30, tzinfo=TZ_KOLKATA)

    res = detect_scheduling_conflicts(
        technician_id="T03",
        proposed_start=p_start,
        proposed_end=p_end,
        job_id="JOB-NEW",
        existing_assignments=existing,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is True
    assert res.is_eligible is False
    assert any(c.code == "COMPLETED_ASSIGNMENT_COLLISION" for c in res.conflicts)


def test_travel_buffer_conflict_preceding_job():
    """
    Verify travel-time conflict when preceding job ends but transit time to next job
    causes technician to arrive later than proposed start.
    """
    # Preceding job at Bangalore MG Road (12.9716, 77.5946), ends at 11:00
    existing = [{
        "job_id": "JOB-01",
        "assignment_id": 21,
        "technician_id": "T02",
        "start_time": datetime(2026, 11, 2, 10, 0, tzinfo=TZ_KOLKATA),
        "end_time": datetime(2026, 11, 2, 11, 0, tzinfo=TZ_KOLKATA),
        "status": "scheduled",
        "lat": 12.9716,
        "lng": 77.5946,
    }]

    # New job at Whitefield (~15 km away, requires 30 mins travel @ 30 km/h)
    # Earliest arrival at Whitefield is 11:30.
    # Proposed start is 11:15 -> Deficit of ~15 mins!
    new_lat, new_lng = 12.9698, 77.7499

    res = detect_scheduling_conflicts(
        technician_id="T02",
        proposed_start=datetime(2026, 11, 2, 11, 15, tzinfo=TZ_KOLKATA),
        proposed_end=datetime(2026, 11, 2, 12, 15, tzinfo=TZ_KOLKATA),
        job_id="JOB-02",
        job_lat=new_lat,
        job_lng=new_lng,
        existing_assignments=existing,
        include_travel=True,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is True
    assert res.is_eligible is False
    assert any(c.code == "TRAVEL_BUFFER_CONFLICT_PRECEDING" for c in res.conflicts)
    conflict = next(c for c in res.conflicts if c.code == "TRAVEL_BUFFER_CONFLICT_PRECEDING")
    assert conflict.travel_buffer_deficit_minutes is not None
    assert conflict.travel_buffer_deficit_minutes > 10.0


def test_travel_buffer_conflict_succeeding_job():
    """
    Verify travel-time conflict when proposed job finishes so late that technician
    cannot reach the already scheduled succeeding job in time.
    """
    # Succeeding job at Whitefield starts at 14:00
    existing = [{
        "job_id": "JOB-03",
        "assignment_id": 22,
        "technician_id": "T02",
        "start_time": datetime(2026, 11, 2, 14, 0, tzinfo=TZ_KOLKATA),
        "end_time": datetime(2026, 11, 2, 15, 0, tzinfo=TZ_KOLKATA),
        "status": "scheduled",
        "lat": 12.9698,
        "lng": 77.7499,
    }]

    # Proposed job at MG Road (12.9716, 77.5946) ends at 13:45
    # Transit takes ~33 mins, arriving at ~14:18 -> Exceeds succeeding start 14:00 by 18 mins!
    res = detect_scheduling_conflicts(
        technician_id="T02",
        proposed_start=datetime(2026, 11, 2, 12, 45, tzinfo=TZ_KOLKATA),
        proposed_end=datetime(2026, 11, 2, 13, 45, tzinfo=TZ_KOLKATA),
        job_id="JOB-02",
        job_lat=12.9716,
        job_lng=77.5946,
        existing_assignments=existing,
        include_travel=True,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is True
    assert res.is_eligible is False
    assert any(c.code == "TRAVEL_BUFFER_CONFLICT_SUCCEEDING" for c in res.conflicts)


def test_adjacent_jobs_abutting_schedule_feasible():
    """Verify that adjacent jobs with zero travel (same location) or exact travel buffer are feasible."""
    # Preceding job ends at 11:00 at exact same coordinates
    existing = [{
        "job_id": "JOB-SAME-LOC",
        "assignment_id": 31,
        "technician_id": "T04",
        "start_time": datetime(2026, 11, 2, 10, 0, tzinfo=TZ_KOLKATA),
        "end_time": datetime(2026, 11, 2, 11, 0, tzinfo=TZ_KOLKATA),
        "status": "scheduled",
        "lat": 12.9716,
        "lng": 77.5946,
    }]

    # Proposed job starts at exactly 11:00 at the same location (0 km travel)
    res = detect_scheduling_conflicts(
        technician_id="T04",
        proposed_start=datetime(2026, 11, 2, 11, 0, tzinfo=TZ_KOLKATA),
        proposed_end=datetime(2026, 11, 2, 12, 0, tzinfo=TZ_KOLKATA),
        job_id="JOB-NEW",
        job_lat=12.9716,
        job_lng=77.5946,
        existing_assignments=existing,
        include_travel=True,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is False
    assert res.is_eligible is True
    assert len(res.conflicts) == 0


def test_multi_date_independence():
    """Verify that assignments scheduled on different calendar dates do not conflict."""
    existing = [{
        "job_id": "JOB-DAY-1",
        "assignment_id": 41,
        "technician_id": "T06",
        "start_time": datetime(2026, 11, 2, 10, 0, tzinfo=TZ_KOLKATA),
        "end_time": datetime(2026, 11, 2, 12, 0, tzinfo=TZ_KOLKATA),
        "status": "scheduled",
    }]

    # Proposed job is on Day 2 (2026-11-03) at the exact same hour
    p_start_day2 = datetime(2026, 11, 3, 10, 0, tzinfo=TZ_KOLKATA)
    p_end_day2 = datetime(2026, 11, 3, 12, 0, tzinfo=TZ_KOLKATA)

    res = detect_scheduling_conflicts(
        technician_id="T06",
        proposed_start=p_start_day2,
        proposed_end=p_end_day2,
        job_id="JOB-DAY-2",
        existing_assignments=existing,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is False
    assert res.is_eligible is True


def test_shift_boundary_conflict_and_overtime():
    """Verify that jobs exceeding shift boundaries without authorized overtime are rejected."""
    technician = {
        "id": "T01",
        "name": "Arjun Rao",
        "shifts": [{
            "date": "2026-11-02",
            "start": "2026-11-02T09:00:00+05:30",
            "end": "2026-11-02T18:00:00+05:30",
        }],
        "overtime": {"allowed": False, "max_minutes_per_shift": 0},
    }

    # Proposed job runs 17:30 to 18:30 (exceeds 18:00 by 30 mins)
    p_start = datetime(2026, 11, 2, 17, 30, tzinfo=TZ_KOLKATA)
    p_end = datetime(2026, 11, 2, 18, 30, tzinfo=TZ_KOLKATA)

    res = detect_scheduling_conflicts(
        technician_id="T01",
        proposed_start=p_start,
        proposed_end=p_end,
        job_id="JOB-OVERTIME",
        technician=technician,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is True
    assert any(c.code == "SHIFT_BOUNDARY_EXCEEDED" for c in res.conflicts)


def test_service_check_technician_conflicts_seeded_db(db_session):
    """Verify conflict evaluation against genuine database records for T05 who has an in-progress assignment."""
    service = SchedulingService(db_session)

    # T05 has in_progress JOB-105 from 09:30 to 11:30
    # Try scheduling T05 for JOB-001 at 10:00 to 11:00
    res = service.check_technician_conflicts(
        technician_id="T05",
        proposed_start=datetime(2026, 11, 2, 10, 0, tzinfo=TZ_KOLKATA),
        duration_minutes=60,
        enforce_simulation_clock=False,
    )
    assert res.has_conflict is True
    assert res.is_eligible is False
    assert any(c.code == "IN_PROGRESS_ASSIGNMENT_COLLISION" for c in res.conflicts)


def test_api_conflicts_check_endpoint(test_client):
    """Test POST /api/v1/scheduling/conflicts/check."""
    payload = {
        "technician_id": "T05",
        "proposed_start": "2026-11-02T10:00:00+05:30",
        "duration_minutes": 60,
        "enforce_simulation_clock": False,
    }
    resp = test_client.post("/api/v1/scheduling/conflicts/check", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["technician_id"] == "T05"
    assert data["has_conflict"] is True
    assert data["is_eligible"] is False
    assert len(data["conflicts"]) > 0


def test_api_technician_job_conflict_get_endpoint(test_client):
    """Test GET /api/v1/scheduling/conflicts/technician/{technician_id}/job/{job_id}."""
    resp = test_client.get(
        "/api/v1/scheduling/conflicts/technician/T05/job/JOB-001?enforce_simulation_clock=false"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["technician_id"] == "T05"
    assert data["job_id"] == "JOB-001"


def test_invalid_assignment_rejected_before_persistence(db_session, test_client):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Invalid assignments are strictly rejected BEFORE persistence.
    Attempting to create an assignment that conflicts with an in-progress job or creates
    a double-booking must raise ValueError / HTTP 400 and persist nothing to the database.
    """
    from app.models.assignment import Assignment
    from app.scheduling.conflicts import persist_assignment_with_conflict_check

    # T05 is busy with in-progress JOB-105 until 11:30
    initial_count = db_session.query(Assignment).count()

    # 1. Direct Python function check: Must raise ValueError
    with pytest.raises(ValueError) as exc_info:
        persist_assignment_with_conflict_check(
            db=db_session,
            job_id="JOB-001",
            technician_id="T05",
            start_time="2026-11-02T10:00:00+05:30",
            enforce_simulation_clock=False,
        )
    assert "Invalid assignment rejected before persistence" in str(exc_info.value)
    assert db_session.query(Assignment).count() == initial_count  # Nothing persisted!

    # 2. API Endpoint check: Must return HTTP 400 Bad Request
    payload = {
        "job_id": "JOB-001",
        "technician_id": "T05",
        "start_time": "2026-11-02T10:00:00+05:30",
    }
    resp = test_client.post("/api/v1/scheduling/assignments", json=payload)
    assert resp.status_code == 400
    assert "Invalid assignment rejected before persistence" in resp.json()["detail"]
    assert db_session.query(Assignment).count() == initial_count  # Still nothing persisted!

