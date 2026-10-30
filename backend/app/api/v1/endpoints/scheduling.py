from typing import Optional, Union, Dict
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
    JobSkillCandidates,
    SkillFilterRequest,
    JobCandidateEvaluation,
    CombinedQualificationRequest,
    TravelEstimate,
    ZoneMatchResult,
    GeoEligibilityResult,
    TravelCalculationRequest,
    TravelCalculationResponse,
)
from app.scheduling.service import SchedulingService
from app.scheduling.loader import load_eligible_technicians
from app.scheduling.skills import filter_technicians_by_skills
from app.scheduling.equipment import filter_candidates_for_job
from app.scheduling.geo import haversine_distance, calculate_travel_minutes



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


@router.get(
    "/scheduling/candidates/skills",
    response_model=Union[JobSkillCandidates, Dict[str, JobSkillCandidates]],
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Get candidate technicians filtered by job required skills",
)
def get_skill_candidates(
    job_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns candidate technicians strictly filtered by required skill matching.
    If job_id is specified, returns the analysis for that job.
    Otherwise, returns a map of all pending jobs to their skill candidate analysis.
    """
    service = SchedulingService(db)
    if job_id:
        try:
            return service.get_candidates_by_skill(job_id)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return service.get_all_skill_candidates()


@router.post(
    "/scheduling/candidates/skills/filter",
    response_model=JobSkillCandidates,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Evaluate technician skill compatibility against job or custom skills",
)
def filter_by_skills(
    req: SkillFilterRequest,
    db: Session = Depends(get_db),
) -> JobSkillCandidates:
    """
    Evaluates candidate technicians against specified skills or an existing job ID.
    """
    service = SchedulingService(db)
    req_skills = req.required_skills or []
    target_job_id = req.job_id or "CUSTOM-SKILL-QUERY"
    target_job_title = "Custom skill evaluation"

    if req.job_id:
        job = db.query(Job).filter_by(id=req.job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID '{req.job_id}' not found",
            )
        target_job_title = job.title
        if not req.required_skills:
            req_skills = job.required_skills or []

    all_techs = load_eligible_technicians(db)
    if req.technician_ids:
        tech_id_set = set(req.technician_ids)
        all_techs = [t for t in all_techs if t.id in tech_id_set]

    unsupported = service.get_unsupported_skills()
    fake_job = {
        "id": target_job_id,
        "title": target_job_title,
        "required_skills": req_skills,
    }
    return filter_technicians_by_skills(
        job=fake_job,
        technicians=all_techs,
        unsupported_skills=unsupported,
    )


@router.get(
    "/scheduling/candidates",
    response_model=Union[JobCandidateEvaluation, Dict[str, JobCandidateEvaluation]],
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Get candidate technicians filtered by both mandatory skills and equipment",
)
def get_job_candidates(
    job_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns candidate technicians strictly filtered by both required skills and equipment.
    Distinguishes skill deficiencies from equipment deficiencies.
    """
    service = SchedulingService(db)
    if job_id:
        try:
            return service.get_candidates_for_job(job_id)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return service.get_all_job_candidates()


@router.post(
    "/scheduling/candidates/filter",
    response_model=JobCandidateEvaluation,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Evaluate technician skill and equipment compatibility against job or custom criteria",
)
def filter_by_qualifications(
    req: CombinedQualificationRequest,
    db: Session = Depends(get_db),
) -> JobCandidateEvaluation:
    """
    Evaluates candidate technicians against specified skills and equipment criteria.
    """
    service = SchedulingService(db)
    req_skills = req.required_skills or []
    req_equipment = req.required_equipment or []
    target_job_id = req.job_id or "CUSTOM-QUAL-QUERY"
    target_job_title = "Custom qualification evaluation"

    if req.job_id:
        job = db.query(Job).filter_by(id=req.job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID '{req.job_id}' not found",
            )
        target_job_title = job.title
        if not req.required_skills:
            req_skills = job.required_skills or []
        if not req.required_equipment:
            req_equipment = job.required_equipment or []

    all_techs = load_eligible_technicians(db)
    if req.technician_ids:
        tech_id_set = set(req.technician_ids)
        all_techs = [t for t in all_techs if t.id in tech_id_set]

    unsupported_skills = service.get_unsupported_skills()
    fleet_equipment = service.get_fleet_equipment()

    fake_job = {
        "id": target_job_id,
        "title": target_job_title,
        "required_skills": req_skills,
        "required_equipment": req_equipment,
    }
    return filter_candidates_for_job(
        job=fake_job,
        technicians=all_techs,
        unsupported_skills=unsupported_skills,
        fleet_equipment_inventory=fleet_equipment,
    )


@router.post(
    "/scheduling/travel/estimate",
    response_model=TravelCalculationResponse,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Calculate Haversine distance and transit duration between coordinates",
)
def estimate_travel(req: TravelCalculationRequest) -> TravelCalculationResponse:
    """
    Computes deterministic great-circle Haversine distance and transit travel duration
    based on the supplied coordinates and travel speed (default 30 km/h).
    """
    try:
        dist_km = haversine_distance(req.origin_lat, req.origin_lng, req.destination_lat, req.destination_lng)
        travel_mins = calculate_travel_minutes(dist_km, speed_kmh=req.speed_kmh or 30.0)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return TravelCalculationResponse(
        distance_km=dist_km,
        travel_minutes=travel_mins,
        speed_kmh=req.speed_kmh or 30.0,
        origin_lat=req.origin_lat,
        origin_lng=req.origin_lng,
        destination_lat=req.destination_lat,
        destination_lng=req.destination_lng,
    )


@router.get(
    "/scheduling/travel/home-to-job",
    response_model=TravelEstimate,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Calculate first-job transit travel from technician home location",
)
def get_home_to_job_travel(
    technician_id: str,
    job_id: str,
    speed_kmh: Optional[float] = None,
    db: Session = Depends(get_db),
) -> TravelEstimate:
    """
    Calculates deterministic transit distance and estimated minutes from technician home to job.
    """
    service = SchedulingService(db)
    try:
        estimate = service.calculate_home_travel(technician_id=technician_id, job_id=job_id)
        if speed_kmh and speed_kmh > 0:
            estimate.speed_kmh = speed_kmh
            estimate.travel_minutes = calculate_travel_minutes(estimate.distance_km, speed_kmh=speed_kmh)
        return estimate
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/scheduling/travel/inter-job",
    response_model=TravelEstimate,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Calculate transit travel between consecutive jobs",
)
def get_inter_job_travel(
    from_job_id: str,
    to_job_id: str,
    speed_kmh: Optional[float] = None,
    db: Session = Depends(get_db),
) -> TravelEstimate:
    """
    Calculates transit distance and duration between consecutive job sites.
    """
    service = SchedulingService(db)
    try:
        estimate = service.calculate_inter_job_travel(from_job_id=from_job_id, to_job_id=to_job_id)
        if speed_kmh and speed_kmh > 0:
            estimate.speed_kmh = speed_kmh
            estimate.travel_minutes = calculate_travel_minutes(estimate.distance_km, speed_kmh=speed_kmh)
        return estimate
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/scheduling/geo-eligibility",
    response_model=GeoEligibilityResult,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Evaluate technician operational zone certification and travel metrics",
)
def get_geo_eligibility(
    technician_id: str,
    job_id: str,
    previous_job_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> GeoEligibilityResult:
    """
    Evaluates whether a technician is certified for the job's zone and computes travel metrics.
    """
    service = SchedulingService(db)
    try:
        return service.get_geo_eligibility(
            job_id=job_id,
            technician_id=technician_id,
            previous_job_id=previous_job_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))





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
