from typing import List, Dict, Any, Optional, Sequence, Union

from app.models.job import Job
from app.models.technician import Technician
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.schemas import (
    SkillMatchResult,
    CandidateTechnicianSummary,
    JobSkillCandidates,
)

DEFAULT_UNSUPPORTED_SKILLS = {"high_voltage"}


def normalize_skill(skill: str) -> str:
    """Normalize skill string by trimming whitespace and converting to lowercase."""
    return skill.strip().lower() if skill else ""


def check_technician_skills(
    required_skills: Sequence[str],
    technician_skills: Sequence[str],
    technician_id: str = "",
    technician_name: Optional[str] = None,
    unsupported_skills: Optional[Sequence[str]] = None,
) -> SkillMatchResult:
    """
    Evaluates whether an individual technician possesses every mandatory skill required for a job.
    Accurately supports multi-skill jobs, identifies missing skills, and detects unsupported skills.
    """
    req_norm = [normalize_skill(s) for s in required_skills if s and s.strip()]
    tech_norm = {normalize_skill(s) for s in technician_skills if s and s.strip()}

    unsupported_set = {
        normalize_skill(s) for s in (unsupported_skills if unsupported_skills is not None else DEFAULT_UNSUPPORTED_SKILLS)
        if s and s.strip()
    }

    # 1. Check for unsupported skills
    unsupported_found = [s for s in req_norm if s in unsupported_set]
    if unsupported_found:
        reason = (
            f"Job requires unsupported skill(s): {', '.join(unsupported_found)}. "
            f"Technician fleet does not support this specialized certification."
        )
        matched = [s for s in req_norm if s in tech_norm]
        missing = [s for s in req_norm if s not in tech_norm]
        return SkillMatchResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_eligible=False,
            matched_skills=matched,
            missing_skills=missing,
            has_unsupported_skills=True,
            unsupported_skills=unsupported_found,
            rejection_reason=reason,
        )

    # 2. Check for missing skills
    matched = [s for s in req_norm if s in tech_norm]
    missing = [s for s in req_norm if s not in tech_norm]

    tech_display = f"Technician {technician_name or technician_id}"
    holds_display = (
        f" (holds: {', '.join(technician_skills)})"
        if technician_skills
        else " (holds no certified skills)"
    )

    if missing:
        reason = f"{tech_display} lacks required skill(s): {', '.join(missing)}{holds_display}"
        return SkillMatchResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_eligible=False,
            matched_skills=matched,
            missing_skills=missing,
            has_unsupported_skills=False,
            unsupported_skills=[],
            rejection_reason=reason,
        )

    # 3. Fully qualified
    return SkillMatchResult(
        technician_id=technician_id,
        technician_name=technician_name,
        is_eligible=True,
        matched_skills=matched,
        missing_skills=[],
        has_unsupported_skills=False,
        unsupported_skills=[],
        rejection_reason=None,
    )


def filter_technicians_by_skills(
    job: Union[Job, JobResponse, Dict[str, Any]],
    technicians: Sequence[Union[Technician, TechnicianResponse, Dict[str, Any]]],
    unsupported_skills: Optional[Sequence[str]] = None,
) -> JobSkillCandidates:
    """
    Filters the entire technician pool for a given job based strictly on skill proficiencies.
    Separates eligible candidate technicians from rejected ones with precise failure explanations.
    """
    # Extract job properties
    if isinstance(job, dict):
        job_id = job.get("id", "")
        job_title = job.get("title")
        required_skills = job.get("required_skills", [])
    else:
        job_id = getattr(job, "id", "")
        job_title = getattr(job, "title", None)
        required_skills = getattr(job, "required_skills", []) or []

    req_norm = [normalize_skill(s) for s in required_skills if s and s.strip()]
    unsupported_set = {
        normalize_skill(s) for s in (unsupported_skills if unsupported_skills is not None else DEFAULT_UNSUPPORTED_SKILLS)
        if s and s.strip()
    }
    unsupported_in_job = [s for s in req_norm if s in unsupported_set]
    has_unsupported = bool(unsupported_in_job)

    eligible_candidates: List[CandidateTechnicianSummary] = []
    rejected_candidates: List[SkillMatchResult] = []
    rejection_summary: Dict[str, str] = {}

    for tech in technicians:
        if isinstance(tech, dict):
            t_id = tech.get("id", "")
            t_name = tech.get("name", t_id)
            t_skills = tech.get("skills", [])
            t_zones = tech.get("eligible_zones", [])
            t_home = tech.get("home_zone_id")
        else:
            t_id = getattr(tech, "id", "")
            t_name = getattr(tech, "name", t_id)
            t_skills = getattr(tech, "skills", []) or []
            t_zones = getattr(tech, "eligible_zones", []) or []
            t_home = getattr(tech, "home_zone_id", None)

        match_res = check_technician_skills(
            required_skills=required_skills,
            technician_skills=t_skills,
            technician_id=t_id,
            technician_name=t_name,
            unsupported_skills=unsupported_skills,
        )

        if match_res.is_eligible:
            eligible_candidates.append(
                CandidateTechnicianSummary(
                    id=t_id,
                    name=t_name,
                    skills=list(t_skills),
                    eligible_zones=list(t_zones),
                    home_zone_id=t_home,
                )
            )
        else:
            rejected_candidates.append(match_res)
            if match_res.rejection_reason:
                rejection_summary[t_id] = match_res.rejection_reason

    candidate_count = len(eligible_candidates)
    is_assignable = (candidate_count > 0 and not has_unsupported)

    reason_if_unassignable: Optional[str] = None
    if not is_assignable:
        if has_unsupported:
            reason_if_unassignable = (
                f"Job requires unsupported skill(s): {', '.join(unsupported_in_job)}. "
                f"No technicians in the fleet are certified for this specialized skill."
            )
        else:
            reason_if_unassignable = (
                f"Zero technicians possess all {len(req_norm)} required skills: {', '.join(req_norm)}. "
                f"Evaluated {len(technicians)} technicians across the fleet."
            )

    return JobSkillCandidates(
        job_id=job_id,
        job_title=job_title,
        required_skills=list(required_skills),
        has_unsupported_skills=has_unsupported,
        unsupported_skills=unsupported_in_job,
        candidate_count=candidate_count,
        is_assignable=is_assignable,
        eligible_candidates=eligible_candidates,
        rejected_candidates=rejected_candidates,
        rejection_summary=rejection_summary,
        reason_if_unassignable=reason_if_unassignable,
    )


def filter_all_jobs_by_skills(
    jobs: Sequence[Union[Job, JobResponse, Dict[str, Any]]],
    technicians: Sequence[Union[Technician, TechnicianResponse, Dict[str, Any]]],
    unsupported_skills: Optional[Sequence[str]] = None,
) -> Dict[str, JobSkillCandidates]:
    """
    Evaluates candidate technician eligibility across an entire batch of jobs.
    Returns a dictionary mapping job_id -> JobSkillCandidates.
    """
    results: Dict[str, JobSkillCandidates] = {}
    for job in jobs:
        cand = filter_technicians_by_skills(
            job=job,
            technicians=technicians,
            unsupported_skills=unsupported_skills,
        )
        results[cand.job_id] = cand
    return results
