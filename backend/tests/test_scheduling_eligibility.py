import pytest
from datetime import datetime, timezone
from httpx import AsyncClient

from app.services.eligibility_service import (
    validate_skills,
    validate_equipment,
    validate_zone_eligibility,
    validate_shift_availability,
    validate_unavailable_periods,
    validate_time_window,
    validate_job_technician_eligibility,
)


# --- 1. SKILLS VALIDATOR TESTS ---

def test_validate_skills_all_present():
    """Verify that when technician possesses all required skills, validator passes."""
    ok, missing, issue = validate_skills(
        required_skills=["electrical", "solar"],
        technician_skills=["electrical", "solar", "plumbing"],
    )
    assert ok is True
    assert missing == []
    assert issue is None


def test_validate_skills_missing_single_and_multiple():
    """Verify missing skills are precisely detected and reported."""
    # Single missing skill
    ok1, missing1, issue1 = validate_skills(
        required_skills=["electrical", "hvac"],
        technician_skills=["electrical"],
    )
    assert ok1 is False
    assert missing1 == ["hvac"]
    assert issue1 is not None
    assert issue1.category == "skills"
    assert "hvac" in issue1.message

    # Multiple missing skills
    ok2, missing2, issue2 = validate_skills(
        required_skills=["electrical", "hvac", "networking"],
        technician_skills=[],
    )
    assert ok2 is False
    assert set(missing2) == {"electrical", "hvac", "networking"}
    assert issue2.code == "MISSING_REQUIRED_SKILLS"


# --- 2. EQUIPMENT VALIDATOR TESTS ---

def test_validate_equipment_missing_and_present():
    """Verify that missing tools/equipment in technician's onboard kit are detected."""
    # Present
    ok_p, missing_p, _ = validate_equipment(
        required_equipment=["ladder", "multimeter"],
        technician_equipment=["ladder", "multimeter", "pipe_wrench"],
    )
    assert ok_p is True
    assert missing_p == []

    # Missing
    ok_m, missing_m, issue_m = validate_equipment(
        required_equipment=["fiber_splicer", "ladder"],
        technician_equipment=["ladder"],
    )
    assert ok_m is False
    assert missing_m == ["fiber_splicer"]
    assert issue_m.category == "equipment"
    assert "fiber_splicer" in issue_m.message


# --- 3. ZONE ELIGIBILITY VALIDATOR TESTS ---

def test_validate_zone_eligibility():
    """Verify geographical zone eligibility checking."""
    # Eligible in operating zones
    ok1, _ = validate_zone_eligibility(
        job_zone_id="Z1",
        eligible_zones=["Z1", "Z2"],
    )
    assert ok1 is True

    # Eligible via home zone
    ok2, _ = validate_zone_eligibility(
        job_zone_id="Z3",
        eligible_zones=["Z1", "Z2"],
        technician_home_zone_id="Z3",
    )
    assert ok2 is True

    # Ineligible
    ok3, issue3 = validate_zone_eligibility(
        job_zone_id="Z4",
        eligible_zones=["Z1", "Z2"],
        technician_home_zone_id="Z1",
    )
    assert ok3 is False
    assert issue3.category == "zone"
    assert issue3.code == "INELIGIBLE_ZONE"
    assert "Z4" in issue3.message


# --- 4. SHIFT AVAILABILITY & OVERTIME TESTS ---

def test_validate_shift_availability_standard_and_overtime():
    """Verify shift availability checking with overtime rules."""
    shifts = [
        {
            "date": "2026-11-02",
            "start": "2026-11-02T09:00:00+05:30",
            "end": "2026-11-02T18:00:00+05:30",
        }
    ]

    # Standard fit within shift
    ok_std, ot_std, is_ot_std, _ = validate_shift_availability(
        proposed_start=datetime.fromisoformat("2026-11-02T10:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T12:00:00+05:30"),
        shifts=shifts,
    )
    assert ok_std is True
    assert ot_std == 0
    assert is_ot_std is False

    # Overtime allowed and within cap
    ok_ot, ot_mins, is_ot, _ = validate_shift_availability(
        proposed_start=datetime.fromisoformat("2026-11-02T16:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T19:00:00+05:30"),  # 1 hour after shift
        shifts=shifts,
        overtime_config={"allowed": True, "max_minutes_per_shift": 90},
    )
    assert ok_ot is True
    assert ot_mins == 60
    assert is_ot is True

    # Overtime prohibited
    ok_prohib, _, _, issue_prohib = validate_shift_availability(
        proposed_start=datetime.fromisoformat("2026-11-02T16:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T19:00:00+05:30"),
        shifts=shifts,
        overtime_config={"allowed": False, "max_minutes_per_shift": 0},
    )
    assert ok_prohib is False
    assert issue_prohib.code == "OVERTIME_PROHIBITED"

    # Overtime limit exceeded
    ok_exceed, _, _, issue_exceed = validate_shift_availability(
        proposed_start=datetime.fromisoformat("2026-11-02T16:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T19:00:00+05:30"),
        shifts=shifts,
        overtime_config={"allowed": True, "max_minutes_per_shift": 30},
    )
    assert ok_exceed is False
    assert issue_exceed.code == "OVERTIME_LIMIT_EXCEEDED"

    # Outside scheduled shift completely
    ok_out, _, _, issue_out = validate_shift_availability(
        proposed_start=datetime.fromisoformat("2026-11-02T06:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T08:00:00+05:30"),
        shifts=shifts,
    )
    assert ok_out is False
    assert issue_out.code == "OUTSIDE_SCHEDULED_SHIFT"


# --- 5. UNAVAILABLE PERIODS TESTS ---

def test_validate_unavailable_periods_collision():
    """Verify detection of collisions with pre-scheduled technician leaves/breaks."""
    unavail = [
        {
            "start": "2026-11-02T14:00:00+05:30",
            "end": "2026-11-02T16:00:00+05:30",
            "reason": "safety_training",
        }
    ]

    # Colliding interval
    ok_col, conflicts, issue_col = validate_unavailable_periods(
        proposed_start=datetime.fromisoformat("2026-11-02T13:30:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T15:00:00+05:30"),
        unavailable_periods=unavail,
    )
    assert ok_col is False
    assert len(conflicts) == 1
    assert issue_col.code == "UNAVAILABLE_PERIOD_CONFLICT"
    assert "safety_training" in issue_col.message

    # Clean non-colliding interval
    ok_clean, conflicts_clean, issue_clean = validate_unavailable_periods(
        proposed_start=datetime.fromisoformat("2026-11-02T10:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T12:00:00+05:30"),
        unavailable_periods=unavail,
    )
    assert ok_clean is True
    assert conflicts_clean == []
    assert issue_clean is None


# --- 6. TIME WINDOW & DURATION TESTS ---

def test_validate_time_window_boundaries():
    """Verify hard start/end time window boundary enforcement and duration matching."""
    w_start = datetime.fromisoformat("2026-11-02T10:00:00+05:30")
    w_end = datetime.fromisoformat("2026-11-02T14:00:00+05:30")

    # Start before window
    ok1, issue1 = validate_time_window(
        proposed_start=datetime.fromisoformat("2026-11-02T09:30:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T11:30:00+05:30"),
        window_start=w_start,
        window_end=w_end,
    )
    assert ok1 is False
    assert issue1.code == "START_BEFORE_WINDOW_START"

    # End after window
    ok2, issue2 = validate_time_window(
        proposed_start=datetime.fromisoformat("2026-11-02T13:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T15:00:00+05:30"),
        window_start=w_start,
        window_end=w_end,
    )
    assert ok2 is False
    assert issue2.code == "END_AFTER_WINDOW_END"

    # Duration mismatch
    ok3, issue3 = validate_time_window(
        proposed_start=datetime.fromisoformat("2026-11-02T10:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T12:00:00+05:30"),  # 120 mins
        window_start=w_start,
        window_end=w_end,
        duration_minutes=60,  # Expected 60 mins
    )
    assert ok3 is False
    assert issue3.code == "DURATION_MISMATCH"


# --- 7. COMPOSITE MULTI-FAILURE REPORTING TESTS ---

def test_composite_validator_multiple_simultaneous_failures():
    """Verify that multiple validation failures across all dimensions are simultaneously captured."""
    result = validate_job_technician_eligibility(
        job_skills=["elevator", "high_voltage"],
        job_equipment=["elevator_rig"],
        job_zone_id="Z5",
        technician_skills=["plumbing"],
        technician_equipment=["pipe_wrench"],
        technician_eligible_zones=["Z1"],
        technician_home_zone_id="Z1",
        proposed_start=datetime.fromisoformat("2026-11-02T10:00:00+05:30"),
        proposed_end=datetime.fromisoformat("2026-11-02T12:00:00+05:30"),
        technician_shifts=[
            {
                "date": "2026-11-02",
                "start": "2026-11-02T09:00:00+05:30",
                "end": "2026-11-02T18:00:00+05:30",
            }
        ],
        technician_unavailable_periods=[
            {
                "start": "2026-11-02T10:00:00+05:30",
                "end": "2026-11-02T13:00:00+05:30",
                "reason": "medical_leave",
            }
        ],
        job_time_window_start=datetime.fromisoformat("2026-11-02T10:00:00+05:30"),
        job_time_window_end=datetime.fromisoformat("2026-11-02T14:00:00+05:30"),
        job_duration_minutes=120,
    )

    # Acceptance criteria: multiple validation failures reported together
    assert result.is_eligible is False
    assert len(result.issues) >= 4
    assert len(result.reasons) >= 4
    assert result.missing_skills == ["elevator", "high_voltage"]
    assert result.missing_equipment == ["elevator_rig"]
    assert result.zone_eligible is False
    assert result.unavailable_conflict is True

    categories = [i.category for i in result.issues]
    assert "skills" in categories
    assert "equipment" in categories
    assert "zone" in categories
    assert "unavailable" in categories


# --- 8. API INTEGRATION TEST ---

@pytest.mark.anyio
async def test_api_scheduling_validate_eligibility_with_db_records(client: AsyncClient):
    """Verify HTTP endpoint evaluates live database records and returns structured report."""
    # JOB-001 requires networking, fiber_splicer, zone Z3
    # T01 has electrical, solar, ladder, multimeter, zone Z1/Z2
    res = await client.post(
        "/api/v1/scheduling/validate-eligibility",
        json={
            "job_id": "JOB-001",
            "technician_id": "T01",
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert data["is_eligible"] is False
    assert "networking" in data["missing_skills"]
    assert "fiber_splicer" in data["missing_equipment"]
    assert data["zone_eligible"] is False
    assert len(data["reasons"]) >= 3
    assert len(data["issues"]) >= 3
