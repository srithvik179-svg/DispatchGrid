"""
Scheduling feasibility classification and diagnostic explanation engine.

Categorizes jobs into three unambiguous operational tiers:
1. FEASIBLE:
   - The job can be scheduled without violating any hard constraints.
   - Soft SLA deadline delays are explicitly distinguished from hard failures.
2. CURRENTLY_INFEASIBLE:
   - The fleet possesses the necessary skills, equipment, and zone eligibility,
     but scheduling fails due to temporary operational capacity constraints:
       - Shift capacity exhausted / outside working shift hours
       - Travel-time reachability / buffer deficit from prior assignments
       - Schedule congestion / double-booking collisions with existing jobs
       - Hard customer time window expired or too tight relative to current itinerary
   - Actionable recommendations provide capacity adjustment strategies.
3. PERMANENTLY_IMPOSSIBLE:
   - Structural impossibility that cannot be resolved by calendar shifting:
       - Unsupported skills (e.g. high_voltage on JOB-014)
       - Missing skill combinations (e.g. elevator + electrical + hvac on JOB-057)
       - Unavailable fleet equipment (e.g. crane on JOB-013)
       - Uncovered operational zones (e.g. Zone Z6 on JOB-017)
       - Invalid job duration exceeding time window capacity
   - Actionable recommendations detail procurement, certification, or contractor dispatch.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Dict, Any, List, Tuple

from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.schemas.assignment import AssignmentSummary
from app.scheduling.schemas import (
    JobFeasibilityReport,
    TechnicianRejectionDetail,
    FleetFeasibilitySummary,
)
from app.scheduling.skills import check_technician_skills, DEFAULT_UNSUPPORTED_SKILLS
from app.scheduling.equipment import check_technician_equipment, STANDARD_FLEET_EQUIPMENT
from app.scheduling.geo import check_zone_eligibility, haversine_distance, calculate_travel_minutes
from app.scheduling.availability import parse_datetime_safe
from app.scheduling.time_windows import validate_job_time_window
from app.scheduling.conflicts import detect_scheduling_conflicts
from app.scheduling.algorithm import find_feasible_slots_for_technician


def classify_job_feasibility(
    job: JobResponse,
    technicians: Sequence[TechnicianResponse],
    technician_itineraries: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    as_of: Optional[datetime] = None,
    unsupported_skills: Sequence[str] = DEFAULT_UNSUPPORTED_SKILLS,
    fleet_equipment: Optional[Sequence[str]] = None,
) -> JobFeasibilityReport:
    """
    Rigorously classifies scheduling feasibility for an individual service job,
    producing actionable diagnostic explanations.
    """
    clock = parse_datetime_safe(as_of) or datetime.now(timezone.utc)
    itineraries = technician_itineraries or {t.id: [] for t in technicians}
    norm_unsupported = {s.strip().lower() for s in unsupported_skills}
    fleet_inventory = set(fleet_equipment) if fleet_equipment else STANDARD_FLEET_EQUIPMENT

    job_skills = [s.strip().lower() for s in (job.required_skills or []) if s.strip()]
    job_equip = [e.strip().lower() for e in (job.required_equipment or []) if e.strip()]

    technician_rejections: List[TechnicianRejectionDetail] = []

    # -------------------------------------------------------------
    # 1. Structural Checks: Job Specification Integrity
    # -------------------------------------------------------------
    window_duration_mins = (job.time_window_end - job.time_window_start).total_seconds() / 60.0
    if window_duration_mins < job.duration_minutes:
        return JobFeasibilityReport(
            job_id=job.id,
            classification="permanently_impossible",
            primary_category="time_window",
            is_structurally_feasible=False,
            qualified_technician_count=0,
            qualified_technician_ids=[],
            rejection_summary=(
                f"Job specification error: service duration ({job.duration_minutes} mins) exceeds "
                f"the hard customer time window ({window_duration_mins:.0f} mins)."
            ),
            actionable_recommendation="Adjust customer time window or correct service duration estimate.",
            technician_rejections=[],
        )

    # -------------------------------------------------------------
    # 2. Structural Checks: Unsupported Skills
    # -------------------------------------------------------------
    unsupported_found = [s for s in job_skills if s in norm_unsupported]
    if unsupported_found:
        rejection_summary = (
            f"Job requires unsupported specialized skill(s): {', '.join(unsupported_found)}. "
            f"The field technician fleet is not certified or authorized for this specialized work."
        )
        actionable_recommendation = (
            "Dispatch an accredited external high-voltage contractor or sponsor specialized certification."
        )

        for tech in technicians:
            technician_rejections.append(
                TechnicianRejectionDetail(
                    technician_id=tech.id,
                    technician_name=tech.name,
                    is_structurally_capable=False,
                    rejection_category="skills",
                    rejection_code="UNSUPPORTED_SKILLS",
                    missing_skills=unsupported_found,
                    missing_equipment=[],
                    zone_certified=True,
                    explanation=f"Technician {tech.name} does not hold unsupported skill '{', '.join(unsupported_found)}'.",
                )
            )

        return JobFeasibilityReport(
            job_id=job.id,
            classification="permanently_impossible",
            primary_category="unsupported_skill",
            is_structurally_feasible=False,
            qualified_technician_count=0,
            qualified_technician_ids=[],
            rejection_summary=rejection_summary,
            actionable_recommendation=actionable_recommendation,
            technician_rejections=technician_rejections,
        )

    # -------------------------------------------------------------
    # 3. Structural Checks: Zone Coverage across Fleet
    # -------------------------------------------------------------
    zone_certified_techs = [
        t.id for t in technicians
        if check_zone_eligibility(job.zone_id, t.eligible_zones or [], t.home_zone_id, t.id).is_eligible
    ]

    if not zone_certified_techs:
        rejection_summary = (
            f"Job is located in Zone '{job.zone_id}', but zero technicians in the entire fleet "
            f"are certified or assigned to operate in Zone '{job.zone_id}'."
        )
        actionable_recommendation = (
            f"Assign or cross-certify at least one field technician for operational Zone '{job.zone_id}'."
        )

        for tech in technicians:
            technician_rejections.append(
                TechnicianRejectionDetail(
                    technician_id=tech.id,
                    technician_name=tech.name,
                    is_structurally_capable=False,
                    rejection_category="zone",
                    rejection_code="ZONE_INELIGIBLE",
                    missing_skills=[],
                    missing_equipment=[],
                    zone_certified=False,
                    explanation=f"Technician {tech.name} operational territory {tech.eligible_zones} excludes Zone '{job.zone_id}'.",
                )
            )

        return JobFeasibilityReport(
            job_id=job.id,
            classification="permanently_impossible",
            primary_category="uncovered_zone",
            is_structurally_feasible=False,
            qualified_technician_count=0,
            qualified_technician_ids=[],
            rejection_summary=rejection_summary,
            actionable_recommendation=actionable_recommendation,
            technician_rejections=technician_rejections,
        )

    # -------------------------------------------------------------
    # 4. Structural Checks: Tooling / Equipment across Fleet
    # -------------------------------------------------------------
    missing_fleet_equip = [e for e in job_equip if e not in fleet_inventory]
    if missing_fleet_equip:
        rejection_summary = (
            f"Job requires specialized equipment {missing_fleet_equip}, which is not provisioned "
            f"in any vehicle kit in the technician fleet."
        )
        actionable_recommendation = (
            f"Procure required tooling item(s): {', '.join(missing_fleet_equip)}."
        )

        for tech in technicians:
            technician_rejections.append(
                TechnicianRejectionDetail(
                    technician_id=tech.id,
                    technician_name=tech.name,
                    is_structurally_capable=False,
                    rejection_category="equipment",
                    rejection_code="MISSING_EQUIPMENT",
                    missing_skills=[],
                    missing_equipment=missing_fleet_equip,
                    zone_certified=True,
                    explanation=f"Technician {tech.name} lacks unprovisioned fleet equipment: {', '.join(missing_fleet_equip)}.",
                )
            )

        return JobFeasibilityReport(
            job_id=job.id,
            classification="permanently_impossible",
            primary_category="missing_equipment",
            is_structurally_feasible=False,
            qualified_technician_count=0,
            qualified_technician_ids=[],
            rejection_summary=rejection_summary,
            actionable_recommendation=actionable_recommendation,
            technician_rejections=technician_rejections,
        )

    # -------------------------------------------------------------
    # 5. Evaluate Individual Technician Qualifications
    # -------------------------------------------------------------
    structurally_qualified_techs: List[TechnicianResponse] = []
    technician_slots_map: Dict[str, List[Dict[str, Any]]] = {}

    for tech in technicians:
        # Check skill
        s_res = check_technician_skills(job_skills, tech.skills or [], tech.id, unsupported_skills=unsupported_skills)
        # Check equipment
        e_res = check_technician_equipment(job_equip, tech.equipment or [], tech.id)
        # Check zone
        z_res = check_zone_eligibility(job.zone_id, tech.eligible_zones or [], tech.home_zone_id, tech.id)

        is_structurally_capable = s_res.is_eligible and e_res.is_eligible and z_res.is_eligible

        if not is_structurally_capable:
            cat = "skills" if not s_res.is_eligible else ("equipment" if not e_res.is_eligible else "zone")
            code = "MISSING_SKILLS" if not s_res.is_eligible else ("MISSING_EQUIPMENT" if not e_res.is_eligible else "ZONE_INELIGIBLE")
            expl = s_res.rejection_reason or e_res.rejection_reason or z_res.rejection_reason or "Ineligible"

            technician_rejections.append(
                TechnicianRejectionDetail(
                    technician_id=tech.id,
                    technician_name=tech.name,
                    is_structurally_capable=False,
                    rejection_category=cat,
                    rejection_code=code,
                    missing_skills=s_res.missing_skills,
                    missing_equipment=e_res.missing_equipment,
                    zone_certified=z_res.is_eligible,
                    explanation=expl,
                )
            )
            continue

        structurally_qualified_techs.append(tech)

        # Check temporal slots in current schedule
        itinerary = itineraries.get(tech.id, [])
        slots = find_feasible_slots_for_technician(
            job=job,
            technician=tech,
            itinerary=itinerary,
            as_of=clock,
        )
        technician_slots_map[tech.id] = slots

        if not slots:
            technician_rejections.append(
                TechnicianRejectionDetail(
                    technician_id=tech.id,
                    technician_name=tech.name,
                    is_structurally_capable=True,
                    rejection_category="shift",
                    rejection_code="SCHEDULE_CAPACITY_EXHAUSTED",
                    missing_skills=[],
                    missing_equipment=[],
                    zone_certified=True,
                    explanation=(
                        f"Technician {tech.name} possesses certified skills, tools, and zone, but has "
                        f"no feasible working shift slot fitting job time window [{job.time_window_start.strftime('%H:%M')} - {job.time_window_end.strftime('%H:%M')}]."
                    ),
                )
            )

    # -------------------------------------------------------------
    # 6. Synthesize Final Classification
    # -------------------------------------------------------------
    qualified_count = len(structurally_qualified_techs)
    qualified_ids = [t.id for t in structurally_qualified_techs]

    # Case A: Zero technicians in the fleet hold the required skill combination
    if qualified_count == 0:
        return JobFeasibilityReport(
            job_id=job.id,
            classification="permanently_impossible",
            primary_category="missing_skill",
            is_structurally_feasible=False,
            qualified_technician_count=0,
            qualified_technician_ids=[],
            rejection_summary=(
                f"No technician in the fleet possesses the complete certified skill bundle "
                f"({job.required_skills}) for operational Zone '{job.zone_id}'."
            ),
            actionable_recommendation="Cross-train a certified technician in this combination or split into multiple dispatches.",
            technician_rejections=technician_rejections,
        )

    # Case B: At least one qualified technician has a feasible slot -> FEASIBLE
    all_feasible_slots = [
        slot for slots in technician_slots_map.values() for slot in slots
    ]

    if all_feasible_slots:
        # Find best slot (e.g. earliest start / lowest lateness)
        all_feasible_slots.sort(key=lambda x: (x["is_sla_violated"], x["sla_lateness_minutes"], x["proposed_start"]))
        best_slot = all_feasible_slots[0]
        best_tech = best_slot["technician"]
        is_sla_delayed = best_slot["is_sla_violated"]
        sla_lateness = best_slot["sla_lateness_minutes"]

        if is_sla_delayed:
            summary = (
                f"Job is feasible to assign to technician {best_tech.name} ({best_tech.id}) "
                f"at {best_slot['proposed_start'].strftime('%Y-%m-%d %H:%M')}. "
                f"Soft SLA deadline is missed by {sla_lateness} mins (does not cause hard rejection)."
            )
        else:
            summary = (
                f"Job is fully feasible to assign to technician {best_tech.name} ({best_tech.id}) "
                f"on-time at {best_slot['proposed_start'].strftime('%Y-%m-%d %H:%M')}."
            )

        return JobFeasibilityReport(
            job_id=job.id,
            classification="feasible",
            primary_category="none",
            is_structurally_feasible=True,
            qualified_technician_count=qualified_count,
            qualified_technician_ids=qualified_ids,
            is_sla_delayed=is_sla_delayed,
            sla_lateness_minutes=sla_lateness,
            rejection_summary=summary,
            actionable_recommendation="Schedule job with eligible technician candidate.",
            technician_rejections=technician_rejections,
        )

    # Case C: Structurally feasible, but no available slot in current schedule -> CURRENTLY_INFEASIBLE
    rejection_summary = (
        f"Job is structurally feasible ({qualified_count} technician(s) qualified: {', '.join(qualified_ids)}), "
        f"but currently unschedulable due to shift boundaries, travel buffers, or schedule congestion in the active horizon."
    )
    actionable_recommendation = (
        "Authorize technician overtime, expand working shift hours, or widen customer time window."
    )

    return JobFeasibilityReport(
        job_id=job.id,
        classification="currently_infeasible",
        primary_category="shift_hours",
        is_structurally_feasible=True,
        qualified_technician_count=qualified_count,
        qualified_technician_ids=qualified_ids,
        is_sla_delayed=False,
        sla_lateness_minutes=0,
        rejection_summary=rejection_summary,
        actionable_recommendation=actionable_recommendation,
        technician_rejections=technician_rejections,
    )


def classify_fleet_feasibility(
    jobs: Sequence[JobResponse],
    technicians: Sequence[TechnicianResponse],
    technician_itineraries: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    as_of: Optional[datetime] = None,
    unsupported_skills: Sequence[str] = DEFAULT_UNSUPPORTED_SKILLS,
    fleet_equipment: Optional[Sequence[str]] = None,
    run_id: Optional[str] = None,
) -> FleetFeasibilitySummary:
    """
    Evaluates and aggregates feasibility classifications for every job in the fleet.
    """
    clock = parse_datetime_safe(as_of) or datetime.now(timezone.utc)
    reports: Dict[str, JobFeasibilityReport] = {}

    feasible_count = 0
    currently_infeasible_count = 0
    permanently_impossible_count = 0

    for job in jobs:
        rep = classify_job_feasibility(
            job=job,
            technicians=technicians,
            technician_itineraries=technician_itineraries,
            as_of=clock,
            unsupported_skills=unsupported_skills,
            fleet_equipment=fleet_equipment,
        )
        reports[job.id] = rep
        if rep.classification == "feasible":
            feasible_count += 1
        elif rep.classification == "currently_infeasible":
            currently_infeasible_count += 1
        elif rep.classification == "permanently_impossible":
            permanently_impossible_count += 1

    return FleetFeasibilitySummary(
        run_id=run_id,
        as_of=clock,
        total_jobs=len(jobs),
        feasible_count=feasible_count,
        currently_infeasible_count=currently_infeasible_count,
        permanently_impossible_count=permanently_impossible_count,
        job_reports=reports,
    )
