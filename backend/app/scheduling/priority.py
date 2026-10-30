"""
Priority-aware scheduling optimization, candidate comparison, and conflict resolution engine.

DOCUMENTED HIERARCHICAL TIE-BREAKING & ORDERING RULES:
------------------------------------------------------
When resolving competing jobs for limited technician capacity, jobs are ordered by:
1. Tier 1 – Operational Priority Level:
   Priority 1 (Urgent) > Priority 2 (High) > Priority 3 (Medium) > Priority 4 (Low).
   Urgent jobs ALWAYS receive scheduling priority over all lower-priority tiers.

2. Tier 2 – Technician Scarcity (Qualification Difficulty):
   Jobs with fewer qualified fleet technicians (skills, equipment, and zone eligible)
   are scheduled BEFORE jobs with abundant technician options. This strictly prevents
   widely-serviceable jobs from consuming rare, specialized technician capacity.

3. Tier 3 – Time Window Tightness (Slack Buffer):
   Tightness ratio = duration_minutes / total_window_minutes.
   Jobs with higher tightness ratios (closer to 1.0, minimum scheduling flexibility)
   are prioritized ahead of loose windows with extensive scheduling slack.

4. Tier 4 – Imminent Soft SLA Target Deadline:
   Jobs with earlier soft SLA deadlines are prioritized to minimize punctuality delay penalties.

5. Tier 5 – Hard Time-Window End:
   Earlier customer expiration boundaries are dispatched before later horizons.

6. Tier 6 – Earliest Permissible Window Start:
   Jobs whose service window opens earlier are scheduled ahead of later windows.

7. Tier 7 – Deterministic Tie-Breaker:
   Lexicographical alphanumeric ascending Job ID (e.g. JOB-011 < JOB-032).
   Guarantees 100% reproducible execution across identical input sets.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List, Tuple

from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.schemas import (
    JobPriorityProfile,
    CompetingJobResolution,
)
from app.scheduling.skills import check_technician_skills, DEFAULT_UNSUPPORTED_SKILLS
from app.scheduling.equipment import check_technician_equipment
from app.scheduling.geo import check_zone_eligibility, haversine_distance, calculate_travel_minutes
from app.scheduling.availability import parse_datetime_safe


def calculate_job_priority_profile(
    job: JobResponse,
    technicians: Sequence[TechnicianResponse],
    unsupported_skills: Sequence[str] = DEFAULT_UNSUPPORTED_SKILLS,
) -> JobPriorityProfile:
    """
    Computes a comprehensive multi-criteria priority and scarcity profile for a job.
    Evaluates exact qualified technicians holding required skills, equipment, and zone eligibility.
    """
    job_skills = [s.strip().lower() for s in (job.required_skills or []) if s.strip()]
    job_equip = [e.strip().lower() for e in (job.required_equipment or []) if e.strip()]
    norm_unsupported = {u.strip().lower() for u in unsupported_skills}

    qualified_tech_ids: List[str] = []

    # If job has unsupported skill, qualified count is 0
    if not any(s in norm_unsupported for s in job_skills):
        for tech in technicians:
            # 1. Skill check (required_skills, technician_skills)
            s_res = check_technician_skills(
                required_skills=job_skills,
                technician_skills=tech.skills or [],
                technician_id=tech.id,
                unsupported_skills=unsupported_skills,
            )
            if not s_res.is_eligible:
                continue

            # 2. Equipment check (required_equipment, technician_equipment)
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

            qualified_tech_ids.append(tech.id)

    # Calculate window tightness ratio and slack
    tw_start = parse_datetime_safe(job.time_window_start) or datetime.min.replace(tzinfo=timezone.utc)
    tw_end = parse_datetime_safe(job.time_window_end) or tw_start + timedelta(minutes=job.duration_minutes)
    window_total_minutes = max(1.0, (tw_end - tw_start).total_seconds() / 60.0)

    duration_mins = float(job.duration_minutes)
    tightness_ratio = round(min(1.0, duration_mins / window_total_minutes), 4)
    slack_minutes = round(max(0.0, window_total_minutes - duration_mins), 1)

    sla_dt = parse_datetime_safe(job.sla_deadline) or tw_end

    tie_key = f"P{job.priority}-S{len(qualified_tech_ids):02d}-T{int(tightness_ratio*1000):04d}-{job.id}"

    return JobPriorityProfile(
        job_id=job.id,
        priority=job.priority,
        priority_label=job.priority_label,
        qualified_technicians_count=len(qualified_tech_ids),
        qualified_technician_ids=qualified_tech_ids,
        window_duration_ratio=tightness_ratio,
        window_slack_minutes=slack_minutes,
        sla_deadline=sla_dt,
        time_window_start=tw_start,
        time_window_end=tw_end,
        tie_breaker_key=tie_key,
    )


def prioritize_jobs_with_scarcity(
    jobs: Sequence[JobResponse],
    technicians: Sequence[TechnicianResponse],
    unsupported_skills: Sequence[str] = DEFAULT_UNSUPPORTED_SKILLS,
) -> List[JobResponse]:
    """
    Rigorously orders pending service jobs using the documented 7-tier criteria:
    1. Priority level (1=Urgent > 2=High > 3=Medium > 4=Low)
    2. Technician scarcity (fewer qualified technicians first; unassignable 0 placed at back of tier)
    3. Time window tightness ratio (highest tightness / least slack first)
    4. Imminent SLA deadline (earliest target deadline first)
    5. Hard time window end (earliest hard deadline first)
    6. Hard time window start (earliest opening first)
    7. Deterministic tie-breaker: Job ID alphanumeric ascending
    """
    profiles: Dict[str, JobPriorityProfile] = {
        j.id: calculate_job_priority_profile(j, technicians, unsupported_skills)
        for j in jobs
    }

    def sort_key(job: JobResponse):
        prof = profiles[job.id]

        # For scarcity: jobs with 0 qualified candidates cannot be scheduled anyway,
        # but amongst assignable jobs, fewer candidates = higher scheduling urgency.
        # So assignable jobs (count >= 1) sorted by count ascending (1, 2, 3...),
        # while count == 0 placed after assignable jobs of the same priority level.
        effective_scarcity = prof.qualified_technicians_count if prof.qualified_technicians_count > 0 else 9999

        # Invert tightness ratio so higher ratio (near 1.0) sorts first
        inverted_tightness = -prof.window_duration_ratio

        return (
            prof.priority,                # Tier 1: 1 Urgent first
            effective_scarcity,           # Tier 2: Scarcity of qualified technicians
            inverted_tightness,           # Tier 3: Tighter windows first
            prof.sla_deadline,            # Tier 4: Earliest SLA target
            prof.time_window_end,         # Tier 5: Earliest hard deadline
            prof.time_window_start,       # Tier 6: Earliest window start
            job.id,                       # Tier 7: Deterministic tie-breaker
        )

    return sorted(jobs, key=sort_key)


def resolve_competing_jobs(
    job_a: JobResponse,
    job_b: JobResponse,
    technicians: Sequence[TechnicianResponse],
    unsupported_skills: Sequence[str] = DEFAULT_UNSUPPORTED_SKILLS,
) -> CompetingJobResolution:
    """
    Deterministically arbitrates between two competing jobs that contend for identical
    technician capabilities, territories, or overlapping time windows.
    Returns the winner, loser, deciding tier, and full explanatory rationale.
    """
    prof_a = calculate_job_priority_profile(job_a, technicians, unsupported_skills)
    prof_b = calculate_job_priority_profile(job_b, technicians, unsupported_skills)

    # Tier 1: Priority Level
    if prof_a.priority != prof_b.priority:
        if prof_a.priority < prof_b.priority:
            winner, loser = prof_a, prof_b
        else:
            winner, loser = prof_b, prof_a
        return CompetingJobResolution(
            winner_job_id=winner.job_id,
            loser_job_id=loser.job_id,
            deciding_factor="PRIORITY_LEVEL",
            explanation=f"Job {winner.job_id} ({winner.priority_label.upper()}, P{winner.priority}) outranks Job {loser.job_id} ({loser.priority_label.upper()}, P{loser.priority}) by operational urgency tier.",
            job_a_profile=prof_a,
            job_b_profile=prof_b,
        )

    # Tier 2: Technician Scarcity (Qualification Difficulty)
    # Both assignable: fewer qualified technicians wins
    count_a = prof_a.qualified_technicians_count
    count_b = prof_b.qualified_technicians_count
    if count_a > 0 and count_b > 0 and count_a != count_b:
        if count_a < count_b:
            winner, loser = prof_a, prof_b
        else:
            winner, loser = prof_b, prof_a
        return CompetingJobResolution(
            winner_job_id=winner.job_id,
            loser_job_id=loser.job_id,
            deciding_factor="TECHNICIAN_SCARCITY",
            explanation=f"Job {winner.job_id} has higher technician scarcity ({winner.qualified_technicians_count} eligible in fleet: {winner.qualified_technician_ids}) compared to Job {loser.job_id} ({loser.qualified_technicians_count} eligible in fleet: {loser.qualified_technician_ids}). Scarcity prioritization prevents bottleneck technician exhaustion.",
            job_a_profile=prof_a,
            job_b_profile=prof_b,
        )

    # Tier 3: Time Window Tightness
    diff_tightness = abs(prof_a.window_duration_ratio - prof_b.window_duration_ratio)
    if diff_tightness >= 0.01:
        if prof_a.window_duration_ratio > prof_b.window_duration_ratio:
            winner, loser = prof_a, prof_b
        else:
            winner, loser = prof_b, prof_a
        return CompetingJobResolution(
            winner_job_id=winner.job_id,
            loser_job_id=loser.job_id,
            deciding_factor="WINDOW_TIGHTNESS",
            explanation=f"Job {winner.job_id} has tighter scheduling window constraints (tightness ratio {winner.window_duration_ratio}, {winner.window_slack_minutes}m slack) than Job {loser.job_id} (ratio {loser.window_duration_ratio}, {loser.window_slack_minutes}m slack).",
            job_a_profile=prof_a,
            job_b_profile=prof_b,
        )

    # Tier 4: Soft SLA Target Deadline
    if prof_a.sla_deadline != prof_b.sla_deadline:
        if prof_a.sla_deadline < prof_b.sla_deadline:
            winner, loser = prof_a, prof_b
        else:
            winner, loser = prof_b, prof_a
        return CompetingJobResolution(
            winner_job_id=winner.job_id,
            loser_job_id=loser.job_id,
            deciding_factor="SLA_DEADLINE",
            explanation=f"Job {winner.job_id} has earlier soft SLA deadline ({winner.sla_deadline.strftime('%H:%M')}) than Job {loser.job_id} ({loser.sla_deadline.strftime('%H:%M')}).",
            job_a_profile=prof_a,
            job_b_profile=prof_b,
        )

    # Tier 5: Hard Time Window End
    if prof_a.time_window_end != prof_b.time_window_end:
        if prof_a.time_window_end < prof_b.time_window_end:
            winner, loser = prof_a, prof_b
        else:
            winner, loser = prof_b, prof_a
        return CompetingJobResolution(
            winner_job_id=winner.job_id,
            loser_job_id=loser.job_id,
            deciding_factor="HARD_WINDOW_END",
            explanation=f"Job {winner.job_id} customer hard window closes earlier ({winner.time_window_end.strftime('%H:%M')}) than Job {loser.job_id} ({loser.time_window_end.strftime('%H:%M')}).",
            job_a_profile=prof_a,
            job_b_profile=prof_b,
        )

    # Tier 6: Time Window Start
    if prof_a.time_window_start != prof_b.time_window_start:
        if prof_a.time_window_start < prof_b.time_window_start:
            winner, loser = prof_a, prof_b
        else:
            winner, loser = prof_b, prof_a
        return CompetingJobResolution(
            winner_job_id=winner.job_id,
            loser_job_id=loser.job_id,
            deciding_factor="WINDOW_START",
            explanation=f"Job {winner.job_id} window opens earlier ({winner.time_window_start.strftime('%H:%M')}) than Job {loser.job_id} ({loser.time_window_start.strftime('%H:%M')}).",
            job_a_profile=prof_a,
            job_b_profile=prof_b,
        )

    # Tier 7: Strict Deterministic Tie-Breaker
    if prof_a.job_id < prof_b.job_id:
        winner, loser = prof_a, prof_b
    else:
        winner, loser = prof_b, prof_a

    return CompetingJobResolution(
        winner_job_id=winner.job_id,
        loser_job_id=loser.job_id,
        deciding_factor="DETERMINISTIC_ID",
        explanation=f"All operational priorities, scarcity metrics, and time constraints were identical. Decided by deterministic alphanumeric tie-breaker ({winner.job_id} < {loser.job_id}).",
        job_a_profile=prof_a,
        job_b_profile=prof_b,
    )


def compare_candidate_assignments(
    candidate_a: Dict[str, Any],
    candidate_b: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    Principled comparison between two candidate dispatch assignments for a job.
    Eliminates arbitrary selection:
    1. Lower objective ranking score wins.
    2. Earlier start time wins.
    3. Shorter travel duration wins.
    4. Deterministic technician ID ascending tie-breaker.
    """
    score_a = candidate_a.get("ranking_score", 9999.0)
    score_b = candidate_b.get("ranking_score", 9999.0)

    # 1. Ranking Score
    if abs(score_a - score_b) > 0.01:
        if score_a < score_b:
            return candidate_a, candidate_b, f"Candidate {candidate_a['technician'].id} has lower objective cost ({score_a:.2f} vs {score_b:.2f})"
        else:
            return candidate_b, candidate_a, f"Candidate {candidate_b['technician'].id} has lower objective cost ({score_b:.2f} vs {score_a:.2f})"

    # 2. Earlier Start Time
    start_a = candidate_a.get("proposed_start")
    start_b = candidate_b.get("proposed_start")
    if start_a and start_b and start_a != start_b:
        if start_a < start_b:
            return candidate_a, candidate_b, f"Candidate {candidate_a['technician'].id} offers earlier dispatch start ({start_a.strftime('%H:%M')})"
        else:
            return candidate_b, candidate_a, f"Candidate {candidate_b['technician'].id} offers earlier dispatch start ({start_b.strftime('%H:%M')})"

    # 3. Minimum Travel Time
    travel_a = candidate_a.get("travel_minutes", 0.0)
    travel_b = candidate_b.get("travel_minutes", 0.0)
    if abs(travel_a - travel_b) > 0.1:
        if travel_a < travel_b:
            return candidate_a, candidate_b, f"Candidate {candidate_a['technician'].id} requires less transit ({travel_a:.1f}m vs {travel_b:.1f}m)"
        else:
            return candidate_b, candidate_a, f"Candidate {candidate_b['technician'].id} requires less transit ({travel_b:.1f}m vs {travel_a:.1f}m)"

    # 4. Deterministic Technician ID
    tech_id_a = candidate_a["technician"].id
    tech_id_b = candidate_b["technician"].id
    if tech_id_a < tech_id_b:
        return candidate_a, candidate_b, f"Deterministic tie-breaker selected technician {tech_id_a} over {tech_id_b}"
    else:
        return candidate_b, candidate_a, f"Deterministic tie-breaker selected technician {tech_id_b} over {tech_id_a}"
