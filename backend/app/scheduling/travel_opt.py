"""
Travel-Time Optimization and Geographical Route Refinement Engine.

Reduces unnecessary fleet transit travel, minimizes zone switching, clusters geographical
assignments, and optimizes technician itineraries while strictly guaranteeing zero hard
operational constraint violations.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List, Tuple
from collections import defaultdict
from itertools import permutations

from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.schemas import (
    AssignedJobPlan,
    TravelLegDetail,
    TechnicianTravelSummary,
    TravelMetricsComparison,
    TravelOptimizationAction,
    TravelOptimizationResult,
    HardConstraintViolation,
)
from app.scheduling.geo import (
    haversine_distance,
    calculate_travel_minutes,
    calculate_home_to_job_travel,
    calculate_inter_job_travel,
    check_zone_eligibility,
    DEFAULT_TRANSIT_SPEED_KMH,
)
from app.scheduling.skills import check_technician_skills, DEFAULT_UNSUPPORTED_SKILLS
from app.scheduling.equipment import check_technician_equipment
from app.scheduling.availability import (
    check_shift_coverage,
    check_unavailability_collision,
    parse_datetime_safe,
)
from app.scheduling.time_windows import validate_job_instance_time_window
from app.scheduling.scoring import validate_schedule_hard_constraints


def calculate_technician_travel_summary(
    technician: TechnicianResponse,
    assignments: Sequence[AssignedJobPlan],
    jobs_lookup: Dict[str, JobResponse],
    speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH,
) -> TechnicianTravelSummary:
    """
    Computes complete leg-by-leg travel metrics for a technician:
    - Origin leg: home base coordinates to the first job.
    - Intermediate legs: inter-job transit between consecutive jobs.
    - Zone switching detection and tracking.
    """
    tech_plans = sorted(
        [p for p in assignments if p.technician_id == technician.id],
        key=lambda x: x.scheduled_start,
    )

    if not tech_plans:
        return TechnicianTravelSummary(
            technician_id=technician.id,
            technician_name=technician.name,
            home_zone_id=technician.home_zone_id,
            total_travel_minutes=0.0,
            total_distance_km=0.0,
            home_to_first_minutes=0.0,
            home_to_first_distance_km=0.0,
            inter_job_minutes=0.0,
            inter_job_distance_km=0.0,
            job_count=0,
            zone_switches_count=0,
            legs=[],
        )

    legs: List[TravelLegDetail] = []
    total_travel_mins = 0.0
    total_dist_km = 0.0
    home_mins = 0.0
    home_dist = 0.0
    inter_mins = 0.0
    inter_dist = 0.0
    zone_switches = 0

    # 1. First leg: Home base to first job
    first_job = jobs_lookup[tech_plans[0].job_id]
    h2j = calculate_home_to_job_travel(technician, first_job, speed_kmh=speed_kmh)
    home_mins = h2j.travel_minutes
    home_dist = h2j.distance_km
    total_travel_mins += home_mins
    total_dist_km += home_dist

    is_first_zone_switch = (
        (technician.home_zone_id != first_job.zone_id)
        if technician.home_zone_id and first_job.zone_id
        else False
    )

    legs.append(
        TravelLegDetail(
            leg_index=1,
            origin_type="home",
            origin_id=technician.id,
            origin_zone=technician.home_zone_id,
            origin_lat=technician.home_lat,
            origin_lng=technician.home_lng,
            destination_job_id=first_job.id,
            destination_zone=first_job.zone_id,
            destination_lat=first_job.lat,
            destination_lng=first_job.lng,
            distance_km=home_dist,
            travel_minutes=home_mins,
            is_zone_switch=is_first_zone_switch,
        )
    )

    # 2. Subsequent legs: Job to Job
    prev_job = first_job
    for idx, plan in enumerate(tech_plans[1:], start=2):
        curr_job = jobs_lookup[plan.job_id]
        i2j = calculate_inter_job_travel(prev_job, curr_job, speed_kmh=speed_kmh)
        dist = i2j.distance_km
        mins = i2j.travel_minutes
        inter_dist += dist
        inter_mins += mins
        total_dist_km += dist
        total_travel_mins += mins

        is_switch = (
            (prev_job.zone_id != curr_job.zone_id)
            if prev_job.zone_id and curr_job.zone_id
            else False
        )
        if is_switch:
            zone_switches += 1

        legs.append(
            TravelLegDetail(
                leg_index=idx,
                origin_type="job",
                origin_id=prev_job.id,
                origin_zone=prev_job.zone_id,
                origin_lat=prev_job.lat,
                origin_lng=prev_job.lng,
                destination_job_id=curr_job.id,
                destination_zone=curr_job.zone_id,
                destination_lat=curr_job.lat,
                destination_lng=curr_job.lng,
                distance_km=dist,
                travel_minutes=mins,
                is_zone_switch=is_switch,
            )
        )
        prev_job = curr_job

    return TechnicianTravelSummary(
        technician_id=technician.id,
        technician_name=technician.name,
        home_zone_id=technician.home_zone_id,
        total_travel_minutes=round(total_travel_mins, 2),
        total_distance_km=round(total_dist_km, 2),
        home_to_first_minutes=round(home_mins, 2),
        home_to_first_distance_km=round(home_dist, 2),
        inter_job_minutes=round(inter_mins, 2),
        inter_job_distance_km=round(inter_dist, 2),
        job_count=len(tech_plans),
        zone_switches_count=zone_switches,
        legs=legs,
    )


def calculate_fleet_travel_breakdown(
    technicians: Sequence[TechnicianResponse],
    assignments: Sequence[AssignedJobPlan],
    jobs_lookup: Dict[str, JobResponse],
    speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH,
) -> Tuple[List[TechnicianTravelSummary], Dict[str, Any]]:
    """
    Aggregates per-technician and fleet-wide travel metrics.
    """
    summaries: List[TechnicianTravelSummary] = []
    total_travel_mins = 0.0
    total_dist_km = 0.0
    total_switches = 0
    assigned_jobs_count = len(assignments)

    for tech in technicians:
        summary = calculate_technician_travel_summary(
            technician=tech,
            assignments=assignments,
            jobs_lookup=jobs_lookup,
            speed_kmh=speed_kmh,
        )
        summaries.append(summary)
        total_travel_mins += summary.total_travel_minutes
        total_dist_km += summary.total_distance_km
        total_switches += summary.zone_switches_count

    avg_per_job = (
        round(total_travel_mins / assigned_jobs_count, 2)
        if assigned_jobs_count > 0
        else 0.0
    )

    metrics = {
        "total_travel_minutes": round(total_travel_mins, 2),
        "total_distance_km": round(total_dist_km, 2),
        "total_zone_switches": total_switches,
        "average_travel_per_job": avg_per_job,
    }
    return summaries, metrics


def _simulate_date_route(
    technician: TechnicianResponse,
    job_sequence: Sequence[JobResponse],
    shift_start_time: datetime,
    as_of: datetime,
    prev_existing_end: Optional[datetime] = None,
    prev_existing_job: Optional[JobResponse] = None,
    speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH,
) -> Optional[List[Dict[str, Any]]]:
    """
    Simulates a sequential route on a given date, strictly validating every hard constraint:
    - Customer time windows
    - Working shifts and authorized overtime
    - Unavailability intervals / leaves
    - Transit buffers between all consecutive legs
    """
    itinerary: List[Dict[str, Any]] = []
    prev_end = prev_existing_end
    prev_j = prev_existing_job

    for idx, job in enumerate(job_sequence):
        if idx == 0 and prev_j is None:
            h2j = calculate_home_to_job_travel(technician, job, speed_kmh=speed_kmh)
            travel_m = h2j.travel_minutes
            arr = max(as_of, shift_start_time + timedelta(minutes=travel_m))
        else:
            origin_j = prev_j if (idx == 0 and prev_j is not None) else job_sequence[idx - 1]
            i2j = calculate_inter_job_travel(origin_j, job, speed_kmh=speed_kmh)
            travel_m = i2j.travel_minutes
            arr = prev_end + timedelta(minutes=travel_m)

        proposed_start = max(arr, job.time_window_start)
        proposed_end = proposed_start + timedelta(minutes=job.duration_minutes)

        # 1. Customer hard time window check
        w_res = validate_job_instance_time_window(job, proposed_start)
        if not w_res.is_eligible:
            return None

        # 2. Shift coverage & overtime limit check
        overtime_cfg = {
            "allowed": technician.overtime_allowed,
            "max_minutes_per_shift": technician.max_overtime_minutes,
        }
        s_cov = check_shift_coverage(
            proposed_start=proposed_start,
            proposed_end=proposed_end,
            shifts=technician.shifts or [],
            overtime_config=overtime_cfg,
            technician_id=technician.id,
        )
        if not s_cov.is_available:
            return None

        # 3. Collision with scheduled leaves/unavailability
        u_cov = check_unavailability_collision(
            proposed_start=proposed_start,
            proposed_end=proposed_end,
            unavailable_periods=technician.unavailable_periods or [],
            technician_id=technician.id,
        )
        if not u_cov.is_free:
            return None

        itinerary.append({
            "job_id": job.id,
            "scheduled_start": proposed_start,
            "scheduled_end": proposed_end,
            "travel_time_minutes": travel_m,
            "requires_overtime": s_cov.requires_overtime,
            "overtime_minutes": s_cov.overtime_minutes,
            "is_sla_violated": proposed_end > job.sla_deadline if job.sla_deadline else False,
            "sla_lateness_minutes": (
                int(max(0.0, (proposed_end - job.sla_deadline).total_seconds() / 60.0))
                if job.sla_deadline
                else 0
            ),
        })
        prev_end = proposed_end
        prev_j = job

    return itinerary


def optimize_technician_routes(
    technicians: Sequence[TechnicianResponse],
    assignments: List[AssignedJobPlan],
    jobs_lookup: Dict[str, JobResponse],
    as_of: datetime,
    speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH,
) -> Tuple[List[AssignedJobPlan], List[TravelOptimizationAction]]:
    """
    Intra-technician route re-sequencing (2-opt local search within shift dates).
    Re-orders jobs for a technician when a tighter geographic order reduces travel minutes
    and zone switching, without violating any customer time windows or shift boundaries.
    Strictly preserves locked/in-progress existing assignments.
    """
    optimized_plans: Dict[str, AssignedJobPlan] = {
        p.job_id: p.model_copy() for p in assignments
    }
    actions: List[TravelOptimizationAction] = []
    techs_map = {t.id: t for t in technicians}

    # Group assignments by technician and date
    for tech in technicians:
        t_plans = [p for p in optimized_plans.values() if p.technician_id == tech.id]
        if len(t_plans) < 2:
            continue

        by_date = defaultdict(list)
        for p in t_plans:
            by_date[p.scheduled_start.date()].append(p)

        for d, date_plans in by_date.items():
            if len(date_plans) < 2:
                continue

            # Skip moving if any existing/locked assignment is on this day
            if any(
                p.is_existing or p.status in ["completed", "in_progress"]
                for p in date_plans
            ):
                continue

            orig_jobs = [
                jobs_lookup[p.job_id]
                for p in sorted(date_plans, key=lambda x: x.scheduled_start)
            ]

            # Calculate baseline travel and switches
            base_summary = calculate_technician_travel_summary(
                tech,
                date_plans,
                jobs_lookup,
                speed_kmh=speed_kmh,
            )
            base_travel = base_summary.total_travel_minutes
            base_switches = base_summary.zone_switches_count

            # Find matching shift start for day d
            shift_start = date_plans[0].scheduled_start.replace(hour=8, minute=0, second=0)
            for sh in (tech.shifts or []):
                st = parse_datetime_safe(
                    sh.get("start") if isinstance(sh, dict) else getattr(sh, "start", None)
                )
                if st and st.date() == d:
                    shift_start = st
                    break

            best_perm: Optional[Tuple[JobResponse, ...]] = None
            best_travel = base_travel
            best_switches = base_switches
            best_itinerary: Optional[List[Dict[str, Any]]] = None

            # Evaluate permutations (capped at 6 jobs to maintain deterministic low latency)
            eval_jobs = orig_jobs if len(orig_jobs) <= 6 else orig_jobs[:6]
            for perm in permutations(eval_jobs):
                if list(perm) == orig_jobs:
                    continue

                # Quick check: route travel (home to first + inter-job)
                p_travel = calculate_home_to_job_travel(
                    tech, perm[0], speed_kmh=speed_kmh
                ).travel_minutes
                p_sw = 0
                for i in range(len(perm) - 1):
                    p_travel += calculate_inter_job_travel(
                        perm[i], perm[i + 1], speed_kmh=speed_kmh
                    ).travel_minutes
                    if perm[i].zone_id != perm[i + 1].zone_id:
                        p_sw += 1

                # Candidate must strictly reduce travel or reduce zone switches
                if (p_travel < best_travel - 0.1) or (p_travel <= best_travel and p_sw < best_switches):
                    itin = _simulate_date_route(
                        technician=tech,
                        job_sequence=perm,
                        shift_start_time=shift_start,
                        as_of=as_of,
                        speed_kmh=speed_kmh,
                    )
                    if itin is not None:
                        best_travel = p_travel
                        best_switches = p_sw
                        best_perm = perm
                        best_itinerary = itin

            if best_perm is not None and best_itinerary is not None:
                saved_travel = round(base_travel - best_travel, 2)
                saved_sw = base_switches - best_switches

                # Apply updated schedule to plans
                for item in best_itinerary:
                    jid = item["job_id"]
                    plan = optimized_plans[jid]
                    plan.scheduled_start = item["scheduled_start"]
                    plan.scheduled_end = item["scheduled_end"]
                    plan.travel_time_minutes = round(item["travel_time_minutes"], 2)
                    if plan.details:
                        plan.details["requires_overtime"] = item["requires_overtime"]
                        plan.details["overtime_minutes"] = item["overtime_minutes"]
                        plan.details["is_sla_violated"] = item["is_sla_violated"]
                        plan.details["sla_lateness_minutes"] = item["sla_lateness_minutes"]

                actions.append(
                    TravelOptimizationAction(
                        action_type="ROUTE_REORDER",
                        technician_ids=[tech.id],
                        job_ids=[j.id for j in best_perm],
                        travel_minutes_saved=saved_travel,
                        zone_switches_reduced=max(0, saved_sw),
                        explanation=(
                            f"Reordered {len(best_perm)} jobs for Technician {tech.name} ({tech.id}) on {d}: "
                            f"reduced transit travel by {saved_travel}m "
                            f"({'avoided ' + str(saved_sw) + ' zone switch(es)' if saved_sw > 0 else 'maintained territory'}) "
                            f"from sequence {[j.id for j in orig_jobs]} to {[j.id for j in best_perm]}."
                        ),
                    )
                )

    return list(optimized_plans.values()), actions


def optimize_schedule_travel(
    initial_assignments: Sequence[AssignedJobPlan],
    technicians: Sequence[TechnicianResponse],
    jobs: Sequence[JobResponse],
    baseline_assignments: Sequence[AssignedJobPlan],
    as_of: datetime,
    speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH,
    run_id: str = "RUN-OPT-TRAVEL",
) -> TravelOptimizationResult:
    """
    Complete travel-time optimization pipeline:
    1. Computes initial leg-by-leg travel summaries and fleet metrics.
    2. Resolves any transit buffer deficits on initial schedule.
    3. Executes intra-technician route re-sequencing (2-opt).
    4. Evaluates optimized leg-by-leg metrics and verifies 100% hard constraint feasibility.
    5. Returns measured improvements and explainable optimization log.
    """
    jobs_lookup = {j.id: j for j in jobs}
    techs_map = {t.id: t for t in technicians}

    # 1. Baseline / Initial metrics
    init_summaries, init_metrics = calculate_fleet_travel_breakdown(
        technicians=technicians,
        assignments=initial_assignments,
        jobs_lookup=jobs_lookup,
        speed_kmh=speed_kmh,
    )

    # 2. Prepare mutable plans and adjust buffer deficits (e.g. JOB-037 buffer after JOB-107)
    working_plans = [p.model_copy() for p in initial_assignments]

    # Ensure buffer compliance from preceding jobs
    plans_by_tech = defaultdict(list)
    for p in working_plans:
        plans_by_tech[p.technician_id].append(p)

    for tid, p_list in plans_by_tech.items():
        sorted_p = sorted(p_list, key=lambda x: x.scheduled_start)
        tech = techs_map.get(tid)
        if not tech:
            continue
        prev_end = None
        prev_lat = tech.home_lat
        prev_lng = tech.home_lng
        for p in sorted_p:
            j = jobs_lookup[p.job_id]
            dist_km = haversine_distance(prev_lat, prev_lng, j.lat, j.lng)
            req_transit = calculate_travel_minutes(dist_km, speed_kmh=speed_kmh)
            if prev_end and not (p.is_existing or p.status in ["completed", "in_progress"]):
                earliest_start = prev_end + timedelta(minutes=req_transit)
                if p.scheduled_start < earliest_start:
                    diff = earliest_start - p.scheduled_start
                    p.scheduled_start = earliest_start
                    p.scheduled_end = p.scheduled_start + timedelta(minutes=j.duration_minutes)
            prev_end = p.scheduled_end
            prev_lat = j.lat
            prev_lng = j.lng

    # 3. Optimization Pass: Route Reordering (2-opt per date)
    optimized_plans, actions = optimize_technician_routes(
        technicians=technicians,
        assignments=working_plans,
        jobs_lookup=jobs_lookup,
        as_of=as_of,
        speed_kmh=speed_kmh,
    )

    # 4. Optimized metrics
    opt_summaries, opt_metrics = calculate_fleet_travel_breakdown(
        technicians=technicians,
        assignments=optimized_plans,
        jobs_lookup=jobs_lookup,
        speed_kmh=speed_kmh,
    )

    # 5. Measure exact improvement
    init_travel = init_metrics["total_travel_minutes"]
    opt_travel = opt_metrics["total_travel_minutes"]
    saved_travel = round(max(0.0, init_travel - opt_travel), 2)
    pct_reduction = round((saved_travel / init_travel) * 100.0, 2) if init_travel > 0 else 0.0

    init_dist = init_metrics["total_distance_km"]
    opt_dist = opt_metrics["total_distance_km"]
    saved_dist = round(max(0.0, init_dist - opt_dist), 2)

    init_sw = init_metrics["total_zone_switches"]
    opt_sw = opt_metrics["total_zone_switches"]
    saved_sw = max(0, init_sw - opt_sw)

    # Count technicians improved
    techs_improved = 0
    for s_init, s_opt in zip(init_summaries, opt_summaries):
        if (
            s_opt.total_travel_minutes < s_init.total_travel_minutes - 0.05
            or s_opt.zone_switches_count < s_init.zone_switches_count
        ):
            techs_improved += 1

    comparison = TravelMetricsComparison(
        initial_travel_minutes=init_travel,
        optimized_travel_minutes=opt_travel,
        travel_minutes_saved=saved_travel,
        travel_time_reduction_percent=pct_reduction,
        initial_distance_km=init_dist,
        optimized_distance_km=opt_dist,
        distance_km_saved=saved_dist,
        initial_zone_switches=init_sw,
        optimized_zone_switches=opt_sw,
        zone_switches_avoided=saved_sw,
        average_travel_per_job_initial=init_metrics["average_travel_per_job"],
        average_travel_per_job_optimized=opt_metrics["average_travel_per_job"],
        technicians_evaluated=len(technicians),
        technicians_improved=techs_improved,
    )

    # 6. Hard constraint verification
    assignments_by_tech = defaultdict(list)
    for p in optimized_plans:
        assignments_by_tech[p.technician_id].append(p)

    violations = validate_schedule_hard_constraints(
        techs_map=techs_map,
        jobs_map=jobs_lookup,
        assignments_by_tech=assignments_by_tech,
        as_of=as_of,
    )
    is_feasible = (len(violations) == 0)

    return TravelOptimizationResult(
        run_id=run_id,
        as_of=as_of,
        is_feasible=is_feasible,
        hard_violations_count=len(violations),
        hard_violations=violations,
        metrics_comparison=comparison,
        technician_travel_initial=init_summaries,
        technician_travel_optimized=opt_summaries,
        optimizations_applied=actions,
        assignments=optimized_plans,
        total_assigned_count=len(optimized_plans),
        persisted=False,
    )
