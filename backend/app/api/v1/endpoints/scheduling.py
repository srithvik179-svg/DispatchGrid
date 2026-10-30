from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import Job
from app.models.technician import Technician
from app.schemas.eligibility import (
    EligibilityCheckRequest,
    EligibilityCheckResponse,
)
from app.services.eligibility_service import validate_job_technician_eligibility

router = APIRouter()


@router.post(
    "/scheduling/validate-eligibility",
    response_model=EligibilityCheckResponse,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling & Validation"],
    summary="Validate job requirements against technician capabilities",
)
def check_eligibility(
    req: EligibilityCheckRequest,
    db: Session = Depends(get_db),
) -> EligibilityCheckResponse:
    """
    Validates all operational constraints (skills, equipment, zone, shift, unavailable intervals)
    for assigning a specific technician to a job. Returns structured validation results.
    """
    # 1. Resolve Job attributes
    job_skills = req.required_skills or []
    job_equipment = req.required_equipment or []
    job_zone = req.job_zone_id
    window_start = req.time_window_start
    window_end = req.time_window_end
    duration = req.duration_minutes

    if req.job_id:
        job = db.query(Job).filter_by(id=req.job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID '{req.job_id}' not found",
            )
        job_skills = job.required_skills or []
        job_equipment = job.required_equipment or []
        job_zone = job.zone_id
        window_start = job.time_window_start
        window_end = job.time_window_end
        duration = job.duration_minutes

    # 2. Resolve Technician attributes
    tech_skills = []
    tech_equipment = []
    tech_zones = []
    tech_home_zone = None
    tech_shifts = []
    tech_unavail = []
    tech_overtime = None

    if req.technician_id:
        tech = db.query(Technician).filter_by(id=req.technician_id).first()
        if not tech:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Technician with ID '{req.technician_id}' not found",
            )
        tech_skills = tech.skills or []
        tech_equipment = tech.equipment or []
        tech_zones = tech.eligible_zones or []
        tech_home_zone = tech.home_zone_id
        tech_shifts = tech.shifts or []
        tech_unavail = tech.unavailable_periods or []
        tech_overtime = tech.overtime

    # 3. Compute execution timestamps if not explicitly supplied
    prop_start = req.proposed_start or window_start
    prop_end = req.proposed_end
    if prop_start and not prop_end and duration:
        from datetime import timedelta
        prop_end = prop_start + timedelta(minutes=duration)

    return validate_job_technician_eligibility(
        job_skills=job_skills,
        job_equipment=job_equipment,
        job_zone_id=job_zone,
        technician_skills=tech_skills,
        technician_equipment=tech_equipment,
        technician_eligible_zones=tech_zones,
        technician_home_zone_id=tech_home_zone,
        proposed_start=prop_start,
        proposed_end=prop_end,
        technician_shifts=tech_shifts,
        technician_unavailable_periods=tech_unavail,
        technician_overtime=tech_overtime,
        job_time_window_start=window_start,
        job_time_window_end=window_end,
        job_duration_minutes=duration,
    )
