"""
Time-window and SLA constraint validation for field technician scheduling.

Enforces:
1. Hard Job Time Windows: [time_window_start, time_window_end]
   - Service start must be >= time_window_start.
   - Service completion (start + duration) must be <= time_window_end.
   - Exact boundary timestamps are fully supported and valid.
2. Complete Service Duration:
   - Validates that the service duration is accurately preserved and non-zero.
3. Required Travel Time Inclusion:
   - Verifies whether technician departing from previous origin can reach job site
     prior to proposed start time.
   - Rejects appointments where transit makes arrival impossible.
4. Expired Window Rejection:
   - Evaluates against the simulation reference clock (as_of).
   - Rejects retroactive appointments or jobs whose hard window has already passed.
5. Soft SLA Deadline Distinction:
   - Distinguishes soft SLA delays from hard time-window rejections.
   - If completion is within the hard time window but exceeds SLA deadline,
     is_eligible remains True while reporting SLA lateness metrics and penalty.
6. Timezone-Aware Arithmetic:
   - Normalizes all datetimes to consistent timezone-aware objects.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List, Tuple

from app.models.job import Job
from app.schemas.job import JobResponse
from app.scheduling.schemas import (
    TimeWindowValidationResult,
    FeasibleWindowResult,
)


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


def validate_job_time_window(
    time_window_start: Union[datetime, str],
    time_window_end: Union[datetime, str],
    duration_minutes: int,
    proposed_start: Union[datetime, str],
    proposed_end: Optional[Union[datetime, str]] = None,
    sla_deadline: Optional[Union[datetime, str]] = None,
    job_id: Optional[str] = None,
    origin_departure_time: Optional[Union[datetime, str]] = None,
    travel_minutes: float = 0.0,
    as_of: Optional[Union[datetime, str]] = None,
    enforce_simulation_clock: bool = True,
) -> TimeWindowValidationResult:
    """
    Validates hard job time-window boundaries, service duration, required transit time,
    and simulation clock bounds, while distinguishing soft SLA lateness.

    Args:
        time_window_start: Hard permitted window opening.
        time_window_end: Hard permitted window closing.
        duration_minutes: Mandatory job service duration in minutes.
        proposed_start: Proposed appointment start time.
        proposed_end: Proposed appointment end time (computed from duration if omitted).
        sla_deadline: Soft SLA target deadline (lateness penalized, but not hard rejected if <= window_end).
        job_id: Optional job identifier.
        origin_departure_time: Timestamp when technician departs prior stop / home.
        travel_minutes: Estimated transit minutes to reach job location.
        as_of: Current simulation reference clock.
        enforce_simulation_clock: Whether to reject expired or retroactive times against as_of.

    Returns:
        TimeWindowValidationResult with detailed hard/soft metrics and rejection reasons.
    """
    # 1. Parse all timestamps safely ensuring timezone-awareness
    w_start = parse_datetime_safe(time_window_start)
    w_end = parse_datetime_safe(time_window_end)
    p_start = parse_datetime_safe(proposed_start)
    p_end = parse_datetime_safe(proposed_end)
    sla = parse_datetime_safe(sla_deadline)
    dep_time = parse_datetime_safe(origin_departure_time)
    clock = parse_datetime_safe(as_of)

    rejection_reasons: List[str] = []
    rejection_codes: List[str] = []

    # Verify basic timestamp inputs
    if not w_start or not w_end or not p_start:
        return TimeWindowValidationResult(
            job_id=job_id,
            is_eligible=False,
            proposed_start=p_start or datetime.now(timezone.utc),
            proposed_end=p_end or datetime.now(timezone.utc),
            duration_minutes=duration_minutes or 0,
            time_window_start=w_start or datetime.now(timezone.utc),
            time_window_end=w_end or datetime.now(timezone.utc),
            sla_deadline=sla,
            rejection_reasons=["Invalid or unparseable time window timestamps provided."],
            rejection_codes=["INVALID_TIMESTAMPS"],
            summary="Invalid or unparseable timestamps provided.",
        )

    if duration_minutes <= 0:
        return TimeWindowValidationResult(
            job_id=job_id,
            is_eligible=False,
            proposed_start=p_start,
            proposed_end=p_end or p_start,
            duration_minutes=duration_minutes,
            time_window_start=w_start,
            time_window_end=w_end,
            sla_deadline=sla,
            duration_mismatch=True,
            rejection_reasons=["Job duration must be greater than zero minutes."],
            rejection_codes=["INVALID_DURATION"],
            summary="Job duration must be strictly positive.",
        )

    # If proposed_end was not provided, compute it directly from proposed_start and duration
    expected_duration_td = timedelta(minutes=duration_minutes)
    if p_end is None:
        p_end = p_start + expected_duration_td

    # 2. Check complete service duration match
    duration_mismatch = False
    actual_seconds = (p_end - p_start).total_seconds()
    actual_duration_minutes = int(round(actual_seconds / 60.0))
    if actual_duration_minutes != duration_minutes or actual_seconds <= 0:
        duration_mismatch = True
        rejection_reasons.append(
            f"Service interval duration ({actual_duration_minutes} mins) does not match required job duration ({duration_minutes} mins)."
        )
        rejection_codes.append("DURATION_MISMATCH")

    # 3. Check simulation reference clock bounds (as_of)
    is_window_expired = False
    starts_before_sim_clock = False

    if enforce_simulation_clock and clock:
        if clock > w_end:
            is_window_expired = True
            rejection_reasons.append(
                f"Job time window has already expired relative to simulation clock (as_of: {clock.isoformat()}, window end: {w_end.isoformat()})."
            )
            rejection_codes.append("WINDOW_EXPIRED")
        elif (w_end - expected_duration_td) < clock:
            is_window_expired = True
            rejection_reasons.append(
                f"Remaining window time as of simulation clock ({clock.isoformat()}) is insufficient for job duration ({duration_minutes} mins)."
            )
            rejection_codes.append("WINDOW_EXPIRED_FOR_DURATION")

        if p_start < clock:
            starts_before_sim_clock = True
            rejection_reasons.append(
                f"Proposed start time ({p_start.isoformat()}) is in the past relative to simulation clock ({clock.isoformat()})."
            )
            rejection_codes.append("START_BEFORE_SIMULATION_CLOCK")

    # 4. Check required travel transit time
    travel_infeasible = False
    earliest_arrival: Optional[datetime] = None

    if dep_time is not None and travel_minutes > 0.0:
        transit_td = timedelta(minutes=travel_minutes)
        earliest_arrival = dep_time + transit_td
        if p_start < earliest_arrival:
            travel_infeasible = True
            rejection_reasons.append(
                f"Technician cannot reach job location by proposed start time: transit from origin requires {travel_minutes:.1f} mins "
                f"(origin departure: {dep_time.isoformat()}, earliest arrival: {earliest_arrival.isoformat()}, proposed start: {p_start.isoformat()})."
            )
            rejection_codes.append("TRAVEL_TIME_INFEASIBLE")

    # 5. Check hard time window boundaries
    starts_too_early = False
    ends_too_late = False

    if p_start < w_start:
        starts_too_early = True
        rejection_reasons.append(
            f"Proposed start time ({p_start.isoformat()}) is earlier than permissible window start ({w_start.isoformat()})."
        )
        rejection_codes.append("START_BEFORE_WINDOW_START")

    if p_end > w_end:
        ends_too_late = True
        rejection_reasons.append(
            f"Proposed service completion ({p_end.isoformat()}) exceeds hard time window end ({w_end.isoformat()})."
        )
        rejection_codes.append("END_AFTER_WINDOW_END")

    # 6. Distinguish Soft SLA Lateness from Hard Rejection
    is_sla_violated = False
    sla_lateness_minutes = 0
    sla_status = "not_applicable"

    if sla:
        if p_end > sla:
            is_sla_violated = True
            sla_lateness_minutes = int(round((p_end - sla).total_seconds() / 60.0))
            sla_status = "late"
        else:
            is_sla_violated = False
            sla_lateness_minutes = 0
            sla_status = "on_time"

    # 7. Synthesize Hard Eligibility
    # CRITICAL: SLA lateness does NOT automatically cause a hard rejection!
    is_eligible = (
        not starts_too_early
        and not ends_too_late
        and not duration_mismatch
        and not is_window_expired
        and not starts_before_sim_clock
        and not travel_infeasible
    )

    # 8. Build human-readable summary
    job_label = f"Job {job_id}" if job_id else "Job"
    if is_eligible:
        if is_sla_violated:
            summary = f"{job_label} satisfies hard time window [{w_start.strftime('%H:%M')} - {w_end.strftime('%H:%M')}] but misses SLA deadline by {sla_lateness_minutes} mins (soft penalty)."
        else:
            summary = f"{job_label} satisfies hard time window [{w_start.strftime('%H:%M')} - {w_end.strftime('%H:%M')}] and meets SLA deadline on time."
    else:
        summary = f"{job_label} violates time-window constraints: {'; '.join(rejection_reasons)}"

    return TimeWindowValidationResult(
        job_id=job_id,
        is_eligible=is_eligible,
        proposed_start=p_start,
        proposed_end=p_end,
        duration_minutes=duration_minutes,
        time_window_start=w_start,
        time_window_end=w_end,
        sla_deadline=sla,
        is_window_expired=is_window_expired,
        starts_too_early=starts_too_early,
        ends_too_late=ends_too_late,
        duration_mismatch=duration_mismatch,
        travel_infeasible=travel_infeasible,
        starts_before_simulation_clock=starts_before_sim_clock,
        travel_minutes=travel_minutes,
        origin_departure_time=dep_time,
        earliest_arrival_time=earliest_arrival,
        is_sla_violated=is_sla_violated,
        sla_lateness_minutes=sla_lateness_minutes,
        sla_status=sla_status,
        rejection_reasons=rejection_reasons,
        rejection_codes=rejection_codes,
        summary=summary,
    )


def validate_job_instance_time_window(
    job: Union[Job, JobResponse],
    proposed_start: Union[datetime, str],
    proposed_end: Optional[Union[datetime, str]] = None,
    origin_departure_time: Optional[Union[datetime, str]] = None,
    travel_minutes: float = 0.0,
    as_of: Optional[Union[datetime, str]] = None,
    enforce_simulation_clock: bool = True,
) -> TimeWindowValidationResult:
    """
    Convenience helper extracting time-window parameters directly from a Job ORM or JobResponse object.
    """
    return validate_job_time_window(
        time_window_start=job.time_window_start,
        time_window_end=job.time_window_end,
        duration_minutes=job.duration_minutes,
        proposed_start=proposed_start,
        proposed_end=proposed_end,
        sla_deadline=getattr(job, "sla_deadline", None),
        job_id=job.id,
        origin_departure_time=origin_departure_time,
        travel_minutes=travel_minutes,
        as_of=as_of,
        enforce_simulation_clock=enforce_simulation_clock,
    )


def calculate_feasible_service_window(
    time_window_start: Union[datetime, str],
    time_window_end: Union[datetime, str],
    duration_minutes: int,
    sla_deadline: Optional[Union[datetime, str]] = None,
    origin_departure_time: Optional[Union[datetime, str]] = None,
    travel_minutes: float = 0.0,
    as_of: Optional[Union[datetime, str]] = None,
    enforce_simulation_clock: bool = True,
    job_id: Optional[str] = None,
) -> FeasibleWindowResult:
    """
    Calculates the exact permissible start and completion bounds for a job,
    taking into account the hard time window, transit time, simulation clock,
    and soft SLA deadline.
    """
    w_start = parse_datetime_safe(time_window_start)
    w_end = parse_datetime_safe(time_window_end)
    sla = parse_datetime_safe(sla_deadline)
    dep_time = parse_datetime_safe(origin_departure_time)
    clock = parse_datetime_safe(as_of)

    if not w_start or not w_end:
        raise ValueError("time_window_start and time_window_end are required.")

    duration_td = timedelta(minutes=duration_minutes)

    # 1. Earliest possible start is determined by the max of:
    # - hard window start
    # - simulation clock (if enforced)
    # - transit arrival from departure origin (if transit provided)
    earliest_start = w_start

    if enforce_simulation_clock and clock:
        if clock > earliest_start:
            earliest_start = clock

    if dep_time is not None and travel_minutes > 0.0:
        transit_arrival = dep_time + timedelta(minutes=travel_minutes)
        if transit_arrival > earliest_start:
            earliest_start = transit_arrival

    # 2. Latest permissible start without violating hard window end
    latest_start = w_end - duration_td

    # 3. Check feasibility
    is_feasible = earliest_start <= latest_start
    infeasibility_reason = None
    if not is_feasible:
        if enforce_simulation_clock and clock and clock > (w_end - duration_td):
            infeasibility_reason = f"Window closed relative to simulation clock ({clock.isoformat()})."
        elif dep_time and (dep_time + timedelta(minutes=travel_minutes)) > latest_start:
            infeasibility_reason = f"Transit arrival exceeds latest feasible start ({latest_start.isoformat()})."
        else:
            infeasibility_reason = f"Earliest feasible start ({earliest_start.isoformat()}) exceeds latest feasible start ({latest_start.isoformat()})."

    # 4. On-time SLA latest start
    on_time_sla_latest_start = None
    if sla:
        on_time_sla_latest_start = sla - duration_td

    earliest_completion = earliest_start + duration_td
    latest_completion = latest_start + duration_td

    return FeasibleWindowResult(
        job_id=job_id,
        earliest_feasible_start=earliest_start,
        latest_feasible_start=latest_start,
        earliest_feasible_completion=earliest_completion,
        latest_feasible_completion=latest_completion,
        duration_minutes=duration_minutes,
        is_feasible=is_feasible,
        travel_minutes=travel_minutes,
        time_window_start=w_start,
        time_window_end=w_end,
        sla_deadline=sla,
        on_time_sla_latest_start=on_time_sla_latest_start,
        infeasibility_reason=infeasibility_reason,
    )
