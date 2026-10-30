from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List

from app.models.technician import Technician
from app.schemas.technician import TechnicianResponse
from app.scheduling.schemas import (
    ShiftAvailabilityResult,
    UnavailabilityCheckResult,
    TechnicianAvailabilityEvaluation,
)

DEFAULT_OVERTIME_PENALTY_PER_MINUTE = 1.5


def parse_datetime_safe(val: Any) -> Optional[datetime]:
    """
    Safely parse ISO datetime string or ensure existing datetime is timezone-aware.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    try:
        s = str(val).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def check_shift_coverage(
    proposed_start: datetime,
    proposed_end: datetime,
    shifts: Sequence[Dict[str, Any]],
    overtime_config: Optional[Dict[str, Any]] = None,
    technician_id: str = "",
    technician_name: Optional[str] = None,
    overtime_penalty_rate: float = DEFAULT_OVERTIME_PENALTY_PER_MINUTE,
) -> ShiftAvailabilityResult:
    """
    Validates that a proposed working interval fits within a scheduled technician shift,
    supporting multi-shift calendars, multi-date horizons, and strictly controlled overtime.
    """
    p_start = parse_datetime_safe(proposed_start)
    p_end = parse_datetime_safe(proposed_end)

    tech_display = f"Technician {technician_name or technician_id}"

    if not p_start or not p_end or p_end <= p_start:
        return ShiftAvailabilityResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_available=False,
            proposed_start=p_start or datetime.now(timezone.utc),
            proposed_end=p_end or datetime.now(timezone.utc),
            rejection_reason="Proposed start timestamp must be strictly earlier than proposed end timestamp.",
        )

    if not shifts:
        return ShiftAvailabilityResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_available=False,
            proposed_start=p_start,
            proposed_end=p_end,
            rejection_reason=f"{tech_display} has no scheduled working shifts configured.",
        )

    # Resolve overtime policy
    ot_allowed = False
    ot_max_mins = 0
    if overtime_config:
        ot_allowed = bool(overtime_config.get("allowed", False))
        ot_max_mins = int(overtime_config.get("max_minutes_per_shift", 0) or 0)

    best_rejection: Optional[str] = None
    shift_matched = False

    for shift in shifts:
        s_start = parse_datetime_safe(shift.get("start"))
        s_end = parse_datetime_safe(shift.get("end"))
        s_date = str(shift.get("date", ""))

        if not s_start or not s_end:
            continue

        # Check if the proposed start fits inside this shift
        if s_start <= p_start < s_end or (s_start <= p_start and p_start < (s_end + timedelta(minutes=ot_max_mins))):
            shift_matched = True

            # Case 1: Wholly contained in standard shift boundaries
            if p_end <= s_end:
                return ShiftAvailabilityResult(
                    technician_id=technician_id,
                    technician_name=technician_name,
                    is_available=True,
                    proposed_start=p_start,
                    proposed_end=p_end,
                    matched_shift_date=s_date,
                    is_within_regular_shift=True,
                    requires_overtime=False,
                    overtime_minutes=0,
                    is_overtime_permitted=ot_allowed,
                    max_overtime_minutes=ot_max_mins,
                    overtime_penalty_cost=0.0,
                    rejection_reason=None,
                )

            # Case 2: Exceeds standard shift end -> Requires overtime
            overtime_needed = int(round((p_end - s_end).total_seconds() / 60.0))

            if ot_allowed and overtime_needed <= ot_max_mins:
                penalty_cost = round(overtime_needed * overtime_penalty_rate, 2)
                return ShiftAvailabilityResult(
                    technician_id=technician_id,
                    technician_name=technician_name,
                    is_available=True,
                    proposed_start=p_start,
                    proposed_end=p_end,
                    matched_shift_date=s_date,
                    is_within_regular_shift=False,
                    requires_overtime=True,
                    overtime_minutes=overtime_needed,
                    is_overtime_permitted=True,
                    max_overtime_minutes=ot_max_mins,
                    overtime_penalty_cost=penalty_cost,
                    rejection_reason=None,
                )
            elif not ot_allowed:
                best_rejection = (
                    f"{tech_display} service ends {overtime_needed} mins after scheduled shift end "
                    f"({s_end.strftime('%H:%M')}) and overtime work is strictly prohibited."
                )
            else:
                best_rejection = (
                    f"{tech_display} requires {overtime_needed} mins of overtime which exceeds "
                    f"the maximum shift allowance cap of {ot_max_mins} mins."
                )

    if not shift_matched:
        best_rejection = (
            f"{tech_display} has no scheduled shift covering start time "
            f"{p_start.strftime('%Y-%m-%d %H:%M')}."
        )

    return ShiftAvailabilityResult(
        technician_id=technician_id,
        technician_name=technician_name,
        is_available=False,
        proposed_start=p_start,
        proposed_end=p_end,
        requires_overtime=False,
        overtime_minutes=0,
        is_overtime_permitted=ot_allowed,
        max_overtime_minutes=ot_max_mins,
        overtime_penalty_cost=0.0,
        rejection_reason=best_rejection,
    )


def check_unavailability_collision(
    proposed_start: datetime,
    proposed_end: datetime,
    unavailable_periods: Sequence[Dict[str, Any]],
    technician_id: str = "",
    technician_name: Optional[str] = None,
) -> UnavailabilityCheckResult:
    """
    Validates that proposed job interval does not collide with scheduled technician leaves,
    breaks, or maintenance windows. Abutting intervals (end == start) do NOT collide.
    """
    p_start = parse_datetime_safe(proposed_start)
    p_end = parse_datetime_safe(proposed_end)

    tech_display = f"Technician {technician_name or technician_id}"

    if not p_start or not p_end or not unavailable_periods:
        return UnavailabilityCheckResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_free=True,
            conflicts=[],
            rejection_reason=None,
        )

    conflicts: List[Dict[str, Any]] = []

    for period in unavailable_periods:
        u_start = parse_datetime_safe(period.get("start"))
        u_end = parse_datetime_safe(period.get("end"))
        reason = period.get("reason", "unavailable")

        if not u_start or not u_end:
            continue

        # Strict open-interval overlap: max(start) < min(end)
        if max(p_start, u_start) < min(p_end, u_end):
            conflicts.append({
                "start": u_start.isoformat(),
                "end": u_end.isoformat(),
                "reason": reason,
            })

    if conflicts:
        conflict_desc = [
            f"{c['reason']} ({c['start']} to {c['end']})" for c in conflicts
        ]
        rejection = (
            f"{tech_display} is unavailable due to scheduled period(s): {'; '.join(conflict_desc)}."
        )
        return UnavailabilityCheckResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_free=False,
            conflicts=conflicts,
            rejection_reason=rejection,
        )

    return UnavailabilityCheckResult(
        technician_id=technician_id,
        technician_name=technician_name,
        is_free=True,
        conflicts=[],
        rejection_reason=None,
    )


def evaluate_technician_availability(
    technician: Union[Technician, TechnicianResponse, Dict[str, Any]],
    proposed_start: datetime,
    duration_minutes: int,
    proposed_end: Optional[datetime] = None,
    job_id: Optional[str] = None,
    simulation_clock: Optional[datetime] = None,
    enforce_simulation_clock: bool = True,
    overtime_penalty_rate: float = DEFAULT_OVERTIME_PENALTY_PER_MINUTE,
) -> TechnicianAvailabilityEvaluation:
    """
    Consolidated availability evaluation verifying:
      1. Respects simulation reference clock (cannot schedule in the past).
      2. Fits within scheduled shifts (supporting multiple dates & permitted overtime).
      3. Avoids all scheduled unavailable intervals.
    """
    if isinstance(technician, dict):
        t_id = technician.get("id", "")
        t_name = technician.get("name", t_id)
        t_shifts = technician.get("shifts", [])
        t_unavail = technician.get("unavailable_periods", [])
        t_ot = technician.get("overtime", {})
    else:
        t_id = getattr(technician, "id", "")
        t_name = getattr(technician, "name", t_id)
        t_shifts = getattr(technician, "shifts", []) or []
        t_unavail = getattr(technician, "unavailable_periods", []) or []
        t_ot = getattr(technician, "overtime", None)
        if isinstance(t_ot, dict):
            pass
        elif t_ot is not None:
            t_ot = {"allowed": getattr(t_ot, "allowed", False), "max_minutes_per_shift": getattr(t_ot, "max_minutes_per_shift", 0)}
        else:
            t_ot = {"allowed": False, "max_minutes_per_shift": 0}

    p_start = parse_datetime_safe(proposed_start)
    if not p_start:
        p_start = datetime.now(timezone.utc)

    if proposed_end:
        p_end = parse_datetime_safe(proposed_end)
    else:
        p_end = p_start + timedelta(minutes=duration_minutes)

    failures: List[str] = []
    is_before_clock = False

    # 1. Simulation Clock Check
    sim_clock = parse_datetime_safe(simulation_clock)
    if enforce_simulation_clock and sim_clock and p_start < sim_clock:
        is_before_clock = True
        failures.append(
            f"Proposed start time ({p_start.isoformat()}) is earlier than current simulation clock ({sim_clock.isoformat()})."
        )

    # 2. Shift Coverage Check
    shift_res = check_shift_coverage(
        proposed_start=p_start,
        proposed_end=p_end,
        shifts=t_shifts,
        overtime_config=t_ot,
        technician_id=t_id,
        technician_name=t_name,
        overtime_penalty_rate=overtime_penalty_rate,
    )
    if not shift_res.is_available and shift_res.rejection_reason:
        failures.append(shift_res.rejection_reason)

    # 3. Unavailability Check
    unavail_res = check_unavailability_collision(
        proposed_start=p_start,
        proposed_end=p_end,
        unavailable_periods=t_unavail,
        technician_id=t_id,
        technician_name=t_name,
    )
    if not unavail_res.is_free and unavail_res.rejection_reason:
        failures.append(unavail_res.rejection_reason)

    is_overall_available = (not is_before_clock) and shift_res.is_available and unavail_res.is_free
    combined_reason = " | ".join(failures) if failures else None

    return TechnicianAvailabilityEvaluation(
        technician_id=t_id,
        technician_name=t_name,
        job_id=job_id,
        is_available=is_overall_available,
        shift_result=shift_res,
        unavailability_result=unavail_res,
        is_before_simulation_clock=is_before_clock,
        proposed_start=p_start,
        proposed_end=p_end,
        duration_minutes=duration_minutes,
        overtime_minutes=shift_res.overtime_minutes,
        overtime_penalty=shift_res.overtime_penalty_cost,
        failure_reasons=failures,
        combined_rejection_reason=combined_reason,
    )
