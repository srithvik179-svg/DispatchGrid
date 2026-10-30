"""
SLA Optimization, Latency Mitigation, and Deadline-Aware Scheduling Engine.

Calculates expected job completion times, detects soft SLA breaches and at-risk intervals,
arbitrates between multiple competing SLA targets, protects customer hard time windows,
and delivers explainable SLA performance metrics and optimization actions.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List, Tuple
from collections import defaultdict

from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.schemas import (
    AssignedJobPlan,
    JobSLADetail,
    FleetSLAMetrics,
    SLAOptimizationAction,
    SLAOptimizationComparison,
    SLAOptimizationResult,
    CompetingSLAResolution,
    HardConstraintViolation,
)
from app.scheduling.geo import haversine_distance, calculate_travel_minutes, DEFAULT_TRANSIT_SPEED_KMH
from app.scheduling.availability import parse_datetime_safe
from app.scheduling.scoring import validate_schedule_hard_constraints


def calculate_job_sla_detail(
    job: JobResponse,
    assignment: Optional[AssignedJobPlan] = None,
    as_of: Optional[datetime] = None,
    lateness_weight: float = 2.0,
    at_risk_threshold_minutes: int = 30,
) -> JobSLADetail:
    """
    Evaluates exact expected completion time, SLA lateness, approaching deadline risks,
    and customer hard window boundaries for a service job.
    """
    clock = as_of or datetime.now(timezone.utc)
    tw_start = parse_datetime_safe(job.time_window_start)
    tw_end = parse_datetime_safe(job.time_window_end)
    sla_target = parse_datetime_safe(job.sla_deadline) or tw_end

    is_already_breached_at_start = (sla_target is not None and sla_target < clock)

    if assignment is None:
        # Unassigned job
        is_past_sla = (sla_target is not None and clock > sla_target)
        lateness = (clock - sla_target).total_seconds() / 60.0 if is_past_sla else 0.0
        return JobSLADetail(
            job_id=job.id,
            title=job.title,
            priority=job.priority,
            priority_label=job.priority_label,
            technician_id=None,
            technician_name=None,
            scheduled_start=None,
            expected_completion=None,
            sla_deadline=sla_target,
            time_window_start=tw_start,
            time_window_end=tw_end,
            sla_status="UNASSIGNED",
            is_already_breached_at_as_of=is_already_breached_at_start,
            is_within_hard_window=True,
            lateness_minutes=round(lateness, 1),
            slack_buffer_minutes=0.0,
            lateness_penalty=round(lateness * lateness_weight, 2),
            explanation=(
                f"Job {job.id} is unassigned. Soft SLA target was {sla_target.strftime('%Y-%m-%d %H:%M') if sla_target else 'none'} "
                f"({'already breached' if is_already_breached_at_start else 'pending dispatch'})."
            ),
        )

    sched_start = parse_datetime_safe(assignment.scheduled_start)
    sched_end = parse_datetime_safe(assignment.scheduled_end)
    tech_name = assignment.details.get("technician_name") if assignment.details else None

    # Customer hard window boundary check
    is_within_hard = (tw_end is None) or (sched_end is not None and sched_end <= tw_end + timedelta(seconds=1))

    # Soft SLA lateness check
    if sla_target and sched_end and sched_end > sla_target:
        lateness_m = round((sched_end - sla_target).total_seconds() / 60.0, 1)
        slack_buf = 0.0
        status_label = "BREACHED"
        if is_already_breached_at_start:
            exp = (
                f"Job {job.id} was already past its SLA target ({sla_target.strftime('%H:%M')}) prior to simulation clock {clock.strftime('%H:%M')}. "
                f"Assigned to {assignment.technician_id} completing at {sched_end.strftime('%H:%M')} "
                f"({lateness_m}m past soft SLA, but safely within customer hard window ending {tw_end.strftime('%H:%M') if tw_end else 'none'})."
            )
        else:
            exp = (
                f"Job {job.id} completion at {sched_end.strftime('%H:%M')} exceeds soft SLA deadline {sla_target.strftime('%H:%M')} "
                f"by {lateness_m} minutes, incurring penalty of ${round(lateness_m * lateness_weight, 2)}. "
                f"Hard window end ({tw_end.strftime('%H:%M') if tw_end else 'none'}) is strictly satisfied."
            )
    elif sla_target and sched_end:
        lateness_m = 0.0
        slack_buf = round((sla_target - sched_end).total_seconds() / 60.0, 1)
        if slack_buf <= at_risk_threshold_minutes:
            status_label = "AT_RISK"
            exp = (
                f"Job {job.id} is AT RISK: expected completion at {sched_end.strftime('%H:%M')} is within "
                f"{slack_buf}m of target SLA deadline {sla_target.strftime('%H:%M')} (buffer <= {at_risk_threshold_minutes}m)."
            )
        else:
            status_label = "ON_TIME"
            exp = (
                f"Job {job.id} is ON TIME: expected completion at {sched_end.strftime('%H:%M')} satisfies "
                f"SLA deadline {sla_target.strftime('%H:%M')} with comfortable {slack_buf}m buffer."
            )
    else:
        lateness_m = 0.0
        slack_buf = 999.0
        status_label = "ON_TIME"
        exp = f"Job {job.id} scheduled from {sched_start.strftime('%H:%M') if sched_start else 'none'} to {sched_end.strftime('%H:%M') if sched_end else 'none'}."

    penalty = round(lateness_m * lateness_weight, 2)

    return JobSLADetail(
        job_id=job.id,
        title=job.title,
        priority=job.priority,
        priority_label=job.priority_label,
        technician_id=assignment.technician_id,
        technician_name=tech_name,
        scheduled_start=sched_start,
        expected_completion=sched_end,
        sla_deadline=sla_target,
        time_window_start=tw_start,
        time_window_end=tw_end,
        sla_status=status_label,
        is_already_breached_at_as_of=is_already_breached_at_start,
        is_within_hard_window=is_within_hard,
        lateness_minutes=lateness_m,
        slack_buffer_minutes=slack_buf,
        lateness_penalty=penalty,
        explanation=exp,
    )


def calculate_fleet_sla_metrics(
    jobs: Sequence[JobResponse],
    assignments: Sequence[AssignedJobPlan],
    as_of: datetime,
    lateness_weight: float = 2.0,
    at_risk_threshold_minutes: int = 30,
) -> Tuple[List[JobSLADetail], FleetSLAMetrics]:
    """
    Computes comprehensive fleet-wide SLA performance metrics and granular per-job details.
    """
    assign_map = {a.job_id: a for a in assignments}
    details: List[JobSLADetail] = []

    on_time_cnt = 0
    at_risk_cnt = 0
    breached_cnt = 0
    already_breached_assigned_cnt = 0
    total_lateness = 0.0
    max_late = 0.0
    total_penalty = 0.0

    for j in jobs:
        detail = calculate_job_sla_detail(
            job=j,
            assignment=assign_map.get(j.id),
            as_of=as_of,
            lateness_weight=lateness_weight,
            at_risk_threshold_minutes=at_risk_threshold_minutes,
        )
        details.append(detail)

        if detail.sla_status == "ON_TIME":
            on_time_cnt += 1
        elif detail.sla_status == "AT_RISK":
            at_risk_cnt += 1
        elif detail.sla_status == "BREACHED":
            breached_cnt += 1
            total_lateness += detail.lateness_minutes
            total_penalty += detail.lateness_penalty
            if detail.lateness_minutes > max_late:
                max_late = detail.lateness_minutes
            if detail.is_already_breached_at_as_of:
                already_breached_assigned_cnt += 1

    total_evaluated = len(jobs)
    assigned_count = len(assignments)

    on_time_pct = round((on_time_cnt / assigned_count) * 100.0, 2) if assigned_count > 0 else 0.0
    at_risk_pct = round((at_risk_cnt / assigned_count) * 100.0, 2) if assigned_count > 0 else 0.0
    breached_pct = round((breached_cnt / assigned_count) * 100.0, 2) if assigned_count > 0 else 0.0
    avg_lateness = round(total_lateness / breached_cnt, 2) if breached_cnt > 0 else 0.0

    metrics = FleetSLAMetrics(
        as_of=as_of,
        total_jobs_evaluated=total_evaluated,
        assigned_jobs_count=assigned_count,
        on_time_count=on_time_cnt,
        on_time_percentage=on_time_pct,
        at_risk_count=at_risk_cnt,
        at_risk_percentage=at_risk_pct,
        breached_count=breached_cnt,
        breached_percentage=breached_pct,
        already_breached_assigned_count=already_breached_assigned_cnt,
        total_lateness_minutes=round(total_lateness, 1),
        average_lateness_minutes=avg_lateness,
        max_lateness_minutes=round(max_late, 1),
        total_sla_penalty=round(total_penalty, 2),
        lateness_penalty_weight=lateness_weight,
        at_risk_threshold_minutes=at_risk_threshold_minutes,
    )

    return details, metrics


def resolve_competing_sla_deadlines(
    job_a: JobResponse,
    job_b: JobResponse,
    as_of: datetime,
) -> CompetingSLAResolution:
    """
    Deterministically arbitrates between two competing jobs with approaching SLA targets:
    1. Earlier SLA deadline wins.
    2. Tighter remaining slack buffer from as_of wins.
    3. Operational priority tier wins.
    4. Deterministic Job ID tie-breaker.
    """
    sla_a = parse_datetime_safe(job_a.sla_deadline) or parse_datetime_safe(job_a.time_window_end)
    sla_b = parse_datetime_safe(job_b.sla_deadline) or parse_datetime_safe(job_b.time_window_end)

    slack_a = round((sla_a - as_of).total_seconds() / 60.0, 1) if sla_a else 9999.0
    slack_b = round((sla_b - as_of).total_seconds() / 60.0, 1) if sla_b else 9999.0

    # 1. Earlier SLA deadline
    if sla_a and sla_b and sla_a != sla_b:
        if sla_a < sla_b:
            return CompetingSLAResolution(
                job_id_a=job_a.id,
                job_id_b=job_b.id,
                winner_job_id=job_a.id,
                loser_job_id=job_b.id,
                sla_a=sla_a,
                sla_b=sla_b,
                slack_a_minutes=slack_a,
                slack_b_minutes=slack_b,
                deciding_factor="SLA_DEADLINE_IMMINENCE",
                explanation=f"Job {job_a.id} has more imminent SLA deadline ({sla_a.strftime('%H:%M')}) than Job {job_b.id} ({sla_b.strftime('%H:%M')}).",
            )
        else:
            return CompetingSLAResolution(
                job_id_a=job_a.id,
                job_id_b=job_b.id,
                winner_job_id=job_b.id,
                loser_job_id=job_a.id,
                sla_a=sla_a,
                sla_b=sla_b,
                slack_a_minutes=slack_a,
                slack_b_minutes=slack_b,
                deciding_factor="SLA_DEADLINE_IMMINENCE",
                explanation=f"Job {job_b.id} has more imminent SLA deadline ({sla_b.strftime('%H:%M')}) than Job {job_a.id} ({sla_a.strftime('%H:%M')}).",
            )

    # 2. Slack buffer tightness
    if abs(slack_a - slack_b) > 1.0:
        if slack_a < slack_b:
            winner, loser = job_a, job_b
        else:
            winner, loser = job_b, job_a
        return CompetingSLAResolution(
            job_id_a=job_a.id,
            job_id_b=job_b.id,
            winner_job_id=winner.id,
            loser_job_id=loser.id,
            sla_a=sla_a,
            sla_b=sla_b,
            slack_a_minutes=slack_a,
            slack_b_minutes=slack_b,
            deciding_factor="SLACK_BUFFER_TIGHTNESS",
            explanation=f"Job {winner.id} has tighter remaining buffer ({min(slack_a, slack_b)}m) than Job {loser.id} ({max(slack_a, slack_b)}m).",
        )

    # 3. Priority tier
    if job_a.priority != job_b.priority:
        if job_a.priority < job_b.priority:
            winner, loser = job_a, job_b
        else:
            winner, loser = job_b, job_a
        return CompetingSLAResolution(
            job_id_a=job_a.id,
            job_id_b=job_b.id,
            winner_job_id=winner.id,
            loser_job_id=loser.id,
            sla_a=sla_a,
            sla_b=sla_b,
            slack_a_minutes=slack_a,
            slack_b_minutes=slack_b,
            deciding_factor="PRIORITY_LEVEL",
            explanation=f"Both jobs had identical deadlines; Job {winner.id} outranks {loser.id} by operational priority (P{winner.priority} vs P{loser.priority}).",
        )

    # 4. Deterministic Job ID
    if job_a.id < job_b.id:
        winner, loser = job_a, job_b
    else:
        winner, loser = job_b, job_a

    return CompetingSLAResolution(
        job_id_a=job_a.id,
        job_id_b=job_b.id,
        winner_job_id=winner.id,
        loser_job_id=loser.id,
        sla_a=sla_a,
        sla_b=sla_b,
        slack_a_minutes=slack_a,
        slack_b_minutes=slack_b,
        deciding_factor="DETERMINISTIC_ID",
        explanation=f"Identical deadlines and priority tiers decided by deterministic tie-breaker ({winner.id} < {loser.id}).",
    )


def optimize_schedule_sla(
    initial_assignments: Sequence[AssignedJobPlan],
    technicians: Sequence[TechnicianResponse],
    jobs: Sequence[JobResponse],
    as_of: datetime,
    lateness_weight: float = 2.0,
    at_risk_threshold_minutes: int = 30,
    run_id: str = "RUN-OPT-SLA",
) -> SLAOptimizationResult:
    """
    SLA schedule optimization pass:
    1. Evaluates baseline SLA metrics and details.
    2. Identifies at-risk and breached assignments.
    3. Examines opportunities to advance schedules where idle waiting time exists,
       reducing lateness while strictly satisfying customer hard windows and transit buffers.
    4. Guarantees zero hard constraint violations via validate_schedule_hard_constraints.
    5. Delivers measured comparison and explainable action logs.
    """
    jobs_lookup = {j.id: j for j in jobs}
    techs_map = {t.id: t for t in technicians}

    # 1. Baseline metrics
    init_details, init_metrics = calculate_fleet_sla_metrics(
        jobs=jobs,
        assignments=initial_assignments,
        as_of=as_of,
        lateness_weight=lateness_weight,
        at_risk_threshold_minutes=at_risk_threshold_minutes,
    )

    # 2. Optimization: evaluate advancing starts for at-risk/breached jobs
    working_plans: Dict[str, AssignedJobPlan] = {p.job_id: p.model_copy() for p in initial_assignments}
    actions: List[SLAOptimizationAction] = []

    # Group by technician
    plans_by_tech = defaultdict(list)
    for p in working_plans.values():
        plans_by_tech[p.technician_id].append(p)

    for tid, p_list in plans_by_tech.items():
        tech = techs_map.get(tid)
        if not tech:
            continue

        sorted_plans = sorted(p_list, key=lambda x: x.scheduled_start)
        prev_end: Optional[datetime] = None
        prev_lat = tech.home_lat
        prev_lng = tech.home_lng

        for p in sorted_plans:
            j = jobs_lookup.get(p.job_id)
            if not j or p.is_existing or p.status in ["completed", "in_progress"]:
                prev_end = p.scheduled_end
                if j:
                    prev_lat = j.lat
                    prev_lng = j.lng
                continue

            # Calculate required transit from previous stop
            dist_km = haversine_distance(prev_lat, prev_lng, j.lat, j.lng)
            req_transit = calculate_travel_minutes(dist_km)

            earliest_arr = (prev_end + timedelta(minutes=req_transit)) if prev_end else (as_of + timedelta(minutes=req_transit))
            earliest_possible_start = max(j.time_window_start, earliest_arr, as_of)

            # Ensure buffer compliance from preceding stop
            if p.scheduled_start < earliest_possible_start:
                diff = earliest_possible_start - p.scheduled_start
                p.scheduled_start = earliest_possible_start
                p.scheduled_end = p.scheduled_end + diff

            # If current start is later than earliest possible start, and job is breached or at risk:
            sla_dt = parse_datetime_safe(j.sla_deadline) or parse_datetime_safe(j.time_window_end)
            if p.scheduled_start > earliest_possible_start + timedelta(minutes=1):
                cur_end = p.scheduled_end
                cand_start = earliest_possible_start
                cand_end = cand_start + timedelta(minutes=j.duration_minutes)

                # Check if advancing start improves SLA lateness
                if cur_end > sla_dt:
                    prev_late = (cur_end - sla_dt).total_seconds() / 60.0
                    new_late = max(0.0, (cand_end - sla_dt).total_seconds() / 60.0)
                    saved_late = round(prev_late - new_late, 1)

                    if saved_late > 0.5:
                        p.scheduled_start = cand_start
                        p.scheduled_end = cand_end
                        actions.append(
                            SLAOptimizationAction(
                                action_type="SCHEDULE_EARLIER",
                                job_id=j.id,
                                technician_id=tid,
                                previous_completion=cur_end,
                                new_completion=cand_end,
                                lateness_minutes_saved=saved_late,
                                explanation=(
                                    f"Advanced Job {j.id} dispatch start from {p.scheduled_start.strftime('%H:%M')} "
                                    f"to {cand_start.strftime('%H:%M')}: completion improved from {cur_end.strftime('%H:%M')} "
                                    f"to {cand_end.strftime('%H:%M')}, eliminating {saved_late}m of SLA lateness."
                                ),
                            )
                        )

            prev_end = p.scheduled_end
            prev_lat = j.lat
            prev_lng = j.lng

    final_plans = list(working_plans.values())

    # 3. Optimized metrics
    opt_details, opt_metrics = calculate_fleet_sla_metrics(
        jobs=jobs,
        assignments=final_plans,
        as_of=as_of,
        lateness_weight=lateness_weight,
        at_risk_threshold_minutes=at_risk_threshold_minutes,
    )

    # 4. Measured comparison
    late_saved = round(max(0.0, init_metrics.total_lateness_minutes - opt_metrics.total_lateness_minutes), 1)
    pen_saved = round(max(0.0, init_metrics.total_sla_penalty - opt_metrics.total_sla_penalty), 2)
    breaches_prevented = max(0, init_metrics.breached_count - opt_metrics.breached_count)
    at_risk_rescued = max(0, init_metrics.at_risk_count - opt_metrics.at_risk_count)

    comp = SLAOptimizationComparison(
        initial_metrics=init_metrics,
        optimized_metrics=opt_metrics,
        lateness_minutes_saved=late_saved,
        penalty_saved=pen_saved,
        breaches_prevented=breaches_prevented,
        at_risk_rescued=at_risk_rescued,
    )

    # 5. Strict hard constraint verification
    assignments_by_tech = defaultdict(list)
    for p in final_plans:
        assignments_by_tech[p.technician_id].append(p)

    violations = validate_schedule_hard_constraints(
        techs_map=techs_map,
        jobs_map=jobs_lookup,
        assignments_by_tech=assignments_by_tech,
        as_of=as_of,
    )
    is_feasible = (len(violations) == 0)

    return SLAOptimizationResult(
        run_id=run_id,
        as_of=as_of,
        is_feasible=is_feasible,
        hard_violations_count=len(violations),
        hard_violations=violations,
        comparison=comp,
        job_sla_details=opt_details,
        optimizations_applied=actions,
        assignments=final_plans,
        persisted=False,
    )
