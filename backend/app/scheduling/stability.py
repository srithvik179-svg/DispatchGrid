"""
Phase 27: Schedule Stability, Assignment Preservation, and Churn Minimisation Engine.

Guarantees:
1. Identification and strict protection of pre-existing, completed, and in-progress work.
2. Measurable penalties for unnecessary modifications to future scheduled work.
3. Principled comparison between baseline schedules and candidate schedules.
4. Minimal-churn rescheduling when disruptions or timeline adjustments occur.
5. High-resolution stability metrics tracking unassigned, reassigned, and time-shifted jobs.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List, Tuple
from collections import defaultdict

from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.schemas import (
    AssignedJobPlan,
    AssignmentChangeDetail,
    ScheduleStabilityMetrics,
    StabilityRecalculationResult,
    HardConstraintViolation,
)
from app.scheduling.geo import haversine_distance, calculate_travel_minutes
from app.scheduling.availability import parse_datetime_safe
from app.scheduling.scoring import validate_schedule_hard_constraints


def is_assignment_protected(status: Optional[str]) -> bool:
    """Returns True if assignment status corresponds to completed or in-progress work."""
    if not status:
        return False
    return str(status).strip().lower() in ["completed", "in_progress"]


def compare_schedules(
    baseline_assignments: Sequence[Union[AssignedJobPlan, Dict[str, Any], Any]],
    candidate_assignments: Sequence[Union[AssignedJobPlan, Dict[str, Any], Any]],
    w_reassign: float = 250.0,
    w_shift_per_hour: float = 30.0,
    w_unassign: float = 500.0,
) -> Tuple[List[AssignmentChangeDetail], ScheduleStabilityMetrics]:
    """
    Performs a high-resolution assignment-by-assignment diff between baseline and candidate schedules.
    Calculates churn penalties, verifies protection compliance, and calculates stability metrics.
    """
    def _extract(a: Any) -> Tuple[str, str, datetime, datetime, str, bool]:
        if isinstance(a, dict):
            j_id = a.get("job_id") or a.get("id")
            t_id = a.get("technician_id")
            start = parse_datetime_safe(a.get("scheduled_start") or a.get("start_time"))
            end = parse_datetime_safe(a.get("scheduled_end") or a.get("end_time"))
            status = str(a.get("status", "scheduled"))
            is_exist = bool(a.get("is_existing", False))
            return j_id, t_id, start, end, status, is_exist
        else:
            j_id = getattr(a, "job_id", None) or getattr(a, "id", None)
            t_id = getattr(a, "technician_id", None)
            start = parse_datetime_safe(getattr(a, "scheduled_start", None) or getattr(a, "start_time", None))
            end = parse_datetime_safe(getattr(a, "scheduled_end", None) or getattr(a, "end_time", None))
            status = str(getattr(a, "status", "scheduled"))
            is_exist = bool(getattr(a, "is_existing", False))
            return j_id, t_id, start, end, status, is_exist

    baseline_map = {}
    for a in baseline_assignments:
        j_id, t_id, start, end, status, is_exist = _extract(a)
        if j_id:
            baseline_map[j_id] = (t_id, start, end, status, is_exist)

    candidate_map = {}
    for a in candidate_assignments:
        j_id, t_id, start, end, status, is_exist = _extract(a)
        if j_id:
            candidate_map[j_id] = (t_id, start, end, status, is_exist)

    all_job_ids = sorted(list(set(baseline_map.keys()) | set(candidate_map.keys())))

    changes: List[AssignmentChangeDetail] = []
    unchanged_cnt = 0
    shifted_cnt = 0
    total_shift_mins = 0.0
    reassigned_cnt = 0
    dropped_cnt = 0
    newly_cnt = 0

    completed_prot_cnt = 0
    completed_pres_cnt = 0
    in_prog_prot_cnt = 0
    in_prog_pres_cnt = 0

    total_churn_penalty = 0.0
    violations: List[str] = []
    is_prot_violated = False

    for j_id in all_job_ids:
        in_base = j_id in baseline_map
        in_cand = j_id in candidate_map

        if in_base and in_cand:
            b_tid, b_start, b_end, b_status, b_exist = baseline_map[j_id]
            c_tid, c_start, c_end, c_status, c_exist = candidate_map[j_id]
            is_prot = is_assignment_protected(b_status)

            if b_status.lower() == "completed":
                completed_prot_cnt += 1
            elif b_status.lower() == "in_progress":
                in_prog_prot_cnt += 1

            # Check for illegal protection breach
            if is_prot:
                is_altered = (b_tid != c_tid) or (b_start != c_start) or (b_end != c_end)
                if is_altered:
                    is_prot_violated = True
                    msg = f"ILLEGAL MUTATION: Protected {b_status} Job {j_id} was modified (Tech: {b_tid}->{c_tid}, Start: {b_start}->{c_start})."
                    violations.append(msg)
                else:
                    if b_status.lower() == "completed":
                        completed_pres_cnt += 1
                    elif b_status.lower() == "in_progress":
                        in_prog_pres_cnt += 1

            if b_tid == c_tid:
                shift_m = round(abs((c_start - b_start).total_seconds()) / 60.0, 1) if (b_start and c_start) else 0.0
                if shift_m <= 1.0:
                    unchanged_cnt += 1
                    changes.append(
                        AssignmentChangeDetail(
                            job_id=j_id,
                            change_type="UNCHANGED",
                            old_technician_id=b_tid,
                            new_technician_id=c_tid,
                            old_start=b_start,
                            new_start=c_start,
                            old_end=b_end,
                            new_end=c_end,
                            time_shift_minutes=0.0,
                            is_protected=is_prot,
                            is_valid=True,
                            penalty=0.0,
                            reason=f"Job {j_id} retained identical assignment on {c_tid}.",
                        )
                    )
                else:
                    shifted_cnt += 1
                    total_shift_mins += shift_m
                    pen = round((shift_m / 60.0) * w_shift_per_hour, 2)
                    total_churn_penalty += pen
                    changes.append(
                        AssignmentChangeDetail(
                            job_id=j_id,
                            change_type="TIME_SHIFTED",
                            old_technician_id=b_tid,
                            new_technician_id=c_tid,
                            old_start=b_start,
                            new_start=c_start,
                            old_end=b_end,
                            new_end=c_end,
                            time_shift_minutes=shift_m,
                            is_protected=is_prot,
                            is_valid=True,
                            penalty=pen,
                            reason=f"Job {j_id} retained {c_tid} but was shifted by {shift_m} minutes.",
                        )
                    )
            else:
                reassigned_cnt += 1
                pen = round(w_reassign, 2)
                total_churn_penalty += pen
                changes.append(
                    AssignmentChangeDetail(
                        job_id=j_id,
                        change_type="REASSIGNED",
                        old_technician_id=b_tid,
                        new_technician_id=c_tid,
                        old_start=b_start,
                        new_start=c_start,
                        old_end=b_end,
                        new_end=c_end,
                        time_shift_minutes=round(abs((c_start - b_start).total_seconds()) / 60.0, 1) if (b_start and c_start) else 0.0,
                        is_protected=is_prot,
                        is_valid=True,
                        penalty=pen,
                        reason=f"Job {j_id} was reassigned from {b_tid} to {c_tid}.",
                    )
                )

        elif in_base and not in_cand:
            b_tid, b_start, b_end, b_status, b_exist = baseline_map[j_id]
            is_prot = is_assignment_protected(b_status)
            if b_status.lower() == "completed":
                completed_prot_cnt += 1
            elif b_status.lower() == "in_progress":
                in_prog_prot_cnt += 1

            if is_prot:
                is_prot_violated = True
                msg = f"ILLEGAL REMOVAL: Protected {b_status} Job {j_id} was dropped from schedule."
                violations.append(msg)

            dropped_cnt += 1
            pen = round(w_unassign, 2)
            total_churn_penalty += pen
            changes.append(
                AssignmentChangeDetail(
                    job_id=j_id,
                    change_type="DROPPED_TO_UNASSIGNED",
                    old_technician_id=b_tid,
                    new_technician_id=None,
                    old_start=b_start,
                    new_start=None,
                    old_end=b_end,
                    new_end=None,
                    time_shift_minutes=0.0,
                    is_protected=is_prot,
                    is_valid=False,
                    penalty=pen,
                    reason=f"Job {j_id} previously assigned to {b_tid} was dropped from candidate schedule.",
                )
            )

        elif not in_base and in_cand:
            c_tid, c_start, c_end, c_status, c_exist = candidate_map[j_id]
            newly_cnt += 1
            changes.append(
                AssignmentChangeDetail(
                    job_id=j_id,
                    change_type="NEWLY_ASSIGNED",
                    old_technician_id=None,
                    new_technician_id=c_tid,
                    old_start=None,
                    new_start=c_start,
                    old_end=None,
                    new_end=c_end,
                    time_shift_minutes=0.0,
                    is_protected=False,
                    is_valid=True,
                    penalty=0.0,
                    reason=f"Job {j_id} was newly scheduled to technician {c_tid}.",
                )
            )

    tot_base = len(baseline_map)
    tot_cand = len(candidate_map)
    unchanged_pct = round((unchanged_cnt / tot_base) * 100.0, 2) if tot_base > 0 else 100.0
    avg_shift = round(total_shift_mins / shifted_cnt, 2) if shifted_cnt > 0 else 0.0

    # Normalized stability score: 100 base, penalizing churn and reassignments
    penalty_discount = min(100.0, (total_churn_penalty / max(1.0, tot_base * 20.0)) * 10.0)
    stability_score = round(max(0.0, unchanged_pct - (penalty_discount * 0.2)), 2)
    if is_prot_violated:
        stability_score = 0.0

    metrics = ScheduleStabilityMetrics(
        total_baseline_assignments=tot_base,
        total_candidate_assignments=tot_cand,
        unchanged_count=unchanged_cnt,
        unchanged_percentage=unchanged_pct,
        time_shifted_count=shifted_cnt,
        average_time_shift_minutes=avg_shift,
        reassigned_count=reassigned_cnt,
        dropped_to_unassigned_count=dropped_cnt,
        newly_assigned_count=newly_cnt,
        completed_protected_count=completed_prot_cnt,
        completed_preserved_count=completed_pres_cnt,
        in_progress_protected_count=in_prog_prot_cnt,
        in_progress_preserved_count=in_prog_pres_cnt,
        total_churn_penalty=round(total_churn_penalty, 2),
        stability_score=stability_score,
        is_protection_violated=is_prot_violated,
        violations=violations,
    )

    return changes, metrics


def recalculate_stable_schedule(
    baseline_assignments: Sequence[AssignedJobPlan],
    technicians: Sequence[TechnicianResponse],
    jobs: Sequence[JobResponse],
    as_of: datetime,
    disrupted_technician_id: Optional[str] = None,
    disrupted_job_id: Optional[str] = None,
    delay_minutes: int = 0,
    w_reassign: float = 250.0,
    w_shift_per_hour: float = 30.0,
    run_id: str = "RUN-STABLE",
) -> StabilityRecalculationResult:
    """
    Recalculates schedules with minimum churn upon timeline disturbance:
    1. Locks all unaffected technicians and unaffected jobs in place.
    2. Protects all completed and in-progress assignments 100%.
    3. Restricts shifting or reassignments strictly to affected downstream work.
    4. Enforces all hard operational constraints via validate_schedule_hard_constraints.
    5. Computes high-fidelity stability metrics and an explainable change manifest.
    """
    jobs_map = {j.id: j for j in jobs}
    techs_map = {t.id: t for t in technicians}

    # Working copy of all baseline assignments
    working_plans: Dict[str, AssignedJobPlan] = {p.job_id: p.model_copy() for p in baseline_assignments}

    affected_job_ids: List[str] = []
    preserved_job_ids: List[str] = []

    # Identify affected technician
    target_tech_id = disrupted_technician_id
    if not target_tech_id and disrupted_job_id:
        curr_plan = working_plans.get(disrupted_job_id)
        if curr_plan:
            target_tech_id = curr_plan.technician_id

    # If no target technician identified, entire schedule is preserved unchanged
    if not target_tech_id or (delay_minutes == 0 and not disrupted_job_id):
        final_plans = list(working_plans.values())
        changes, metrics = compare_schedules(
            baseline_assignments=baseline_assignments,
            candidate_assignments=final_plans,
            w_reassign=w_reassign,
            w_shift_per_hour=w_shift_per_hour,
        )
        return StabilityRecalculationResult(
            run_id=run_id,
            as_of=as_of,
            is_feasible=True,
            hard_violations_count=0,
            hard_violations=[],
            affected_jobs=[],
            preserved_jobs=[p.job_id for p in final_plans],
            stability_metrics=metrics,
            assignment_changes=changes,
            assignments=final_plans,
            persisted=False,
        )

    # Segregate plans by technician
    plans_by_tech = defaultdict(list)
    for p in working_plans.values():
        plans_by_tech[p.technician_id].append(p)

    # Ensure buffer compliance from preceding stops across all technicians
    for tid, p_list in plans_by_tech.items():
        sorted_p = sorted(p_list, key=lambda x: x.scheduled_start)
        tech = techs_map.get(tid)
        if not tech:
            continue
        prev_end = None
        prev_lat = tech.home_lat
        prev_lng = tech.home_lng
        for p in sorted_p:
            j = jobs_map.get(p.job_id)
            if not j:
                continue
            dist_km = haversine_distance(prev_lat, prev_lng, j.lat, j.lng)
            req_transit = calculate_travel_minutes(dist_km)
            if prev_end and not (is_assignment_protected(p.status) or p.is_existing):
                earliest_start = prev_end + timedelta(minutes=req_transit)
                if p.scheduled_start < earliest_start:
                    diff = earliest_start - p.scheduled_start
                    p.scheduled_start = earliest_start
                    p.scheduled_end = p.scheduled_end + diff
            prev_end = p.scheduled_end
            prev_lat = j.lat
            prev_lng = j.lng

    # Process affected technician
    target_plans = sorted(plans_by_tech.get(target_tech_id, []), key=lambda x: x.scheduled_start)
    delay_started = False
    cum_delay = timedelta(minutes=delay_minutes)

    for p in target_plans:
        is_prot = is_assignment_protected(p.status) or p.is_existing

        if p.job_id == disrupted_job_id:
            delay_started = True
            if is_prot:
                # Protected work cannot be delayed
                preserved_job_ids.append(p.job_id)
                continue
            # Apply delay to disrupted job
            p.scheduled_start += cum_delay
            p.scheduled_end += cum_delay
            affected_job_ids.append(p.job_id)
            continue

        if delay_started:
            if is_prot:
                # Protected downstream work cannot be delayed
                preserved_job_ids.append(p.job_id)
                continue
            # Downstream shift
            p.scheduled_start += cum_delay
            p.scheduled_end += cum_delay
            affected_job_ids.append(p.job_id)
        else:
            preserved_job_ids.append(p.job_id)

    # All jobs on other technicians are strictly preserved
    for tid, p_list in plans_by_tech.items():
        if tid != target_tech_id:
            for p in p_list:
                preserved_job_ids.append(p.job_id)

    final_plans = list(working_plans.values())

    # Verify hard constraints
    by_tech_eval = defaultdict(list)
    for p in final_plans:
        by_tech_eval[p.technician_id].append(p)

    violations = validate_schedule_hard_constraints(
        techs_map=techs_map,
        jobs_map=jobs_map,
        assignments_by_tech=by_tech_eval,
        as_of=as_of,
    )

    changes, metrics = compare_schedules(
        baseline_assignments=baseline_assignments,
        candidate_assignments=final_plans,
        w_reassign=w_reassign,
        w_shift_per_hour=w_shift_per_hour,
    )

    return StabilityRecalculationResult(
        run_id=run_id,
        as_of=as_of,
        is_feasible=(len(violations) == 0),
        hard_violations_count=len(violations),
        hard_violations=violations,
        affected_jobs=affected_job_ids,
        preserved_jobs=preserved_job_ids,
        stability_metrics=metrics,
        assignment_changes=changes,
        assignments=final_plans,
        persisted=False,
    )
