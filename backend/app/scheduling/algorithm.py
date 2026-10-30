"""
Initial deterministic workforce scheduling and assignment algorithm.

Implements the first working automatic scheduling algorithm for DispatchGrid:
1. Multi-Criteria Job Prioritization:
   - Priority 1 (Urgent) > 2 (High) > 3 (Medium) > 4 (Low).
   - Constrained-first ordering: jobs requiring rare skills/equipment are scheduled first.
   - Tight time windows and SLA deadlines scheduled earlier.
   - Deterministic tie-breaking on job ID ascending.
2. Candidate Qualification Filtering:
   - Certified multi-skills matching (no unqualified dispatches; unsupported skills flagged).
   - Mandatory equipment tooling verification.
   - Geographic operational zone certification.
3. Candidate Feasible Slot Search:
   - Evaluates technician working shifts across multiple dates in the planning horizon.
   - Considers technician home departure for the first job and inter-job travel between consecutive jobs.
   - Enforces hard time windows [time_window_start, time_window_end].
   - Enforces simulation reference clock (as_of), rejecting retroactive dispatches.
   - Strictly protects pre-existing active in-progress and completed assignments.
   - Detects and prevents travel buffer deficits and double bookings.
4. Deterministic Multi-Factor Ranking:
   - Optimizes a multi-objective cost function balancing travel efficiency, wait time,
     authorized overtime, SLA punctuality, and fleet workload distribution.
   - Does NOT simply dump all work onto the first available technician.
5. In-Memory Dynamic Schedule Tracking:
   - Newly assigned jobs immediately update the technician's itinerary, preventing subsequent
     jobs from colliding with newly planned dispatches.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List, Tuple

from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.schemas.assignment import AssignmentSummary
from app.scheduling.schemas import (
    SchedulingInput,
    SchedulingResult,
    AssignedJobPlan,
    UnassignedJobReport,
)
from app.scheduling.skills import check_technician_skills, DEFAULT_UNSUPPORTED_SKILLS
from app.scheduling.equipment import check_technician_equipment
from app.scheduling.geo import (
    check_zone_eligibility,
    haversine_distance,
    calculate_travel_minutes,
)
from app.scheduling.availability import parse_datetime_safe
from app.scheduling.time_windows import validate_job_time_window
from app.scheduling.conflicts import detect_scheduling_conflicts, extract_assignment_info


def calculate_job_scheduling_difficulty(
    job: JobResponse,
    technicians: Sequence[TechnicianResponse],
    unsupported_skills: Sequence[str] = DEFAULT_UNSUPPORTED_SKILLS,
) -> int:
    """
    Computes a deterministic scheduling difficulty metric: the count of qualified technicians.
    Jobs with fewer eligible technicians are more constrained and should be prioritized earlier.
    """
    # If job has unsupported skill, count is 0
    job_skills = [s.strip().lower() for s in (job.required_skills or []) if s.strip()]
    norm_unsupported = {u.strip().lower() for u in unsupported_skills}
    if any(s in norm_unsupported for s in job_skills):
        return 0

    count = 0
    job_equip = [e.strip().lower() for e in (job.required_equipment or []) if e.strip()]

    for tech in technicians:
        # Check skill
        s_res = check_technician_skills(
            required_skills=job_skills,
            technician_skills=tech.skills or [],
            technician_id=tech.id,
            unsupported_skills=unsupported_skills,
        )
        if not s_res.is_eligible:
            continue
        # Check equip
        e_res = check_technician_equipment(
            required_equipment=job_equip,
            technician_equipment=tech.equipment or [],
            technician_id=tech.id,
        )
        if not e_res.is_eligible:
            continue
        # Check zone
        z_res = check_zone_eligibility(
            job_zone_id=job.zone_id,
            eligible_zones=tech.eligible_zones or [],
            home_zone_id=tech.home_zone_id,
            technician_id=tech.id,
        )
        if not z_res.is_eligible:
            continue
        count += 1

    return count


def prioritize_pending_jobs(
    jobs: Sequence[JobResponse],
    technicians: Sequence[TechnicianResponse],
    unsupported_skills: Sequence[str] = DEFAULT_UNSUPPORTED_SKILLS,
) -> List[JobResponse]:
    """
    Sorts pending jobs deterministically by:
    1. Priority level (1=Urgent, 2=High, 3=Medium, 4=Low) ascending.
    2. Candidate qualification difficulty (fewer qualified technicians first).
    3. Hard time window end (earliest hard deadline first).
    4. Soft SLA deadline (earliest SLA first).
    5. Hard time window start (earliest start first).
    6. Job ID ascending (strict tie-breaker).
    """
    difficulties = {
        j.id: calculate_job_scheduling_difficulty(j, technicians, unsupported_skills)
        for j in jobs
    }

    def sort_key(job: JobResponse):
        sla = job.sla_deadline or job.time_window_end
        return (
            job.priority,  # 1 is highest priority
            difficulties.get(job.id, 999),  # Most constrained (fewer technicians) first
            job.time_window_end,  # Earliest hard deadline first
            sla,  # Earliest SLA deadline first
            job.time_window_start,  # Earliest start first
            job.id,  # Deterministic tie-breaker
        )

    return sorted(jobs, key=sort_key)


def find_feasible_slots_for_technician(
    job: JobResponse,
    technician: TechnicianResponse,
    itinerary: List[Dict[str, Any]],
    as_of: datetime,
) -> List[Dict[str, Any]]:
    """
    Finds all valid, conflict-free scheduling slots for a specific job and technician
    across all scheduled shifts in the planning horizon.
    """
    feasible_slots: List[Dict[str, Any]] = []
    shifts = technician.shifts or []
    if not shifts:
        return feasible_slots

    duration_td = timedelta(minutes=job.duration_minutes)

    for shift in shifts:
        s_start = parse_datetime_safe(shift.get("start") if isinstance(shift, dict) else getattr(shift, "start", None))
        s_end = parse_datetime_safe(shift.get("end") if isinstance(shift, dict) else getattr(shift, "end", None))

        if not s_start or not s_end:
            continue

        # Skip shifts that already ended in the past relative to simulation clock
        if s_end <= as_of:
            continue

        # Extract shift's date string
        shift_date_str = str(shift.get("date", "")) if isinstance(shift, dict) else str(getattr(shift, "date", ""))

        # Filter itinerary assignments falling on this shift/date
        shift_assignments = [
            a for a in itinerary
            if a["start_time"].date() == s_start.date()
        ]
        shift_assignments.sort(key=lambda x: x["start_time"])

        # Candidate insertion positions:
        # Position 0: Before first assignment (or sole job if no assignments on this shift)
        # Position i: Between assignment i and i+1
        # Position k: After last assignment on this shift

        candidate_departure_points: List[Tuple[Optional[Dict[str, Any]], datetime, float, float, str]] = []

        if not shift_assignments:
            # Departure from technician home
            dep_time = max(s_start, as_of)
            candidate_departure_points.append(
                (None, dep_time, technician.home_lat, technician.home_lng, "home")
            )
        else:
            # 1. Before first assignment on shift
            first_assign = shift_assignments[0]
            dep_time = max(s_start, as_of)
            candidate_departure_points.append(
                (None, dep_time, technician.home_lat, technician.home_lng, "home_before_first")
            )

            # 2. After each existing assignment on shift
            for idx, a in enumerate(shift_assignments):
                candidate_departure_points.append(
                    (a, a["end_time"], a["lat"], a["lng"], f"after_{a['job_id']}")
                )

        # Evaluate each departure point
        for prec_assign, dep_time, origin_lat, origin_lng, pos_tag in candidate_departure_points:
            # Transit time from origin to job
            if origin_lat is not None and origin_lng is not None and job.lat is not None and job.lng is not None:
                dist_km = haversine_distance(origin_lat, origin_lng, job.lat, job.lng)
                transit_mins = calculate_travel_minutes(dist_km)
            else:
                dist_km = 0.0
                transit_mins = 0.0

            arrival_time = dep_time + timedelta(minutes=transit_mins)

            # Proposed start cannot be earlier than:
            # 1. Hard job window start
            # 2. Earliest arrival from origin
            # 3. Simulation reference clock (as_of)
            proposed_start = max(job.time_window_start, arrival_time, as_of)
            proposed_end = proposed_start + duration_td

            # Check 1: Time Window Validation (Hard window start/end + duration)
            tw_res = validate_job_time_window(
                time_window_start=job.time_window_start,
                time_window_end=job.time_window_end,
                duration_minutes=job.duration_minutes,
                proposed_start=proposed_start,
                proposed_end=proposed_end,
                sla_deadline=job.sla_deadline,
                job_id=job.id,
                origin_departure_time=dep_time,
                travel_minutes=transit_mins,
                as_of=as_of,
                enforce_simulation_clock=True,
            )
            if not tw_res.is_eligible:
                continue

            # Check 2: Conflict Detection against all existing/new assignments
            conflict_res = detect_scheduling_conflicts(
                technician_id=technician.id,
                proposed_start=proposed_start,
                proposed_end=proposed_end,
                job_id=job.id,
                job_lat=job.lat,
                job_lng=job.lng,
                existing_assignments=itinerary,
                technician=technician,
                as_of=as_of,
                include_travel=True,
                enforce_simulation_clock=True,
            )
            if conflict_res.has_conflict:
                continue

            # Compute idle wait minutes (arrived early before window start)
            wait_minutes = max(0.0, (proposed_start - arrival_time).total_seconds() / 60.0)

            feasible_slots.append({
                "technician": technician,
                "proposed_start": proposed_start,
                "proposed_end": proposed_end,
                "travel_minutes": transit_mins,
                "distance_km": dist_km,
                "wait_minutes": wait_minutes,
                "requires_overtime": conflict_res.requires_overtime,
                "overtime_minutes": conflict_res.overtime_minutes,
                "overtime_penalty": conflict_res.overtime_penalty,
                "is_sla_violated": tw_res.is_sla_violated,
                "sla_lateness_minutes": tw_res.sla_lateness_minutes,
                "shift_date": shift_date_str,
            })

    return feasible_slots


def compute_slot_ranking_score(
    slot: Dict[str, Any],
    technician_workload_minutes: float,
) -> float:
    """
    Multi-objective deterministic ranking score:
    Lower score = better match.
    Considers:
    - Travel duration (efficiency)
    - Idle wait time (packing density)
    - Overtime penalty (prefers standard hours)
    - SLA lateness (punctuality)
    - Workload balance across fleet (prevents assigning all work to T01)
    """
    travel_weight = 1.0
    wait_weight = 0.5
    overtime_weight = 2.0
    sla_lateness_weight = 3.0
    workload_balance_weight = 0.05

    score = (
        travel_weight * slot["travel_minutes"]
        + wait_weight * slot["wait_minutes"]
        + overtime_weight * slot["overtime_penalty"]
        + sla_lateness_weight * slot["sla_lateness_minutes"]
        + workload_balance_weight * technician_workload_minutes
    )
    return score


def run_deterministic_initial_scheduler(
    inputs: SchedulingInput,
    unsupported_skills: Sequence[str] = DEFAULT_UNSUPPORTED_SKILLS,
) -> SchedulingResult:
    """
    Executes the initial automatic deterministic scheduling algorithm.

    Guarantees:
    - 100% reproducible results given identical inputs.
    - Zero hard constraint violations.
    - Strict preservation of all pre-existing assignments.
    - Balanced workload distribution across the active fleet.
    """
    run_id = inputs.run_id
    as_of = inputs.as_of
    norm_unsupported = {s.strip().lower() for s in unsupported_skills}

    # 1. Initialize In-Memory Itineraries with Protected Existing Assignments
    technician_itineraries: Dict[str, List[Dict[str, Any]]] = {
        t.id: [] for t in inputs.technicians
    }
    technician_workloads: Dict[str, float] = {
        t.id: 0.0 for t in inputs.technicians
    }

    assigned_plans: List[AssignedJobPlan] = []
    unassigned_job_reports: List[UnassignedJobReport] = []

    # Map jobs and technicians for fast lookup
    tech_map: Dict[str, TechnicianResponse] = {t.id: t for t in inputs.technicians}

    # Seed existing assignments
    for existing in inputs.existing_assignments:
        plan = AssignedJobPlan(
            job_id=existing.job_id,
            technician_id=existing.technician_id,
            scheduled_start=existing.start_time,
            scheduled_end=existing.end_time,
            travel_time_minutes=0.0,
            is_existing=True,
            status=existing.status,
            details={
                "assignment_id": existing.id,
                "actual_start": existing.actual_start.isoformat() if existing.actual_start else None,
                "job_title": existing.job_title,
                "technician_name": existing.technician_name,
            },
        )
        assigned_plans.append(plan)

        # Find job coordinates if available
        # Pre-existing jobs might be in inputs or looked up
        existing_info = extract_assignment_info(existing)
        t_id = existing.technician_id
        if t_id in technician_itineraries:
            technician_itineraries[t_id].append(existing_info)
            duration_mins = (existing.end_time - existing.start_time).total_seconds() / 60.0
            technician_workloads[t_id] += duration_mins

    # 2. Prioritize Pending Jobs
    sorted_jobs = prioritize_pending_jobs(
        jobs=inputs.pending_jobs,
        technicians=inputs.technicians,
        unsupported_skills=unsupported_skills,
    )

    # 3. Schedule Each Job Deterministically
    for job in sorted_jobs:
        job_skills = [s.strip().lower() for s in (job.required_skills or []) if s.strip()]
        job_equip = [e.strip().lower() for e in (job.required_equipment or []) if e.strip()]

        # Filter out jobs with unsupported requirements
        has_unsupported = any(s in norm_unsupported for s in job_skills)
        if has_unsupported:
            unassigned_job_reports.append(
                UnassignedJobReport(
                    job_id=job.id,
                    reason=f"Job requires unsupported skill(s): {', '.join(s for s in job_skills if s in norm_unsupported)}",
                    violated_constraints=["UNSUPPORTED_SKILLS"],
                )
            )
            continue

        # Find qualified candidates by skills, equipment, and zone
        candidate_options: List[Dict[str, Any]] = []

        for tech in inputs.technicians:
            # 1. Skill check
            s_res = check_technician_skills(
                required_skills=job_skills,
                technician_skills=tech.skills or [],
                technician_id=tech.id,
                unsupported_skills=unsupported_skills,
            )
            if not s_res.is_eligible:
                continue

            # 2. Equipment check
            e_res = check_technician_equipment(
                required_equipment=job_equip,
                technician_equipment=tech.equipment or [],
                technician_id=tech.id,
            )
            if not e_res.is_eligible:
                continue

            # 3. Zone check
            z_res = check_zone_eligibility(
                job_zone_id=job.zone_id,
                eligible_zones=tech.eligible_zones or [],
                home_zone_id=tech.home_zone_id,
                technician_id=tech.id,
            )
            if not z_res.is_eligible:
                continue

            # 4. Find feasible slots for this technician
            itinerary = technician_itineraries.get(tech.id, [])
            slots = find_feasible_slots_for_technician(
                job=job,
                technician=tech,
                itinerary=itinerary,
                as_of=as_of,
            )

            # Score each slot
            for slot in slots:
                w_mins = technician_workloads.get(tech.id, 0.0)
                rank_score = compute_slot_ranking_score(slot, w_mins)
                slot["ranking_score"] = rank_score
                candidate_options.append(slot)

        # 4. Select Best Candidate Option
        if not candidate_options:
            unassigned_job_reports.append(
                UnassignedJobReport(
                    job_id=job.id,
                    reason="No feasible technician candidate satisfies all skill, equipment, shift, and time-window constraints.",
                    violated_constraints=["NO_FEASIBLE_CANDIDATE"],
                )
            )
            continue

        # Sort candidate options deterministically:
        # 1. Lowest ranking score
        # 2. Earliest proposed start
        # 3. Technician ID ascending
        candidate_options.sort(
            key=lambda x: (
                x["ranking_score"],
                x["proposed_start"],
                x["technician"].id,
            )
        )

        best_choice = candidate_options[0]
        chosen_tech = best_choice["technician"]
        chosen_start = best_choice["proposed_start"]
        chosen_end = best_choice["proposed_end"]
        chosen_travel = best_choice["travel_minutes"]

        # Create AssignedJobPlan
        new_plan = AssignedJobPlan(
            job_id=job.id,
            technician_id=chosen_tech.id,
            scheduled_start=chosen_start,
            scheduled_end=chosen_end,
            travel_time_minutes=round(chosen_travel, 2),
            is_existing=False,
            status="scheduled",
            details={
                "job_title": job.title,
                "technician_name": chosen_tech.name,
                "zone_id": job.zone_id,
                "lat": job.lat,
                "lng": job.lng,
                "requires_overtime": best_choice["requires_overtime"],
                "overtime_minutes": best_choice["overtime_minutes"],
                "is_sla_violated": best_choice["is_sla_violated"],
                "sla_lateness_minutes": best_choice["sla_lateness_minutes"],
                "ranking_score": round(best_choice["ranking_score"], 2),
            },
        )
        assigned_plans.append(new_plan)

        # Immediately update the technician's in-memory itinerary & workload
        new_assign_dict = {
            "assignment_id": None,
            "job_id": job.id,
            "technician_id": chosen_tech.id,
            "start_time": chosen_start,
            "end_time": chosen_end,
            "status": "scheduled",
            "lat": job.lat,
            "lng": job.lng,
            "job_title": job.title,
        }
        technician_itineraries[chosen_tech.id].append(new_assign_dict)
        technician_workloads[chosen_tech.id] += job.duration_minutes + chosen_travel

    # 5. Compile Summary Metrics and Results
    newly_scheduled_count = len([p for p in assigned_plans if not p.is_existing])
    unassigned_job_ids = [r.job_id for r in unassigned_job_reports]
    total_evaluated = len(assigned_plans) + len(unassigned_job_ids)

    # Technician job count distribution
    tech_distribution: Dict[str, int] = {t.id: 0 for t in inputs.technicians}
    for p in assigned_plans:
        if p.technician_id in tech_distribution:
            tech_distribution[p.technician_id] += 1

    travel_times = [p.travel_time_minutes for p in assigned_plans if not p.is_existing]
    avg_travel = round(sum(travel_times) / len(travel_times), 2) if travel_times else 0.0

    unassigned_due_to_skills = [
        r.job_id for r in unassigned_job_reports if "UNSUPPORTED_SKILLS" in r.violated_constraints
    ]

    result = SchedulingResult(
        run_id=run_id,
        status="scheduled",
        as_of=as_of,
        horizon_start=inputs.horizon_start,
        horizon_end=inputs.horizon_end,
        total_jobs=total_evaluated,
        pending_jobs_count=inputs.pending_jobs_count,
        assigned_jobs_count=len(assigned_plans),
        unassigned_jobs_count=len(unassigned_job_ids),
        existing_assignments_preserved=True,
        assignments=assigned_plans,
        unassigned_jobs=unassigned_job_ids,
        metrics={
            "algorithm": "deterministic_constrained_greedy_v1",
            "existing_assignments_count": len(inputs.existing_assignments),
            "newly_scheduled_count": newly_scheduled_count,
            "unassigned_count": len(unassigned_job_ids),
            "unassigned_reports": [r.model_dump() for r in unassigned_job_reports],
            "unassigned_due_to_unsupported_skills": unassigned_due_to_skills,
            "technician_distribution": tech_distribution,
            "active_technicians_utilized": sum(1 for c in tech_distribution.values() if c > 0),
            "average_new_travel_minutes": avg_travel,
            "total_new_travel_minutes": round(sum(travel_times), 2),
            "reproducible": True,
        },
        created_at=datetime.now(timezone.utc),
    )

    return result
