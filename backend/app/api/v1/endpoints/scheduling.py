from typing import Optional
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
from app.scheduling.schemas import (
    SchedulingRunConfig,
    SchedulingInput,
    SchedulingResult,
    SimulationClockResponse,
)
from app.scheduling.service import SchedulingService

router = APIRouter()


@router.get(
    "/scheduling/clock",
    response_model=SimulationClockResponse,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Get simulation reference clock and planning horizon",
)
def get_clock(db: Session = Depends(get_db)) -> SimulationClockResponse:
    """
    Returns the authoritative simulation reference clock ('as_of') and the active planning horizon.
    """
    service = SchedulingService(db)
    as_of = service.get_clock()
    h_start, h_end = service.get_horizon()
    return SimulationClockResponse(
        as_of=as_of,
        horizon_start=h_start,
        horizon_end=h_end,
        time_zone="Asia/Kolkata (+05:30)",
    )


@router.get(
    "/scheduling/inputs",
    response_model=SchedulingInput,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Load and inspect current scheduling input data",
)
def get_scheduling_inputs(
    db: Session = Depends(get_db),
) -> SchedulingInput:
    """
    Loads all pending jobs, available technicians, and existing protected assignments
    from the database without modifying any state.
    """
    service = SchedulingService(db)
    return service.load_inputs()


@router.post(
    "/scheduling/runs/init",
    response_model=SchedulingResult,
    status_code=status.HTTP_201_CREATED,
    tags=["Scheduling Engine"],
    summary="Initialize a scheduling run session",
)
def initialize_scheduling_run(
    config: Optional[SchedulingRunConfig] = None,
    db: Session = Depends(get_db),
) -> SchedulingResult:
    """
    Initializes a new scheduling run session, generates a unique run ID, loads inputs,
    and locks in pre-existing assignments without altering any database records.
    """
    service = SchedulingService(db)
    return service.initialize_run(config=config)


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
