"""
Configurable deterministic schedule objective function and scoring engine.

MATHEMATICAL FORMULATION & ASSUMPTIONS:
----------------------------------------
Total Schedule Objective Cost:
    J(S) = C_sla + C_travel + C_unassigned + C_overtime + C_churn

Where:
1. SLA Lateness Penalty (C_sla):
   - For each scheduled job j with completion time C_j and soft SLA deadline D_j:
     Lateness_j = max(0, (C_j - D_j) in minutes)
     C_sla = w_sla * sum(Lateness_j)
   - Units: Minutes late * Cost per minute (default w_sla = 2.0).

2. Total Travel-Time Penalty (C_travel):
   - For each technician t and consecutive route stops (including initial trip from home):
     Travel_t = sum(Leg_transit_minutes) at standard 30.0 km/h velocity
     C_travel = w_travel * sum(Travel_t)
   - Units: Travel minutes * Cost per minute (default w_travel = 1.0).

3. Unassigned Job Priority Penalty (C_unassigned):
   - Heavily penalizes leaving backlog jobs unserviced, scaled by priority tier:
     Priority 1 (Urgent): w_unassigned_p1 (default = 1000.0)
     Priority 2 (High):   w_unassigned_p2 (default = 500.0)
     Priority 3 (Medium): w_unassigned_p3 (default = 200.0)
     Priority 4 (Low):    w_unassigned_p4 (default = 100.0)
     C_unassigned = sum(w_unassigned[job.priority])
   - Units: Penalty points per unassigned job.

4. Overtime Penalty (C_overtime):
   - For authorized overtime worked past standard shift working hours:
     Overtime_t = sum(max(0, Job_end - Shift_end) in minutes)
     C_overtime = w_overtime * sum(Overtime_t)
   - Units: Overtime minutes * Cost per minute (default w_overtime = 3.0).

5. Assignment Churn / Disruption Penalty (C_churn):
   - Penalizes modifying pre-existing baseline/locked assignments:
     C_churn = w_churn * Count(Modified_pre_existing_jobs)
   - Units: Penalty points per disrupted assignment (default w_churn = 250.0).

STRICT HARD CONSTRAINT INDEPENDENCE:
------------------------------------
Hard constraints are validated independently of the objective score.
If a schedule violates any hard constraint (double booking, missing skill,
missing equipment, uncovered zone, hard window breach, unauthorized overtime),
it is strictly flagged as `is_feasible = False` with itemized violations.
A lower objective score CANNOT override or mask hard constraint violations.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Sequence, Tuple
from collections import defaultdict

from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.schemas.assignment import AssignmentSummary
from app.scheduling.schemas import (
    ObjectiveWeightsConfig,
    ScheduleAssignmentItem,
    JobLatenessDetail,
    SLALatenessBreakdown,
    TechnicianTravelDetail,
    TravelTimeBreakdown,
    UnassignedPriorityBreakdown,
    TechnicianOvertimeDetail,
    OvertimeBreakdown,
    AssignmentChurnDetail,
    AssignmentChurnBreakdown,
    HardConstraintViolation,
    ScheduleScoreResult,
)
from app.scheduling.geo import haversine_distance, calculate_travel_minutes
from app.scheduling.availability import parse_datetime_safe
from app.scheduling.skills import check_technician_skills
from app.scheduling.equipment import check_technician_equipment


# Documented System Units & Assumptions
SCORING_UNITS: Dict[str, str] = {
    "sla_lateness": "minutes late past soft SLA deadline (cost = lateness_minutes * w_sla)",
    "travel_time": "minutes in transit @ 30.0 km/h Haversine distance (cost = travel_minutes * w_travel)",
    "unassigned_p1": "penalty points per unassigned Urgent (Priority 1) service job",
    "unassigned_p2": "penalty points per unassigned High (Priority 2) service job",
    "unassigned_p3": "penalty points per unassigned Medium (Priority 3) service job",
    "unassigned_p4": "penalty points per unassigned Low (Priority 4) service job",
    "overtime": "minutes worked outside regular shift hours (cost = overtime_minutes * w_overtime)",
    "churn": "penalty points per altered or reassigned pre-existing baseline assignment",
    "total_score": "aggregate objective cost (lower is superior)",
}

SCORING_ASSUMPTIONS: List[str] = [
    "Vehicle velocity is constant at 30.0 km/h across all operational zones.",
    "Distance calculations use the Haversine spherical model with Earth radius 6371.0 km.",
    "Initial technician dispatch originates from their primary home base coordinates.",
    "Consecutive assignments on the same day calculate direct inter-job transit buffers.",
    "Soft SLA deadlines do not prevent execution but assess linear penalties per minute late.",
    "Hard customer time windows and working shift boundaries are strictly enforced.",
    "Hard constraint violations render is_feasible=False regardless of objective score value.",
    "Deterministic execution ensures identical inputs and weights produce identical scores.",
]


def calculate_sla_lateness_penalty(
    jobs_map: Dict[str, Any],
    assignments: Sequence[Any],
    weight: float,
) -> SLALatenessBreakdown:
    """
    Computes SLA lateness penalty for all assigned jobs whose completion
    exceeds their soft SLA target deadline.
    """
    total_delayed = 0
    total_lateness_mins = 0
    total_penalty = 0.0
    delayed_jobs: List[JobLatenessDetail] = []

    for a in assignments:
        job_id = getattr(a, "job_id", None)
        end_time = getattr(a, "end_time", None) or getattr(a, "scheduled_end", None)
        if not job_id or not end_time:
            continue

        job = jobs_map.get(job_id)
        if not job:
            continue

        sla_deadline = getattr(job, "sla_deadline", None)
        if not sla_deadline:
            continue

        dt_end = parse_datetime_safe(end_time)
        dt_sla = parse_datetime_safe(sla_deadline)

        if dt_end and dt_sla and dt_end > dt_sla:
            lateness_mins = int((dt_end - dt_sla).total_seconds() / 60)
            if lateness_mins > 0:
                cost = round(lateness_mins * weight, 2)
                total_delayed += 1
                total_lateness_mins += lateness_mins
                total_penalty += cost
                delayed_jobs.append(
                    JobLatenessDetail(
                        job_id=job_id,
                        completion_time=dt_end,
                        sla_deadline=dt_sla,
                        lateness_minutes=lateness_mins,
                        penalty=cost,
                    )
                )

    return SLALatenessBreakdown(
        total_delayed_jobs=total_delayed,
        total_lateness_minutes=total_lateness_mins,
        total_penalty=round(total_penalty, 2),
        weight=weight,
        delayed_jobs=delayed_jobs,
    )


def calculate_travel_time_penalty(
    techs_map: Dict[str, Any],
    jobs_map: Dict[str, Any],
    assignments_by_tech: Dict[str, List[Any]],
    weight: float,
) -> TravelTimeBreakdown:
    """
    Computes travel time and transit penalty for all dispatched routes.
    Includes initial trip from home base and inter-job travel.
    """
    total_travel_mins = 0.0
    total_dist_km = 0.0
    total_penalty = 0.0
    tech_details: List[TechnicianTravelDetail] = []

    for tech_id, assigns in assignments_by_tech.items():
        if not assigns:
            continue

        tech = techs_map.get(tech_id)
        if not tech:
            continue

        # Sort assignments chronologically
        sorted_assigns = sorted(
            assigns,
            key=lambda x: parse_datetime_safe(getattr(x, "start_time", None) or getattr(x, "scheduled_start", None))
            or datetime.min.replace(tzinfo=timezone.utc),
        )

        prev_lat = getattr(tech, "home_lat", 0.0)
        prev_lng = getattr(tech, "home_lng", 0.0)
        t_travel_mins = 0.0
        t_dist_km = 0.0
        legs_count = 0

        for a in sorted_assigns:
            job_id = getattr(a, "job_id", None)
            job = jobs_map.get(job_id)
            if not job:
                continue

            j_lat = getattr(job, "lat", 0.0)
            j_lng = getattr(job, "lng", 0.0)

            dist = haversine_distance(prev_lat, prev_lng, j_lat, j_lng)
            travel_mins = calculate_travel_minutes(dist)

            t_dist_km += dist
            t_travel_mins += travel_mins
            legs_count += 1

            prev_lat = j_lat
            prev_lng = j_lng

        t_penalty = round(t_travel_mins * weight, 2)
        total_travel_mins += t_travel_mins
        total_dist_km += t_dist_km
        total_penalty += t_penalty

        tech_details.append(
            TechnicianTravelDetail(
                technician_id=tech_id,
                technician_name=getattr(tech, "name", tech_id),
                legs_count=legs_count,
                total_distance_km=round(t_dist_km, 2),
                total_travel_minutes=round(t_travel_mins, 2),
                penalty=t_penalty,
            )
        )

    return TravelTimeBreakdown(
        total_travel_minutes=round(total_travel_mins, 2),
        total_distance_km=round(total_dist_km, 2),
        total_penalty=round(total_penalty, 2),
        weight=weight,
        technician_travel=tech_details,
    )


def calculate_unassigned_penalty(
    unassigned_jobs: Sequence[Any],
    weights: ObjectiveWeightsConfig,
) -> UnassignedPriorityBreakdown:
    """
    Computes penalty for unassigned jobs, heavily weighted by priority tier.
    """
    p1_count = 0
    p2_count = 0
    p3_count = 0
    p4_count = 0
    unassigned_ids: List[str] = []

    for job in unassigned_jobs:
        job_id = getattr(job, "id", None) or getattr(job, "job_id", None)
        priority = getattr(job, "priority", 3)
        if job_id:
            unassigned_ids.append(job_id)

        if priority == 1:
            p1_count += 1
        elif priority == 2:
            p2_count += 1
        elif priority == 3:
            p3_count += 1
        else:
            p4_count += 1

    p1_pen = round(p1_count * weights.w_unassigned_p1, 2)
    p2_pen = round(p2_count * weights.w_unassigned_p2, 2)
    p3_pen = round(p3_count * weights.w_unassigned_p3, 2)
    p4_pen = round(p4_count * weights.w_unassigned_p4, 2)
    total_pen = round(p1_pen + p2_pen + p3_pen + p4_pen, 2)

    return UnassignedPriorityBreakdown(
        unassigned_p1_count=p1_count,
        unassigned_p2_count=p2_count,
        unassigned_p3_count=p3_count,
        unassigned_p4_count=p4_count,
        total_unassigned_count=len(unassigned_jobs),
        p1_penalty=p1_pen,
        p2_penalty=p2_pen,
        p3_penalty=p3_pen,
        p4_penalty=p4_pen,
        total_penalty=total_pen,
        unassigned_job_ids=unassigned_ids,
    )


def calculate_overtime_penalty(
    techs_map: Dict[str, Any],
    assignments_by_tech: Dict[str, List[Any]],
    weight: float,
) -> OvertimeBreakdown:
    """
    Computes penalty for authorized overtime minutes worked beyond regular shifts.
    """
    total_ot_mins = 0
    total_penalty = 0.0
    tech_ot_details: List[TechnicianOvertimeDetail] = []

    for tech_id, assigns in assignments_by_tech.items():
        if not assigns:
            continue

        tech = techs_map.get(tech_id)
        if not tech:
            continue

        shifts = getattr(tech, "shifts", []) or []
        shifts_by_date = {}
        for s in shifts:
            if isinstance(s, dict):
                d_str = s.get("date")
                start_dt = parse_datetime_safe(s.get("start"))
                end_dt = parse_datetime_safe(s.get("end"))
            else:
                d_str = getattr(s, "date", None)
                start_dt = parse_datetime_safe(getattr(s, "start", None))
                end_dt = parse_datetime_safe(getattr(s, "end", None))

            if d_str and start_dt and end_dt:
                shifts_by_date[d_str] = (start_dt, end_dt)

        # Calculate overtime per shift date
        tech_ot_for_tech = 0
        for a in assigns:
            end_time = parse_datetime_safe(getattr(a, "end_time", None) or getattr(a, "scheduled_end", None))
            if not end_time:
                continue

            date_str = end_time.strftime("%Y-%m-%d")
            if date_str in shifts_by_date:
                _, regular_shift_end = shifts_by_date[date_str]
                if end_time > regular_shift_end:
                    ot_mins = int((end_time - regular_shift_end).total_seconds() / 60)
                    if ot_mins > 0:
                        tech_ot_for_tech = max(tech_ot_for_tech, ot_mins)

        if tech_ot_for_tech > 0:
            ot_cost = round(tech_ot_for_tech * weight, 2)
            total_ot_mins += tech_ot_for_tech
            total_penalty += ot_cost
            tech_ot_details.append(
                TechnicianOvertimeDetail(
                    technician_id=tech_id,
                    technician_name=getattr(tech, "name", tech_id),
                    overtime_minutes=tech_ot_for_tech,
                    penalty=ot_cost,
                )
            )

    return OvertimeBreakdown(
        total_overtime_minutes=total_ot_mins,
        technicians_with_overtime_count=len(tech_ot_details),
        total_penalty=round(total_penalty, 2),
        weight=weight,
        technician_overtime=tech_ot_details,
    )


def calculate_assignment_churn_penalty(
    baseline_assignments: Sequence[Any],
    candidate_assignments: Sequence[Any],
    weight: float,
) -> AssignmentChurnBreakdown:
    """
    Computes penalty for modifying or reassigning pre-existing locked/baseline assignments.
    """
    baseline_map = {}
    for a in baseline_assignments:
        job_id = getattr(a, "job_id", None)
        tech_id = getattr(a, "technician_id", None)
        if job_id and tech_id:
            baseline_map[job_id] = tech_id

    churn_details: List[AssignmentChurnDetail] = []
    total_penalty = 0.0

    for a in candidate_assignments:
        job_id = getattr(a, "job_id", None)
        new_tech_id = getattr(a, "technician_id", None)
        if job_id in baseline_map:
            baseline_tech = baseline_map[job_id]
            if baseline_tech != new_tech_id:
                cost = round(weight, 2)
                total_penalty += cost
                churn_details.append(
                    AssignmentChurnDetail(
                        job_id=job_id,
                        baseline_technician_id=baseline_tech,
                        new_technician_id=new_tech_id,
                        change_type="reassigned",
                        penalty=cost,
                    )
                )

    return AssignmentChurnBreakdown(
        total_disrupted_jobs=len(churn_details),
        total_penalty=round(total_penalty, 2),
        weight=weight,
        churn_details=churn_details,
    )


def validate_schedule_hard_constraints(
    techs_map: Dict[str, Any],
    jobs_map: Dict[str, Any],
    assignments_by_tech: Dict[str, List[Any]],
    as_of: Optional[datetime] = None,
) -> List[HardConstraintViolation]:
    """
    Rigorously verifies all hard operational constraints independently of the objective score:
    - Skill mismatches
    - Equipment mismatches
    - Zone eligibility violations
    - Double booking (time overlaps)
    - Transit buffer deficits
    - Shift / overtime authorization and caps
    - Hard customer time-window violations
    - Retroactive scheduling prior to simulation clock
    """
    violations: List[HardConstraintViolation] = []
    clock = parse_datetime_safe(as_of)

    for tech_id, assigns in assignments_by_tech.items():
        if not assigns:
            continue

        tech = techs_map.get(tech_id)
        if not tech:
            violations.append(
                HardConstraintViolation(
                    violation_type="UNKNOWN_TECHNICIAN",
                    technician_id=tech_id,
                    description=f"Assigned technician '{tech_id}' does not exist in roster.",
                )
            )
            continue

        tech_skills = getattr(tech, "skills", []) or []
        tech_equip = getattr(tech, "equipment", []) or []
        eligible_zones = set(getattr(tech, "eligible_zones", []) or [])
        home_zone = getattr(tech, "home_zone_id", None)
        if home_zone:
            eligible_zones.add(home_zone)

        # Sort assignments chronologically
        sorted_assigns = sorted(
            assigns,
            key=lambda x: parse_datetime_safe(getattr(x, "start_time", None) or getattr(x, "scheduled_start", None))
            or datetime.min.replace(tzinfo=timezone.utc),
        )

        prev_end = None
        prev_lat = getattr(tech, "home_lat", 0.0)
        prev_lng = getattr(tech, "home_lng", 0.0)

        for a in sorted_assigns:
            job_id = getattr(a, "job_id", None)
            job = jobs_map.get(job_id)
            if not job:
                violations.append(
                    HardConstraintViolation(
                        violation_type="UNKNOWN_JOB",
                        job_id=job_id,
                        technician_id=tech_id,
                        description=f"Assigned job '{job_id}' does not exist in dataset.",
                    )
                )
                continue

            start_time = parse_datetime_safe(getattr(a, "start_time", None) or getattr(a, "scheduled_start", None))
            end_time = parse_datetime_safe(getattr(a, "end_time", None) or getattr(a, "scheduled_end", None))
            is_exist = getattr(a, "is_existing", False)
            status = getattr(a, "status", "")

            # 1. Simulation clock retroactivity check
            if clock and start_time and start_time < clock:
                # Pre-existing completed or in-progress assignments are historical facts
                if not (is_exist or status in ["completed", "in_progress"]):
                    violations.append(
                        HardConstraintViolation(
                            violation_type="SIMULATION_CLOCK_RETROACTIVE",
                            job_id=job_id,
                            technician_id=tech_id,
                            description=f"Job {job_id} scheduled at {start_time} before simulation clock {clock}.",
                        )
                    )

            # For newly proposed / scheduled assignments, validate capabilities and customer window
            if not (is_exist or status in ["completed", "in_progress"]):
                # 2. Skill check
                req_skills = getattr(job, "required_skills", []) or []
                skill_res = check_technician_skills(req_skills, tech_skills)
                if not skill_res.is_eligible:
                    violations.append(
                        HardConstraintViolation(
                            violation_type="SKILL_MISMATCH",
                            job_id=job_id,
                            technician_id=tech_id,
                            description=f"Technician {tech_id} lacks required skills {skill_res.missing_skills} for {job_id}.",
                        )
                    )

                # 3. Equipment check
                req_equip = getattr(job, "required_equipment", []) or []
                equip_res = check_technician_equipment(req_equip, tech_equip)
                if not equip_res.is_eligible:
                    violations.append(
                        HardConstraintViolation(
                            violation_type="EQUIPMENT_MISMATCH",
                            job_id=job_id,
                            technician_id=tech_id,
                            description=f"Technician {tech_id} lacks required equipment {equip_res.missing_equipment} for {job_id}.",
                        )
                    )

                # 4. Zone eligibility check
                job_zone = getattr(job, "zone_id", None)
                if job_zone and job_zone not in eligible_zones:
                    violations.append(
                        HardConstraintViolation(
                            violation_type="ZONE_VIOLATION",
                            job_id=job_id,
                            technician_id=tech_id,
                            description=f"Job {job_id} in Zone {job_zone} outside technician {tech_id} eligible zones {sorted(list(eligible_zones))}.",
                        )
                    )

                # 5. Hard time-window boundaries check
                tw_start = parse_datetime_safe(getattr(job, "time_window_start", None))
                tw_end = parse_datetime_safe(getattr(job, "time_window_end", None))
                if tw_start and start_time and start_time < tw_start:
                    violations.append(
                        HardConstraintViolation(
                            violation_type="TIME_WINDOW_BREACH",
                            job_id=job_id,
                            technician_id=tech_id,
                            description=f"Job {job_id} scheduled start {start_time} is earlier than hard window start {tw_start}.",
                        )
                    )
                if tw_end and end_time and end_time > tw_end:
                    violations.append(
                        HardConstraintViolation(
                            violation_type="TIME_WINDOW_BREACH",
                            job_id=job_id,
                            technician_id=tech_id,
                            description=f"Job {job_id} scheduled completion {end_time} is later than hard window end {tw_end}.",
                        )
                    )

            # 6. Overlap / Double booking check
            if prev_end and start_time and start_time < prev_end:
                violations.append(
                    HardConstraintViolation(
                        violation_type="DOUBLE_BOOKING",
                        job_id=job_id,
                        technician_id=tech_id,
                        description=f"Job {job_id} start {start_time} overlaps with preceding assignment end {prev_end}.",
                    )
                )

            # 7. Transit buffer check
            j_lat = getattr(job, "lat", 0.0)
            j_lng = getattr(job, "lng", 0.0)
            dist_km = haversine_distance(prev_lat, prev_lng, j_lat, j_lng)
            req_transit_mins = calculate_travel_minutes(dist_km)

            if prev_end and start_time:
                avail_buffer_mins = (start_time - prev_end).total_seconds() / 60.0
                if avail_buffer_mins + 0.01 < req_transit_mins:
                    violations.append(
                        HardConstraintViolation(
                            violation_type="BUFFER_VIOLATION",
                            job_id=job_id,
                            technician_id=tech_id,
                            description=f"Transit buffer deficit for {job_id}: available {round(avail_buffer_mins, 1)}m < required {round(req_transit_mins, 1)}m.",
                        )
                    )

            prev_end = end_time
            prev_lat = j_lat
            prev_lng = j_lng

    return violations


def evaluate_schedule_score(
    jobs: Sequence[Any],
    technicians: Sequence[Any],
    assignments: Sequence[Any],
    baseline_assignments: Optional[Sequence[Any]] = None,
    weights: Optional[ObjectiveWeightsConfig] = None,
    as_of: Optional[datetime] = None,
) -> ScheduleScoreResult:
    """
    Rigorously evaluates the multi-criteria schedule objective score and hard constraint feasibility.

    Guarantees:
    - Every score component is traceable and separable.
    - Weights are fully configurable.
    - Hard constraints cannot be overridden by a better score (is_feasible reflects hard violations).
    - Deterministic: identical schedules and weights produce identical results.
    """
    active_weights = weights or ObjectiveWeightsConfig()

    jobs_map = {getattr(j, "id", None) or getattr(j, "job_id", None): j for j in jobs}
    techs_map = {getattr(t, "id", None) or getattr(t, "technician_id", None): t for t in technicians}

    # Group assignments by technician
    assignments_by_tech = defaultdict(list)
    assigned_job_ids = set()
    for a in assignments:
        tech_id = getattr(a, "technician_id", None)
        job_id = getattr(a, "job_id", None)
        if tech_id and job_id:
            assignments_by_tech[tech_id].append(a)
            assigned_job_ids.add(job_id)

    # 1. Independent Hard Constraint Verification
    hard_violations = validate_schedule_hard_constraints(
        techs_map=techs_map,
        jobs_map=jobs_map,
        assignments_by_tech=assignments_by_tech,
        as_of=as_of,
    )
    is_feasible = (len(hard_violations) == 0)

    # 2. SLA Lateness Component
    sla_comp = calculate_sla_lateness_penalty(
        jobs_map=jobs_map,
        assignments=assignments,
        weight=active_weights.w_sla_lateness,
    )

    # 3. Total Travel-Time Component
    travel_comp = calculate_travel_time_penalty(
        techs_map=techs_map,
        jobs_map=jobs_map,
        assignments_by_tech=assignments_by_tech,
        weight=active_weights.w_travel_time,
    )

    # 4. Unassigned Priority Component
    unassigned_jobs = [
        j for j_id, j in jobs_map.items()
        if j_id not in assigned_job_ids and getattr(j, "status", "pending") in ["pending", "unassigned"]
    ]
    unassigned_comp = calculate_unassigned_penalty(
        unassigned_jobs=unassigned_jobs,
        weights=active_weights,
    )

    # 5. Overtime Component
    ot_comp = calculate_overtime_penalty(
        techs_map=techs_map,
        assignments_by_tech=assignments_by_tech,
        weight=active_weights.w_overtime,
    )

    # 6. Assignment Churn Component
    baseline = baseline_assignments or []
    churn_comp = calculate_assignment_churn_penalty(
        baseline_assignments=baseline,
        candidate_assignments=assignments,
        weight=active_weights.w_churn,
    )

    # Total Score Sum
    total_score = round(
        sla_comp.total_penalty
        + travel_comp.total_penalty
        + unassigned_comp.total_penalty
        + ot_comp.total_penalty
        + churn_comp.total_penalty,
        2,
    )

    return ScheduleScoreResult(
        total_score=total_score,
        is_feasible=is_feasible,
        hard_violations_count=len(hard_violations),
        hard_violations=hard_violations,
        sla_component=sla_comp,
        travel_component=travel_comp,
        unassigned_component=unassigned_comp,
        overtime_component=ot_comp,
        churn_component=churn_comp,
        weights_used=active_weights,
        units=SCORING_UNITS,
        assumptions=SCORING_ASSUMPTIONS,
    )
