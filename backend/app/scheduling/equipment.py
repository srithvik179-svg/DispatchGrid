from typing import List, Dict, Any, Optional, Sequence, Union

from app.models.job import Job
from app.models.technician import Technician
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.schemas import (
    EquipmentMatchResult,
    QualificationMatchResult,
    CandidateTechnicianSummary,
    JobCandidateEvaluation,
)
from app.scheduling.skills import check_technician_skills

STANDARD_FLEET_EQUIPMENT = {
    "appliance_toolkit",
    "fiber_splicer",
    "hvac_gauge",
    "ladder",
    "multimeter",
    "pipe_wrench",
    "scissor_lift",
    "thermal_camera",
}


def normalize_equipment(item: str) -> str:
    """Normalize equipment name by trimming whitespace and converting to lowercase."""
    return item.strip().lower() if item else ""


def check_technician_equipment(
    required_equipment: Sequence[str],
    technician_equipment: Sequence[str],
    technician_id: str = "",
    technician_name: Optional[str] = None,
    fleet_equipment_inventory: Optional[Sequence[str]] = None,
) -> EquipmentMatchResult:
    """
    Evaluates whether an individual technician possesses every mandatory equipment item for a job.
    Accurately supports multi-equipment requirements, separates missing equipment,
    and identifies tools completely missing from the organization's fleet inventory.
    """
    req_norm = [normalize_equipment(e) for e in required_equipment if e and e.strip()]
    tech_norm = {normalize_equipment(e) for e in technician_equipment if e and e.strip()}

    fleet_inventory = {
        normalize_equipment(e)
        for e in (fleet_equipment_inventory if fleet_equipment_inventory is not None else STANDARD_FLEET_EQUIPMENT)
        if e and e.strip()
    }

    # 1. Check for equipment missing from the entire fleet inventory
    unsupported_found = [e for e in req_norm if e not in fleet_inventory]
    if unsupported_found:
        reason = (
            f"Job requires equipment: {', '.join(unsupported_found)}. "
            f"This equipment item is not supported in the organization's fleet inventory."
        )
        matched = [e for e in req_norm if e in tech_norm]
        missing = [e for e in req_norm if e not in tech_norm]
        return EquipmentMatchResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_eligible=False,
            matched_equipment=matched,
            missing_equipment=missing,
            has_unsupported_equipment=True,
            unsupported_equipment=unsupported_found,
            rejection_reason=reason,
        )

    # 2. Check for missing equipment items from technician onboard kit
    matched = [e for e in req_norm if e in tech_norm]
    missing = [e for e in req_norm if e not in tech_norm]

    tech_display = f"Technician {technician_name or technician_id}"
    kit_display = (
        f" (onboard kit: {', '.join(technician_equipment)})"
        if technician_equipment
        else " (onboard kit: none)"
    )

    if missing:
        reason = f"{tech_display} lacks required equipment: {', '.join(missing)}{kit_display}"
        return EquipmentMatchResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_eligible=False,
            matched_equipment=matched,
            missing_equipment=missing,
            has_unsupported_equipment=False,
            unsupported_equipment=[],
            rejection_reason=reason,
        )

    # 3. Fully equipped
    return EquipmentMatchResult(
        technician_id=technician_id,
        technician_name=technician_name,
        is_eligible=True,
        matched_equipment=matched,
        missing_equipment=[],
        has_unsupported_equipment=False,
        unsupported_equipment=[],
        rejection_reason=None,
    )


def check_technician_qualification(
    required_skills: Sequence[str],
    required_equipment: Sequence[str],
    technician_skills: Sequence[str],
    technician_equipment: Sequence[str],
    technician_id: str = "",
    technician_name: Optional[str] = None,
    unsupported_skills: Optional[Sequence[str]] = None,
    fleet_equipment_inventory: Optional[Sequence[str]] = None,
) -> QualificationMatchResult:
    """
    Combines skill proficiencies and equipment tooling requirements.
    Distinguishes skill deficiencies from equipment deficiencies clearly.
    """
    skill_res = check_technician_skills(
        required_skills=required_skills,
        technician_skills=technician_skills,
        technician_id=technician_id,
        technician_name=technician_name,
        unsupported_skills=unsupported_skills,
    )

    equip_res = check_technician_equipment(
        required_equipment=required_equipment,
        technician_equipment=technician_equipment,
        technician_id=technician_id,
        technician_name=technician_name,
        fleet_equipment_inventory=fleet_equipment_inventory,
    )

    is_eligible = skill_res.is_eligible and equip_res.is_eligible
    failure_cats: List[str] = []
    reasons: List[str] = []

    if not skill_res.is_eligible:
        failure_cats.append("skills")
        if skill_res.rejection_reason:
            reasons.append(skill_res.rejection_reason)

    if not equip_res.is_eligible:
        failure_cats.append("equipment")
        if equip_res.rejection_reason:
            reasons.append(equip_res.rejection_reason)

    combined_reason = " | ".join(reasons) if reasons else None

    return QualificationMatchResult(
        technician_id=technician_id,
        technician_name=technician_name,
        is_eligible=is_eligible,
        skill_eligible=skill_res.is_eligible,
        equipment_eligible=equip_res.is_eligible,
        skill_match=skill_res,
        equipment_match=equip_res,
        missing_skills=skill_res.missing_skills,
        missing_equipment=equip_res.missing_equipment,
        failure_categories=failure_cats,
        combined_rejection_reason=combined_reason,
    )


def filter_candidates_for_job(
    job: Union[Job, JobResponse, Dict[str, Any]],
    technicians: Sequence[Union[Technician, TechnicianResponse, Dict[str, Any]]],
    unsupported_skills: Optional[Sequence[str]] = None,
    fleet_equipment_inventory: Optional[Sequence[str]] = None,
) -> JobCandidateEvaluation:
    """
    Filters technician candidates for a job enforcing BOTH mandatory skills and mandatory equipment.
    Tracks candidates that match skills but fail equipment tooling.
    """
    if isinstance(job, dict):
        job_id = job.get("id", "")
        job_title = job.get("title")
        required_skills = job.get("required_skills", [])
        required_equipment = job.get("required_equipment", [])
    else:
        job_id = getattr(job, "id", "")
        job_title = getattr(job, "title", None)
        required_skills = getattr(job, "required_skills", []) or []
        required_equipment = getattr(job, "required_equipment", []) or []

    eligible_candidates: List[CandidateTechnicianSummary] = []
    rejected_candidates: List[QualificationMatchResult] = []
    skill_only_matching: List[str] = []
    rejection_summary: Dict[str, str] = {}
    unsupported_reqs: List[str] = []

    for tech in technicians:
        if isinstance(tech, dict):
            t_id = tech.get("id", "")
            t_name = tech.get("name", t_id)
            t_skills = tech.get("skills", [])
            t_equip = tech.get("equipment", [])
            t_zones = tech.get("eligible_zones", [])
            t_home = tech.get("home_zone_id")
        else:
            t_id = getattr(tech, "id", "")
            t_name = getattr(tech, "name", t_id)
            t_skills = getattr(tech, "skills", []) or []
            t_equip = getattr(tech, "equipment", []) or []
            t_zones = getattr(tech, "eligible_zones", []) or []
            t_home = getattr(tech, "home_zone_id", None)

        qual = check_technician_qualification(
            required_skills=required_skills,
            required_equipment=required_equipment,
            technician_skills=t_skills,
            technician_equipment=t_equip,
            technician_id=t_id,
            technician_name=t_name,
            unsupported_skills=unsupported_skills,
            fleet_equipment_inventory=fleet_equipment_inventory,
        )

        if qual.skill_match.has_unsupported_skills:
            for s in qual.skill_match.unsupported_skills:
                if s not in unsupported_reqs:
                    unsupported_reqs.append(s)

        if qual.equipment_match.has_unsupported_equipment:
            for e in qual.equipment_match.unsupported_equipment:
                if e not in unsupported_reqs:
                    unsupported_reqs.append(e)

        if qual.is_eligible:
            eligible_candidates.append(
                CandidateTechnicianSummary(
                    id=t_id,
                    name=t_name,
                    skills=list(t_skills),
                    equipment=list(t_equip),
                    eligible_zones=list(t_zones),
                    home_zone_id=t_home,
                )
            )
        else:
            rejected_candidates.append(qual)
            if qual.combined_rejection_reason:
                rejection_summary[t_id] = qual.combined_rejection_reason

            # Track candidates who passed skills but failed equipment
            if qual.skill_eligible and not qual.equipment_eligible:
                skill_only_matching.append(t_id)

    candidate_count = len(eligible_candidates)
    has_unsupported = bool(unsupported_reqs)
    is_assignable = (candidate_count > 0 and not has_unsupported)

    reason_if_unassignable: Optional[str] = None
    if not is_assignable:
        if has_unsupported:
            reason_if_unassignable = (
                f"Job requires unsupported requirement(s): {', '.join(unsupported_reqs)}. "
                f"Fleet capability does not support these operational requirements."
            )
        elif skill_only_matching and candidate_count == 0:
            reason_if_unassignable = (
                f"{len(skill_only_matching)} technician(s) match required skills ({', '.join(required_skills)}), "
                f"but lack mandatory equipment ({', '.join(required_equipment)})."
            )
        else:
            reason_if_unassignable = (
                f"No technicians in fleet satisfy combined skill ({', '.join(required_skills)}) "
                f"and equipment ({', '.join(required_equipment)}) requirements."
            )

    return JobCandidateEvaluation(
        job_id=job_id,
        job_title=job_title,
        required_skills=list(required_skills),
        required_equipment=list(required_equipment),
        has_unsupported_requirements=has_unsupported,
        unsupported_requirements=unsupported_reqs,
        candidate_count=candidate_count,
        is_assignable=is_assignable,
        eligible_candidates=eligible_candidates,
        rejected_candidates=rejected_candidates,
        skill_only_matching_candidates=skill_only_matching,
        rejection_summary=rejection_summary,
        reason_if_unassignable=reason_if_unassignable,
    )


def filter_all_jobs_candidates(
    jobs: Sequence[Union[Job, JobResponse, Dict[str, Any]]],
    technicians: Sequence[Union[Technician, TechnicianResponse, Dict[str, Any]]],
    unsupported_skills: Optional[Sequence[str]] = None,
    fleet_equipment_inventory: Optional[Sequence[str]] = None,
) -> Dict[str, JobCandidateEvaluation]:
    """
    Evaluates candidate compatibility combining skills and equipment across all jobs.
    Returns mapping of job_id -> JobCandidateEvaluation.
    """
    results: Dict[str, JobCandidateEvaluation] = {}
    for job in jobs:
        eval_res = filter_candidates_for_job(
            job=job,
            technicians=technicians,
            unsupported_skills=unsupported_skills,
            fleet_equipment_inventory=fleet_equipment_inventory,
        )
        results[eval_res.job_id] = eval_res
    return results
