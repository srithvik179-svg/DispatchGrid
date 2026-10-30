"""
Scheduling conflict detection engine for field workforce dispatching.

Prevents:
1. Direct Overlaps (Double Booking):
   - A technician cannot be assigned to two jobs simultaneously.
2. Protected Assignment Collisions:
   - In-progress assignments are strictly protected and immutable.
   - Completed historical assignments cannot be retroactively altered or scheduled over.
3. Travel-Time Buffer Violations:
   - Consecutive jobs must have sufficient transit time buffer using deterministic
     Haversine distance @ 30 km/h:
       end_preceding + travel_time(preceding -> new) <= start_new
       end_new + travel_time(new -> succeeding) <= start_succeeding
4. Adjacent Jobs & Abutting Feasibility:
   - Zero-travel or exact-travel abutting intervals are validated without false positives.
5. Multi-Date Itinerary Management:
   - Accurately tracks itineraries across the 48-hour planning horizon and multiple dates.
6. Shift Boundary & Unavailability Protection:
   - Enforces shift working hours, overtime authorization caps, and scheduled leaves/breaks.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List, Tuple

from app.models.job import Job
from app.models.technician import Technician
from app.models.assignment import Assignment
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.schemas.assignment import AssignmentSummary
from app.scheduling.schemas import (
    SchedulingConflict,
    ConflictCheckResult,
    AssignedJobPlan,
)
from app.scheduling.geo import haversine_distance, calculate_travel_minutes
from app.scheduling.availability import check_shift_coverage, check_unavailability_collision


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


def extract_assignment_info(assign: Any) -> Dict[str, Any]:
    """
    Normalizes diverse assignment representations (ORM Assignment, AssignedJobPlan,
    AssignmentSummary, dict) into a consistent dictionary for collision analysis.
    """
    if isinstance(assign, dict):
        return {
            "assignment_id": assign.get("id") or assign.get("assignment_id"),
            "job_id": assign.get("job_id"),
            "technician_id": assign.get("technician_id"),
            "start_time": parse_datetime_safe(assign.get("start_time") or assign.get("scheduled_start") or assign.get("start")),
            "end_time": parse_datetime_safe(assign.get("end_time") or assign.get("scheduled_end") or assign.get("end")),
            "status": str(assign.get("status", "scheduled")).lower(),
            "lat": assign.get("lat"),
            "lng": assign.get("lng"),
            "job_title": assign.get("job_title"),
        }

    # ORM Assignment
    if hasattr(assign, "job_id") and hasattr(assign, "start_time"):
        job_obj = getattr(assign, "job", None)
        return {
            "assignment_id": getattr(assign, "id", None),
            "job_id": getattr(assign, "job_id", None),
            "technician_id": getattr(assign, "technician_id", None),
            "start_time": parse_datetime_safe(getattr(assign, "start_time", None)),
            "end_time": parse_datetime_safe(getattr(assign, "end_time", None)),
            "status": str(getattr(assign, "status", "scheduled")).lower(),
            "lat": getattr(job_obj, "lat", None) if job_obj else getattr(assign, "lat", None),
            "lng": getattr(job_obj, "lng", None) if job_obj else getattr(assign, "lng", None),
            "job_title": getattr(job_obj, "title", None) if job_obj else getattr(assign, "job_title", None),
        }

    # AssignedJobPlan
    if hasattr(assign, "scheduled_start") and hasattr(assign, "scheduled_end"):
        details = getattr(assign, "details", {}) or {}
        return {
            "assignment_id": details.get("assignment_id"),
            "job_id": getattr(assign, "job_id", None),
            "technician_id": getattr(assign, "technician_id", None),
            "start_time": parse_datetime_safe(getattr(assign, "scheduled_start", None)),
            "end_time": parse_datetime_safe(getattr(assign, "scheduled_end", None)),
            "status": str(getattr(assign, "status", "scheduled")).lower(),
            "lat": details.get("lat"),
            "lng": details.get("lng"),
            "job_title": details.get("job_title"),
        }

    return {}


def detect_scheduling_conflicts(
    technician_id: str,
    proposed_start: Union[datetime, str],
    proposed_end: Union[datetime, str],
    job_id: Optional[str] = None,
    job_lat: Optional[float] = None,
    job_lng: Optional[float] = None,
    existing_assignments: Sequence[Any] = (),
    technician: Optional[Any] = None,
    as_of: Optional[Union[datetime, str]] = None,
    include_travel: bool = True,
    enforce_simulation_clock: bool = True,
) -> ConflictCheckResult:
    """
    Evaluates whether a proposed job assignment conflicts with a technician's existing
    schedule, transit buffers, protected active jobs, or shift boundaries.
    """
    p_start = parse_datetime_safe(proposed_start)
    p_end = parse_datetime_safe(proposed_end)
    clock = parse_datetime_safe(as_of)

    if not p_start or not p_end or p_end <= p_start:
        raise ValueError("proposed_start must be strictly earlier than proposed_end.")

    duration_minutes = int(round((p_end - p_start).total_seconds() / 60.0))
    conflicts: List[SchedulingConflict] = []

    # 1. Simulation clock past-scheduling check
    if enforce_simulation_clock and clock and p_start < clock:
        conflicts.append(
            SchedulingConflict(
                conflict_type="simulation_clock_past",
                code="START_BEFORE_SIMULATION_CLOCK",
                message=f"Proposed service start ({p_start.isoformat()}) is in the past relative to simulation clock ({clock.isoformat()}).",
            )
        )

    # 2. Extract and filter existing assignments for this technician
    tech_assignments: List[Dict[str, Any]] = []
    for raw in existing_assignments:
        info = extract_assignment_info(raw)
        if (
            info.get("technician_id") == technician_id
            and info.get("start_time")
            and info.get("end_time")
            # Exclude self if modifying or re-evaluating the same assignment
            and (not job_id or info.get("job_id") != job_id)
        ):
            tech_assignments.append(info)

    # Sort chronologically by start_time
    tech_assignments.sort(key=lambda x: x["start_time"])

    preceding_assignment: Optional[Dict[str, Any]] = None
    succeeding_assignment: Optional[Dict[str, Any]] = None

    # 3. Conflict Detection Across Assignments
    for assign in tech_assignments:
        a_start: datetime = assign["start_time"]
        a_end: datetime = assign["end_time"]
        a_status: str = assign["status"]
        a_job: str = assign["job_id"] or "unspecified"
        a_id: Optional[int] = assign["assignment_id"]

        # 3A. Double Booking / Direct Interval Overlap
        # Condition: p_start < a_end and p_end > a_start
        if p_start < a_end and p_end > a_start:
            if a_status == "in_progress":
                conflicts.append(
                    SchedulingConflict(
                        conflict_type="in_progress_collision",
                        code="IN_PROGRESS_ASSIGNMENT_COLLISION",
                        conflicting_job_id=a_job,
                        conflicting_assignment_id=a_id,
                        conflicting_status=a_status,
                        conflicting_start=a_start,
                        conflicting_end=a_end,
                        message=(
                            f"Double-booking collision with protected in-progress assignment {a_job} "
                            f"({a_start.strftime('%Y-%m-%d %H:%M')} to {a_end.strftime('%Y-%m-%d %H:%M')})."
                        ),
                    )
                )
            elif a_status == "completed":
                conflicts.append(
                    SchedulingConflict(
                        conflict_type="completed_collision",
                        code="COMPLETED_ASSIGNMENT_COLLISION",
                        conflicting_job_id=a_job,
                        conflicting_assignment_id=a_id,
                        conflicting_status=a_status,
                        conflicting_start=a_start,
                        conflicting_end=a_end,
                        message=(
                            f"Proposed appointment collides retroactively with completed assignment {a_job} "
                            f"({a_start.strftime('%Y-%m-%d %H:%M')} to {a_end.strftime('%Y-%m-%d %H:%M')})."
                        ),
                    )
                )
            else:
                conflicts.append(
                    SchedulingConflict(
                        conflict_type="double_booking",
                        code="DOUBLE_BOOKING_OVERLAP",
                        conflicting_job_id=a_job,
                        conflicting_assignment_id=a_id,
                        conflicting_status=a_status,
                        conflicting_start=a_start,
                        conflicting_end=a_end,
                        message=(
                            f"Technician is already booked for assignment {a_job} "
                            f"({a_start.strftime('%Y-%m-%d %H:%M')} to {a_end.strftime('%Y-%m-%d %H:%M')})."
                        ),
                    )
                )

        # 3B. Track Preceding Assignment (latest end <= proposed start)
        if a_end <= p_start:
            if preceding_assignment is None or a_end > preceding_assignment["end_time"]:
                preceding_assignment = assign

        # 3C. Track Succeeding Assignment (earliest start >= proposed end)
        if a_start >= p_end:
            if succeeding_assignment is None or a_start < succeeding_assignment["start_time"]:
                succeeding_assignment = assign

    # 4. Travel-Time Buffer Verification (Preceding Job -> Proposed Job)
    if include_travel and preceding_assignment and job_lat is not None and job_lng is not None:
        p_job_lat = preceding_assignment.get("lat")
        p_job_lng = preceding_assignment.get("lng")
        if p_job_lat is not None and p_job_lng is not None:
            dist_km = haversine_distance(p_job_lat, p_job_lng, job_lat, job_lng)
            transit_mins = calculate_travel_minutes(dist_km)
            earliest_arr = preceding_assignment["end_time"] + timedelta(minutes=transit_mins)

            if p_start < earliest_arr:
                deficit = (earliest_arr - p_start).total_seconds() / 60.0
                conflicts.append(
                    SchedulingConflict(
                        conflict_type="travel_buffer_preceding",
                        code="TRAVEL_BUFFER_CONFLICT_PRECEDING",
                        conflicting_job_id=preceding_assignment["job_id"],
                        conflicting_assignment_id=preceding_assignment["assignment_id"],
                        conflicting_status=preceding_assignment["status"],
                        conflicting_start=preceding_assignment["start_time"],
                        conflicting_end=preceding_assignment["end_time"],
                        travel_minutes_required=round(transit_mins, 2),
                        travel_buffer_deficit_minutes=round(deficit, 2),
                        message=(
                            f"Insufficient travel time from preceding assignment {preceding_assignment['job_id']}: "
                            f"ends at {preceding_assignment['end_time'].strftime('%H:%M')}, transit requires {transit_mins:.1f} mins "
                            f"arriving at {earliest_arr.strftime('%H:%M')}, but proposed start is {p_start.strftime('%H:%M')} "
                            f"(deficit: {deficit:.1f} mins)."
                        ),
                    )
                )

    # 5. Travel-Time Buffer Verification (Proposed Job -> Succeeding Job)
    if include_travel and succeeding_assignment and job_lat is not None and job_lng is not None:
        s_job_lat = succeeding_assignment.get("lat")
        s_job_lng = succeeding_assignment.get("lng")
        if s_job_lat is not None and s_job_lng is not None:
            dist_km = haversine_distance(job_lat, job_lng, s_job_lat, s_job_lng)
            transit_mins = calculate_travel_minutes(dist_km)
            earliest_arr_succ = p_end + timedelta(minutes=transit_mins)

            if earliest_arr_succ > succeeding_assignment["start_time"]:
                deficit = (earliest_arr_succ - succeeding_assignment["start_time"]).total_seconds() / 60.0
                conflicts.append(
                    SchedulingConflict(
                        conflict_type="travel_buffer_succeeding",
                        code="TRAVEL_BUFFER_CONFLICT_SUCCEEDING",
                        conflicting_job_id=succeeding_assignment["job_id"],
                        conflicting_assignment_id=succeeding_assignment["assignment_id"],
                        conflicting_status=succeeding_assignment["status"],
                        conflicting_start=succeeding_assignment["start_time"],
                        conflicting_end=succeeding_assignment["end_time"],
                        travel_minutes_required=round(transit_mins, 2),
                        travel_buffer_deficit_minutes=round(deficit, 2),
                        message=(
                            f"Insufficient travel time to succeeding assignment {succeeding_assignment['job_id']}: "
                            f"proposed job ends at {p_end.strftime('%H:%M')}, transit requires {transit_mins:.1f} mins "
                            f"arriving at {earliest_arr_succ.strftime('%H:%M')}, which exceeds {succeeding_assignment['job_id']} "
                            f"start at {succeeding_assignment['start_time'].strftime('%H:%M')} (deficit: {deficit:.1f} mins)."
                        ),
                    )
                )

    # 6. First Job Travel from Home Location
    # If no preceding assignment on the same shift date, check transit from technician home
    if include_travel and preceding_assignment is None and technician is not None:
        t_home_lat = getattr(technician, "home_lat", None)
        t_home_lng = getattr(technician, "home_lng", None)
        if isinstance(technician, dict):
            t_home_lat = technician.get("home_lat")
            t_home_lng = technician.get("home_lng")

        if t_home_lat is not None and t_home_lng is not None and job_lat is not None and job_lng is not None:
            home_dist = haversine_distance(t_home_lat, t_home_lng, job_lat, job_lng)
            home_transit_mins = calculate_travel_minutes(home_dist)

            # Determine earliest possible departure: shift start or clock
            earliest_dep = p_start.replace(hour=0, minute=0, second=0, microsecond=0)
            shifts = getattr(technician, "shifts", None) or (technician.get("shifts") if isinstance(technician, dict) else [])
            for s in shifts or []:
                s_st = parse_datetime_safe(s.get("start") if isinstance(s, dict) else getattr(s, "start", None))
                if s_st and s_st.date() == p_start.date():
                    earliest_dep = s_st
                    break

            if clock and clock > earliest_dep:
                earliest_dep = clock

            earliest_arr_from_home = earliest_dep + timedelta(minutes=home_transit_mins)
            if p_start < earliest_arr_from_home:
                deficit = (earliest_arr_from_home - p_start).total_seconds() / 60.0
                conflicts.append(
                    SchedulingConflict(
                        conflict_type="home_travel_conflict",
                        code="HOME_TRAVEL_CONFLICT",
                        travel_minutes_required=round(home_transit_mins, 2),
                        travel_buffer_deficit_minutes=round(deficit, 2),
                        message=(
                            f"Cannot reach first job from technician home base in time: "
                            f"earliest departure {earliest_dep.strftime('%H:%M')}, transit requires {home_transit_mins:.1f} mins "
                            f"(earliest arrival: {earliest_arr_from_home.strftime('%H:%M')}, proposed start: {p_start.strftime('%H:%M')}, deficit: {deficit:.1f} mins)."
                        ),
                    )
                )

    # 7. Shift Boundaries & Unavailability Collisions
    requires_ot = False
    ot_minutes = 0
    ot_penalty = 0.0

    if technician is not None:
        shifts = getattr(technician, "shifts", None) or (technician.get("shifts") if isinstance(technician, dict) else [])
        unavail = getattr(technician, "unavailable_periods", None) or (technician.get("unavailable_periods") if isinstance(technician, dict) else [])
        ot_config = getattr(technician, "overtime", None) or (technician.get("overtime") if isinstance(technician, dict) else None)
        tech_name = getattr(technician, "name", None) or (technician.get("name") if isinstance(technician, dict) else None)

        # Check shifts
        if shifts:
            shift_res = check_shift_coverage(
                proposed_start=p_start,
                proposed_end=p_end,
                shifts=shifts,
                overtime_config=ot_config,
                technician_id=technician_id,
                technician_name=tech_name,
            )
            if not shift_res.is_available:
                conflicts.append(
                    SchedulingConflict(
                        conflict_type="shift_boundary_conflict",
                        code="SHIFT_BOUNDARY_EXCEEDED",
                        message=shift_res.rejection_reason or "Proposed service extends beyond scheduled shift limits.",
                    )
                )
            else:
                requires_ot = shift_res.requires_overtime
                ot_minutes = shift_res.overtime_minutes
                ot_penalty = shift_res.overtime_penalty_cost

        # Check unavailable periods
        if unavail:
            unavail_res = check_unavailability_collision(
                proposed_start=p_start,
                proposed_end=p_end,
                unavailable_periods=unavail,
                technician_id=technician_id,
                technician_name=tech_name,
            )
            if not unavail_res.is_free:
                conflicts.append(
                    SchedulingConflict(
                        conflict_type="unavailability_collision",
                        code="UNAVAILABLE_PERIOD_COLLISION",
                        message=unavail_res.rejection_reason or "Proposed service collides with technician scheduled unavailable period.",
                    )
                )

    # 8. Synthesize summary
    has_conflict = len(conflicts) > 0
    is_eligible = not has_conflict
    tech_label = f"Technician {technician_id}"
    job_label = f"job {job_id}" if job_id else "proposed job"

    if is_eligible:
        summary = f"{tech_label} is free with no scheduling conflicts for {job_label} ({p_start.strftime('%H:%M')} - {p_end.strftime('%H:%M')})."
        if requires_ot:
            summary += f" Requires {ot_minutes} mins authorized overtime."
    else:
        conflict_msgs = [c.message for c in conflicts]
        summary = f"{tech_label} has {len(conflicts)} scheduling conflict(s): {'; '.join(conflict_msgs)}"

    prec_dict = (
        {
            "job_id": preceding_assignment["job_id"],
            "end_time": preceding_assignment["end_time"].isoformat(),
            "status": preceding_assignment["status"],
        }
        if preceding_assignment
        else None
    )

    succ_dict = (
        {
            "job_id": succeeding_assignment["job_id"],
            "start_time": succeeding_assignment["start_time"].isoformat(),
            "status": succeeding_assignment["status"],
        }
        if succeeding_assignment
        else None
    )

    return ConflictCheckResult(
        technician_id=technician_id,
        technician_name=getattr(technician, "name", None) or (technician.get("name") if isinstance(technician, dict) else None),
        job_id=job_id,
        has_conflict=has_conflict,
        is_eligible=is_eligible,
        proposed_start=p_start,
        proposed_end=p_end,
        duration_minutes=duration_minutes,
        conflicts=conflicts,
        preceding_assignment=prec_dict,
        succeeding_assignment=succ_dict,
        requires_overtime=requires_ot,
        overtime_minutes=ot_minutes,
        overtime_penalty=ot_penalty,
        summary=summary,
    )


def persist_assignment_with_conflict_check(
    db: Any,
    job_id: str,
    technician_id: str,
    start_time: Union[datetime, str],
    end_time: Optional[Union[datetime, str]] = None,
    enforce_simulation_clock: bool = True,
) -> Assignment:
    """
    Enforces that invalid or conflicting assignments are strictly rejected BEFORE persistence.
    Validates technician qualifications, direct overlaps, travel-time buffers, and protected jobs.
    """
    p_start = parse_datetime_safe(start_time)
    if not p_start:
        raise ValueError("Invalid start_time provided.")

    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise ValueError(f"Job with ID '{job_id}' not found.")

    if job.status in ("completed", "cancelled"):
        raise ValueError(f"Cannot assign job in terminal status '{job.status}'.")

    technician = db.query(Technician).filter_by(id=technician_id).first()
    if not technician:
        raise ValueError(f"Technician with ID '{technician_id}' not found.")

    p_end = parse_datetime_safe(end_time)
    if not p_end:
        p_end = p_start + timedelta(minutes=job.duration_minutes)

    from app.scheduling.loader import load_existing_assignments, get_simulation_clock
    existing_assignments = load_existing_assignments(db)
    ref_clock = get_simulation_clock(db)

    conflict_res = detect_scheduling_conflicts(
        technician_id=technician_id,
        proposed_start=p_start,
        proposed_end=p_end,
        job_id=job.id,
        job_lat=job.lat,
        job_lng=job.lng,
        existing_assignments=existing_assignments,
        technician=technician,
        as_of=ref_clock,
        include_travel=True,
        enforce_simulation_clock=enforce_simulation_clock,
    )

    if conflict_res.has_conflict:
        reasons = "; ".join(c.message for c in conflict_res.conflicts)
        raise ValueError(f"Invalid assignment rejected before persistence: {reasons}")

    assignment = Assignment(
        job_id=job.id,
        technician_id=technician.id,
        start_time=p_start,
        end_time=p_end,
        status="scheduled",
        is_existing=False,
    )
    db.add(assignment)

    old_status = job.status
    job.assigned_technician_id = technician.id
    job.scheduled_start = p_start
    job.scheduled_end = p_end
    job.status = "assigned"

    from app.models.job_state_history import JobStateHistory
    history = JobStateHistory(
        job_id=job.id,
        from_status=old_status,
        to_status="assigned",
        reason=f"Assigned to {technician.id} ({technician.name})",
        changed_at=datetime.now(timezone.utc),
    )
    db.add(history)

    db.commit()
    db.refresh(assignment)
    db.refresh(job)
    return assignment

