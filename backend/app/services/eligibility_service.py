from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Sequence, Union

from app.schemas.eligibility import (
    ValidationIssueSchema,
    EligibilityCheckResponse,
)


def parse_datetime_safe(val: Any) -> Optional[datetime]:
    """Parse string or datetime object ensuring timezone-aware consistency."""
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


def validate_skills(
    required_skills: Sequence[str],
    technician_skills: Sequence[str],
) -> Tuple[bool, List[str], Optional[ValidationIssueSchema]]:
    """
    Validates that technician possesses ALL certified skills required by the job.
    Supports single-skill and multi-skill jobs.
    """
    if not required_skills:
        return True, [], None

    tech_skills_norm = {s.strip().lower() for s in (technician_skills or []) if s and s.strip()}
    missing: List[str] = []

    for req in required_skills:
        if req and req.strip():
            norm_req = req.strip().lower()
            if norm_req not in tech_skills_norm:
                missing.append(req.strip())

    if missing:
        issue = ValidationIssueSchema(
            category="skills",
            code="MISSING_REQUIRED_SKILLS",
            message=f"Technician lacks required skill(s): {', '.join(missing)}",
            details={"missing_skills": missing, "technician_skills": list(technician_skills or [])},
        )
        return False, missing, issue

    return True, [], None


def validate_equipment(
    required_equipment: Sequence[str],
    technician_equipment: Sequence[str],
) -> Tuple[bool, List[str], Optional[ValidationIssueSchema]]:
    """
    Validates that technician possesses ALL required tools/equipment items in their onboard kit.
    """
    if not required_equipment:
        return True, [], None

    tech_equip_norm = {e.strip().lower() for e in (technician_equipment or []) if e and e.strip()}
    missing: List[str] = []

    for req in required_equipment:
        if req and req.strip():
            norm_req = req.strip().lower()
            if norm_req not in tech_equip_norm:
                missing.append(req.strip())

    if missing:
        issue = ValidationIssueSchema(
            category="equipment",
            code="MISSING_REQUIRED_EQUIPMENT",
            message=f"Technician lacks required equipment: {', '.join(missing)}",
            details={"missing_equipment": missing, "technician_equipment": list(technician_equipment or [])},
        )
        return False, missing, issue

    return True, [], None


def validate_zone_eligibility(
    job_zone_id: Optional[str],
    eligible_zones: Sequence[str],
    home_zone_id: Optional[str] = None,
    technician_home_zone_id: Optional[str] = None,
) -> Tuple[bool, Optional[ValidationIssueSchema]]:
    """
    Validates whether the job zone falls within technician's certified operational territory.
    """
    if not job_zone_id or not job_zone_id.strip():
        return True, None

    effective_home_zone = home_zone_id or technician_home_zone_id
    target_zone = job_zone_id.strip().upper()
    tech_zones_norm = {z.strip().upper() for z in (eligible_zones or []) if z and z.strip()}
    if effective_home_zone and effective_home_zone.strip():
        tech_zones_norm.add(effective_home_zone.strip().upper())

    if target_zone not in tech_zones_norm:
        issue = ValidationIssueSchema(
            category="zone",
            code="INELIGIBLE_ZONE",
            message=f"Job zone '{job_zone_id}' is not in technician eligible zones: {list(eligible_zones or [])}",
            details={
                "job_zone": job_zone_id,
                "eligible_zones": list(eligible_zones or []),
                "home_zone_id": home_zone_id,
            },
        )
        return False, issue

    return True, None


def validate_shift_availability(
    proposed_start: datetime,
    proposed_end: datetime,
    shifts: Sequence[Dict[str, Any]],
    overtime_config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, int, bool, Optional[ValidationIssueSchema]]:
    """
    Validates that proposed working interval fits inside a scheduled shift,
    evaluating overtime allowance if work exceeds standard shift end.
    Returns: (is_available, overtime_minutes, is_overtime_authorized, issue)
    """
    p_start = parse_datetime_safe(proposed_start)
    p_end = parse_datetime_safe(proposed_end)

    if not p_start or not p_end or p_end <= p_start:
        issue = ValidationIssueSchema(
            category="shift",
            code="INVALID_TIME_INTERVAL",
            message="Proposed execution start time must be strictly earlier than end time",
            details={},
        )
        return False, 0, False, issue

    if not shifts:
        issue = ValidationIssueSchema(
            category="shift",
            code="NO_SHIFTS_CONFIGURED",
            message="Technician has no scheduled working shifts",
            details={},
        )
        return False, 0, False, issue

    # Extract overtime policy
    ot_allowed = False
    ot_max_mins = 0
    if overtime_config:
        ot_allowed = bool(overtime_config.get("allowed", False))
        ot_max_mins = int(overtime_config.get("max_minutes_per_shift", 0) or 0)

    # Check against all shifts
    best_issue: Optional[ValidationIssueSchema] = None
    shift_matched = False

    for shift in shifts:
        s_start = parse_datetime_safe(shift.get("start"))
        s_end = parse_datetime_safe(shift.get("end"))

        if not s_start or not s_end:
            continue

        # Check if shift covers proposed start
        if s_start <= p_start:
            shift_matched = True
            # Case 1: Fully within standard shift
            if p_end <= s_end:
                return True, 0, False, None

            # Case 2: Exceeds shift end -> requires overtime
            overtime_needed = int(round((p_end - s_end).total_seconds() / 60.0))
            if ot_allowed and overtime_needed <= ot_max_mins:
                return True, overtime_needed, True, None
            elif not ot_allowed:
                best_issue = ValidationIssueSchema(
                    category="shift",
                    code="OVERTIME_PROHIBITED",
                    message=f"Job ends {overtime_needed} mins after shift end ({s_end.strftime('%H:%M')}) and overtime is not authorized",
                    details={
                        "shift_end": s_end.isoformat(),
                        "overtime_needed_minutes": overtime_needed,
                    },
                )
            else:
                best_issue = ValidationIssueSchema(
                    category="shift",
                    code="OVERTIME_LIMIT_EXCEEDED",
                    message=f"Required overtime of {overtime_needed} mins exceeds technician max cap of {ot_max_mins} mins",
                    details={
                        "shift_end": s_end.isoformat(),
                        "overtime_needed_minutes": overtime_needed,
                        "max_overtime_allowed_minutes": ot_max_mins,
                    },
                )

    if not shift_matched:
        return (
            False,
            0,
            False,
            ValidationIssueSchema(
                category="shift",
                code="OUTSIDE_SCHEDULED_SHIFT",
                message=f"Proposed start {p_start.strftime('%Y-%m-%d %H:%M')} does not fall within any scheduled shift",
                details={"proposed_start": p_start.isoformat(), "proposed_end": p_end.isoformat()},
            ),
        )

    return False, 0, False, best_issue


def validate_unavailable_periods(
    proposed_start: datetime,
    proposed_end: datetime,
    unavailable_periods: Sequence[Dict[str, Any]],
) -> Tuple[bool, List[Dict[str, Any]], Optional[ValidationIssueSchema]]:
    """
    Validates that proposed job interval does not collide with any pre-scheduled
    technician leaves, breaks, or maintenance windows.
    """
    p_start = parse_datetime_safe(proposed_start)
    p_end = parse_datetime_safe(proposed_end)

    if not p_start or not p_end or not unavailable_periods:
        return True, [], None

    conflicts: List[Dict[str, Any]] = []

    for period in unavailable_periods:
        u_start = parse_datetime_safe(period.get("start"))
        u_end = parse_datetime_safe(period.get("end"))
        reason = period.get("reason", "unavailable")

        if not u_start or not u_end:
            continue

        # Overlap condition: start < u_end and end > u_start
        if p_start < u_end and p_end > u_start:
            conflicts.append({
                "start": u_start.isoformat(),
                "end": u_end.isoformat(),
                "reason": reason,
            })

    if conflicts:
        reasons_list = [f"{c['reason']} ({c['start']} to {c['end']})" for c in conflicts]
        issue = ValidationIssueSchema(
            category="unavailable",
            code="UNAVAILABLE_PERIOD_CONFLICT",
            message=f"Proposed job interval conflicts with technician unavailable period(s): {'; '.join(reasons_list)}",
            details={"conflicts": conflicts},
        )
        return False, conflicts, issue

    return True, [], None


def validate_time_window(
    proposed_start: datetime,
    proposed_end: datetime,
    window_start: datetime,
    window_end: datetime,
    duration_minutes: Optional[int] = None,
) -> Tuple[bool, Optional[ValidationIssueSchema]]:
    """
    Validates hard operational time window constraints:
    service must start >= window_start and end <= window_end.
    """
    p_start = parse_datetime_safe(proposed_start)
    p_end = parse_datetime_safe(proposed_end)
    w_start = parse_datetime_safe(window_start)
    w_end = parse_datetime_safe(window_end)

    if not p_start or not p_end or not w_start or not w_end:
        return True, None

    if p_start < w_start:
        return False, ValidationIssueSchema(
            category="time_window",
            code="START_BEFORE_WINDOW_START",
            message=f"Proposed start ({p_start.strftime('%H:%M')}) is earlier than permissible window start ({w_start.strftime('%H:%M')})",
            details={"proposed_start": p_start.isoformat(), "window_start": w_start.isoformat()},
        )

    if p_end > w_end:
        return False, ValidationIssueSchema(
            category="time_window",
            code="END_AFTER_WINDOW_END",
            message=f"Proposed end ({p_end.strftime('%H:%M')}) exceeds permissible window end ({w_end.strftime('%H:%M')})",
            details={"proposed_end": p_end.isoformat(), "window_end": w_end.isoformat()},
        )

    if duration_minutes is not None and duration_minutes > 0:
        actual_minutes = int(round((p_end - p_start).total_seconds() / 60.0))
        if actual_minutes != duration_minutes:
            return False, ValidationIssueSchema(
                category="time_window",
                code="DURATION_MISMATCH",
                message=f"Proposed time interval duration ({actual_minutes} mins) does not match required job duration ({duration_minutes} mins)",
                details={"actual_minutes": actual_minutes, "required_duration": duration_minutes},
            )

    return True, None


def validate_job_technician_eligibility(
    job_skills: Sequence[str],
    job_equipment: Sequence[str],
    job_zone_id: Optional[str],
    technician_skills: Sequence[str],
    technician_equipment: Sequence[str],
    technician_eligible_zones: Sequence[str],
    technician_home_zone_id: Optional[str] = None,
    proposed_start: Optional[datetime] = None,
    proposed_end: Optional[datetime] = None,
    technician_shifts: Optional[Sequence[Dict[str, Any]]] = None,
    technician_unavailable_periods: Optional[Sequence[Dict[str, Any]]] = None,
    technician_overtime: Optional[Dict[str, Any]] = None,
    job_time_window_start: Optional[datetime] = None,
    job_time_window_end: Optional[datetime] = None,
    job_duration_minutes: Optional[int] = None,
) -> EligibilityCheckResponse:
    """
    Master composite validator evaluating all hard and soft constraints
    between a customer service job and a field technician resource.
    Aggregates all failures simultaneously into a unified result object.
    """
    reasons: List[str] = []
    issues: List[ValidationIssueSchema] = []

    # 1. Skills Validation
    skills_ok, missing_skills, skill_issue = validate_skills(
        required_skills=job_skills,
        technician_skills=technician_skills,
    )
    if not skills_ok and skill_issue:
        reasons.append(skill_issue.message)
        issues.append(skill_issue)

    # 2. Equipment Validation
    equip_ok, missing_equip, equip_issue = validate_equipment(
        required_equipment=job_equipment,
        technician_equipment=technician_equipment,
    )
    if not equip_ok and equip_issue:
        reasons.append(equip_issue.message)
        issues.append(equip_issue)

    # 3. Zone Eligibility Validation
    zone_ok, zone_issue = validate_zone_eligibility(
        job_zone_id=job_zone_id,
        eligible_zones=technician_eligible_zones,
        home_zone_id=technician_home_zone_id,
    )
    if not zone_ok and zone_issue:
        reasons.append(zone_issue.message)
        issues.append(zone_issue)

    # 4. Shift Availability & Overtime (if proposed execution times provided)
    shift_ok = True
    ot_needed = 0
    ot_allowed = False
    if proposed_start and proposed_end and technician_shifts:
        shift_ok, ot_needed, ot_allowed, shift_issue = validate_shift_availability(
            proposed_start=proposed_start,
            proposed_end=proposed_end,
            shifts=technician_shifts,
            overtime_config=technician_overtime,
        )
        if not shift_ok and shift_issue:
            reasons.append(shift_issue.message)
            issues.append(shift_issue)

    # 5. Unavailable Periods Conflict Check
    unavail_conflict = False
    if proposed_start and proposed_end and technician_unavailable_periods:
        unavail_ok, _, unavail_issue = validate_unavailable_periods(
            proposed_start=proposed_start,
            proposed_end=proposed_end,
            unavailable_periods=technician_unavailable_periods,
        )
        if not unavail_ok and unavail_issue:
            unavail_conflict = True
            reasons.append(unavail_issue.message)
            issues.append(unavail_issue)

    # 6. Time Window Compliance Check
    window_ok = True
    if proposed_start and proposed_end and job_time_window_start and job_time_window_end:
        window_ok, window_issue = validate_time_window(
            proposed_start=proposed_start,
            proposed_end=proposed_end,
            window_start=job_time_window_start,
            window_end=job_time_window_end,
            duration_minutes=job_duration_minutes,
        )
        if not window_ok and window_issue:
            reasons.append(window_issue.message)
            issues.append(window_issue)

    is_eligible = len(issues) == 0

    return EligibilityCheckResponse(
        is_eligible=is_eligible,
        reasons=reasons,
        missing_skills=missing_skills,
        missing_equipment=missing_equip,
        zone_eligible=zone_ok,
        shift_available=shift_ok,
        unavailable_conflict=unavail_conflict,
        time_window_valid=window_ok,
        overtime_required_minutes=ot_needed,
        overtime_allowed=ot_allowed,
        issues=issues,
    )
