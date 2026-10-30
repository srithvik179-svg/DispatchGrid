from datetime import datetime
from typing import Optional, Union, Dict, Any, List
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
    TechnicianAvailabilityEvaluation,
    AvailabilityCheckRequest,
    TimeWindowValidationResult,
    FeasibleWindowResult,
    TimeWindowCheckRequest,
    SchedulingConflict,
    ConflictCheckResult,
    ConflictCheckRequest,
    TechnicianRejectionDetail,
    JobFeasibilityReport,
    FleetFeasibilitySummary,
    FeasibilityEvaluationRequest,
    ScheduleGenerateRequest,
    ScheduleGenerateResponse,
    ScheduleCurrentResponse,
    JobAssignmentResponse,
    TechnicianScheduleResponse,
    ObjectiveWeightsConfig,
    ScheduleScoreResult,
    ScoreEvaluationRequest,
    JobPriorityProfile,
    CompetingJobResolution,
    ConflictPairEvaluationRequest,
    TravelOptimizationResult,
    TravelOptimizationRequest,
    TechnicianTravelSummary,
)

from app.scheduling.service import SchedulingService
from app.scheduling.loader import load_eligible_technicians, load_existing_assignments
from app.scheduling.skills import filter_technicians_by_skills
from app.scheduling.equipment import filter_candidates_for_job
from app.scheduling.geo import haversine_distance, calculate_travel_minutes
from app.scheduling.time_windows import (
    validate_job_time_window,
    validate_job_instance_time_window,
    calculate_feasible_service_window,
)
from app.schemas.assignment import AssignmentSummary, AssignmentCreateRequest
from app.scheduling.conflicts import detect_scheduling_conflicts, persist_assignment_with_conflict_check



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
    "/scheduling/runs/initial",
    response_model=SchedulingResult,
    status_code=status.HTTP_201_CREATED,
    tags=["Scheduling Engine"],
    summary="Execute initial automatic deterministic scheduling algorithm",
)
def execute_initial_scheduling_run(
    config: Optional[SchedulingRunConfig] = None,
    db: Session = Depends(get_db),
) -> SchedulingResult:
    """
    Executes the initial automatic deterministic scheduling algorithm.
    Generates optimal, conflict-free assignments across the technician fleet,
    strictly preserving existing assignments and balancing fleet workload.
    """
    service = SchedulingService(db)
    return service.generate_initial_schedule(config=config)



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
    "/scheduling/availability/evaluate",
    response_model=TechnicianAvailabilityEvaluation,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Evaluate technician availability across shifts, unavailabilities, and simulation clock",
)
def evaluate_technician_availability_endpoint(
    req: AvailabilityCheckRequest,
    db: Session = Depends(get_db),
) -> TechnicianAvailabilityEvaluation:
    """
    Validates technician availability against scheduled working shifts, permitted overtime,
    unavailable intervals, and the authoritative simulation reference clock.
    """
    service = SchedulingService(db)
    duration = req.duration_minutes
    if not duration and req.job_id:
        job = db.query(Job).filter_by(id=req.job_id).first()
        if job:
            duration = job.duration_minutes
    if not duration:
        duration = 60

    try:
        return service.evaluate_availability(
            technician_id=req.technician_id,
            proposed_start=req.proposed_start,
            duration_minutes=duration,
            proposed_end=req.proposed_end,
            job_id=req.job_id,
            enforce_simulation_clock=req.enforce_simulation_clock,
            as_of_override=req.as_of,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/scheduling/availability/technician/{technician_id}/job/{job_id}",
    response_model=TechnicianAvailabilityEvaluation,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Engine"],
    summary="Check technician availability for a specific job in the database",
)
def get_technician_job_availability(
    technician_id: str,
    job_id: str,
    proposed_start: Optional[datetime] = None,
    enforce_simulation_clock: bool = True,
    db: Session = Depends(get_db),
) -> TechnicianAvailabilityEvaluation:
    """
    Evaluates whether a technician is available to perform a specific database job.
    Defaults proposed start to job.time_window_start and duration to job.duration_minutes.
    """
    service = SchedulingService(db)
    try:
        return service.check_job_technician_availability(
            technician_id=technician_id,
            job_id=job_id,
            proposed_start=proposed_start,
            enforce_simulation_clock=enforce_simulation_clock,
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


@router.post(
    "/scheduling/time-windows/validate",
    response_model=TimeWindowValidationResult,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Time Windows"],
    summary="Validate job hard time windows, service duration, and soft SLA deadlines",
)
def validate_time_window_endpoint(
    req: TimeWindowCheckRequest,
    db: Session = Depends(get_db),
) -> TimeWindowValidationResult:
    """
    Evaluates hard time window constraints, service duration, transit time feasibility,
    and simulation reference clock limits, while computing soft SLA lateness.
    """
    service = SchedulingService(db)
    ref_clock = req.as_of or service.get_clock()

    # If job_id is supplied, load job details as baseline
    w_start = req.time_window_start
    w_end = req.time_window_end
    duration = req.duration_minutes
    sla = req.sla_deadline

    if req.job_id:
        job = db.query(Job).filter_by(id=req.job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID '{req.job_id}' not found.",
            )
        w_start = w_start or job.time_window_start
        w_end = w_end or job.time_window_end
        duration = duration or job.duration_minutes
        sla = sla or job.sla_deadline

    if not w_start or not w_end or not duration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time_window_start, time_window_end, and duration_minutes must be specified or resolved from job_id.",
        )

    return validate_job_time_window(
        time_window_start=w_start,
        time_window_end=w_end,
        duration_minutes=duration,
        proposed_start=req.proposed_start,
        proposed_end=req.proposed_end,
        sla_deadline=sla,
        job_id=req.job_id,
        origin_departure_time=req.origin_departure_time,
        travel_minutes=req.travel_minutes or 0.0,
        as_of=ref_clock,
        enforce_simulation_clock=req.enforce_simulation_clock,
    )


@router.get(
    "/scheduling/time-windows/job/{job_id}",
    response_model=TimeWindowValidationResult,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Time Windows"],
    summary="Evaluate time window and SLA compliance for a specific job",
)
def get_job_time_window_validation(
    job_id: str,
    proposed_start: Optional[datetime] = None,
    proposed_end: Optional[datetime] = None,
    origin_departure_time: Optional[datetime] = None,
    travel_minutes: float = 0.0,
    enforce_simulation_clock: bool = True,
    db: Session = Depends(get_db),
) -> TimeWindowValidationResult:
    """
    Validates proposed appointment timestamps against a specific database job.
    Defaults proposed_start to job.time_window_start if omitted.
    """
    service = SchedulingService(db)
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    start_dt = proposed_start or job.time_window_start
    return service.validate_job_time_window(
        job_id=job_id,
        proposed_start=start_dt,
        proposed_end=proposed_end,
        origin_departure_time=origin_departure_time,
        travel_minutes=travel_minutes,
        enforce_simulation_clock=enforce_simulation_clock,
    )


@router.get(
    "/scheduling/time-windows/job/{job_id}/feasible",
    response_model=FeasibleWindowResult,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Time Windows"],
    summary="Compute earliest and latest feasible scheduling boundaries for a job",
)
def get_job_feasible_window_bounds(
    job_id: str,
    origin_departure_time: Optional[datetime] = None,
    travel_minutes: float = 0.0,
    enforce_simulation_clock: bool = True,
    db: Session = Depends(get_db),
) -> FeasibleWindowResult:
    """
    Computes earliest and latest feasible start times for a job given its hard window,
    transit time, simulation clock, and soft SLA deadline.
    """
    service = SchedulingService(db)
    try:
        return service.calculate_job_feasible_window(
            job_id=job_id,
            origin_departure_time=origin_departure_time,
            travel_minutes=travel_minutes,
            enforce_simulation_clock=enforce_simulation_clock,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/scheduling/conflicts/check",
    response_model=ConflictCheckResult,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Conflicts"],
    summary="Detect itinerary conflicts, travel buffer violations, and protected job collisions",
)
def check_scheduling_conflicts_endpoint(
    req: ConflictCheckRequest,
    db: Session = Depends(get_db),
) -> ConflictCheckResult:
    """
    Evaluates whether a proposed job assignment collides with technician's existing assignments,
    transit travel buffers between consecutive stops, protected in-progress jobs, or shift limits.
    """
    service = SchedulingService(db)
    try:
        return service.check_technician_conflicts(
            technician_id=req.technician_id,
            proposed_start=req.proposed_start,
            proposed_end=req.proposed_end,
            duration_minutes=req.duration_minutes,
            job_id=req.job_id,
            job_lat=req.job_lat,
            job_lng=req.job_lng,
            include_travel=req.include_travel,
            as_of=req.as_of,
            enforce_simulation_clock=req.enforce_simulation_clock,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/scheduling/conflicts/technician/{technician_id}/job/{job_id}",
    response_model=ConflictCheckResult,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Conflicts"],
    summary="Check conflict status for a specific technician and database job",
)
def get_technician_job_conflict(
    technician_id: str,
    job_id: str,
    proposed_start: Optional[datetime] = None,
    include_travel: bool = True,
    enforce_simulation_clock: bool = True,
    db: Session = Depends(get_db),
) -> ConflictCheckResult:
    """
    Evaluates potential conflicts for a specific technician dispatched to a database job.
    Defaults proposed_start to job.time_window_start if not provided.
    """
    service = SchedulingService(db)
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    start_dt = proposed_start or job.time_window_start
    try:
        return service.check_technician_conflicts(
            technician_id=technician_id,
            job_id=job_id,
            proposed_start=start_dt,
            include_travel=include_travel,
            enforce_simulation_clock=enforce_simulation_clock,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/scheduling/assignments",
    response_model=AssignmentSummary,
    status_code=status.HTTP_201_CREATED,
    tags=["Scheduling Assignments"],
    summary="Create a new assignment, strictly rejecting conflicts before persistence",
)
def create_scheduling_assignment(
    req: AssignmentCreateRequest,
    db: Session = Depends(get_db),
) -> AssignmentSummary:
    """
    Creates an assignment after verifying that no technician receives overlapping assignments,
    travel time buffer is respected, and active/completed jobs are protected.
    Invalid assignments are rejected before persistence.
    """
    try:
        assign = persist_assignment_with_conflict_check(
            db=db,
            job_id=req.job_id,
            technician_id=req.technician_id,
            start_time=req.start_time,
            end_time=req.end_time,
        )
        return AssignmentSummary(
            id=assign.id,
            job_id=assign.job_id,
            technician_id=assign.technician_id,
            start_time=assign.start_time,
            end_time=assign.end_time,
            status=assign.status,
            is_existing=assign.is_existing,
            job_title=assign.job.title if assign.job else None,
            technician_name=assign.technician.name if assign.technician else None,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/scheduling/feasibility/job/{job_id}",
    response_model=JobFeasibilityReport,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Feasibility"],
    summary="Get detailed feasibility classification and diagnostic explanation for a job",
)
def get_job_feasibility_endpoint(
    job_id: str,
    as_of: Optional[datetime] = None,
    db: Session = Depends(get_db),
) -> JobFeasibilityReport:
    """
    Classifies a job into feasible, currently_infeasible, or permanently_impossible,
    providing root-cause failure categories, technician rejection details, and actionable recommendations.
    """
    service = SchedulingService(db)
    try:
        return service.get_job_feasibility(job_id=job_id, as_of=as_of)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/scheduling/feasibility/fleet",
    response_model=FleetFeasibilitySummary,
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Feasibility"],
    summary="Evaluate fleet-wide feasibility classifications across all pending jobs",
)
def get_fleet_feasibility_endpoint(
    as_of: Optional[datetime] = None,
    db: Session = Depends(get_db),
) -> FleetFeasibilitySummary:
    """
    Aggregates diagnostic feasibility metrics across the entire pending backlog.
    """
    service = SchedulingService(db)
    return service.get_fleet_feasibility(as_of=as_of)


@router.post(
    "/scheduling/feasibility/evaluate",
    response_model=Union[JobFeasibilityReport, FleetFeasibilitySummary],
    status_code=status.HTTP_200_OK,
    tags=["Scheduling Feasibility"],
    summary="Evaluate feasibility for a specific job or fleet backlog",
)
def evaluate_feasibility_endpoint(
    req: FeasibilityEvaluationRequest,
    db: Session = Depends(get_db),
):
    """
    Evaluates job feasibility report if job_id is provided, otherwise evaluates entire fleet.
    """
    service = SchedulingService(db)
    if req.job_id:
        try:
            return service.get_job_feasibility(job_id=req.job_id, as_of=req.as_of)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
    return service.get_fleet_feasibility(as_of=req.as_of)


# =========================================================================
# PHASE 22 – Scheduling API Endpoints
# =========================================================================

@router.post(
    "/schedule/generate",
    response_model=ScheduleGenerateResponse,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Trigger automatic schedule generation and safely persist assignments",
)
@router.post(
    "/scheduling/generate",
    response_model=ScheduleGenerateResponse,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def generate_schedule_endpoint(
    req: Optional[ScheduleGenerateRequest] = None,
    db: Session = Depends(get_db),
) -> ScheduleGenerateResponse:
    """
    Executes the automatic scheduling engine across all pending jobs,
    persisting new assignments safely into the database while strictly preserving
    all pre-existing assignments. Returns structured assignments and diagnostic
    explanations for all unassigned jobs.
    """
    service = SchedulingService(db)
    try:
        return service.generate_and_persist_schedule(req=req)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scheduling execution failed: {str(e)}",
        )


@router.get(
    "/schedule/current",
    response_model=ScheduleCurrentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Retrieve current operational schedule, assigned jobs, and unassigned explanations",
)
@router.get(
    "/scheduling/current",
    response_model=ScheduleCurrentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def get_current_schedule_endpoint(
    db: Session = Depends(get_db),
) -> ScheduleCurrentResponse:
    """
    Retrieves the current operational workforce schedule from the database,
    providing all assigned jobs, technician routes, and actionable feasibility
    diagnostics for pending/unassigned jobs.
    """
    service = SchedulingService(db)
    return service.get_current_schedule()


@router.get(
    "/jobs/{job_id}/assignment",
    response_model=JobAssignmentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Get assignment status and technician details for a specific job",
)
def get_job_assignment_endpoint(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobAssignmentResponse:
    """
    Returns dispatch assignment details if job is assigned, or diagnostic
    feasibility explanation explaining why it remains unassigned.
    """
    service = SchedulingService(db)
    try:
        return service.get_job_assignment(job_id=job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/technicians/{technician_id}/schedule",
    response_model=TechnicianScheduleResponse,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Get full sequential itinerary and route schedule for a technician",
)
def get_technician_schedule_endpoint(
    technician_id: str,
    db: Session = Depends(get_db),
) -> TechnicianScheduleResponse:
    """
    Returns sequential route schedule for a technician, including Haversine transit
    buffers and distances between consecutive stops.
    """
    service = SchedulingService(db)
    try:
        return service.get_technician_schedule(technician_id=technician_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/schedule/reset",
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Reset schedule to baseline preserving the 7 existing assignments",
)
@router.post(
    "/scheduling/reset",
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def reset_schedule_endpoint(
    db: Session = Depends(get_db),
):
    """
    Clears all newly generated assignments and reverts modified jobs back to pending,
    strictly preserving all 7 pre-existing assignments.
    """
    service = SchedulingService(db)
    return service.reset_schedule_to_baseline()


# =========================================================================
# PHASE 23 – Objective Function & Scoring Engine Endpoints
# =========================================================================

@router.get(
    "/schedule/score",
    response_model=ScheduleScoreResult,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Evaluate objective score, cost components, and hard constraint feasibility for current schedule",
)
@router.get(
    "/scheduling/score",
    response_model=ScheduleScoreResult,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def get_schedule_score_endpoint(
    db: Session = Depends(get_db),
) -> ScheduleScoreResult:
    """
    Evaluates the multi-criteria objective score and hard feasibility for the active schedule.
    Provides separable component costs for SLA lateness, transit travel, unassigned priority,
    overtime, and assignment churn.
    """
    service = SchedulingService(db)
    return service.get_schedule_score()


@router.post(
    "/schedule/score",
    response_model=ScheduleScoreResult,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Evaluate schedule objective score with custom configurable weights",
)
@router.post(
    "/scheduling/score",
    response_model=ScheduleScoreResult,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def evaluate_schedule_score_endpoint(
    req: Optional[ScoreEvaluationRequest] = None,
    db: Session = Depends(get_db),
) -> ScheduleScoreResult:
    """
    Evaluates the multi-criteria objective score using caller-specified weights and simulation parameters.
    Ensures hard operational constraints are verified independently of objective cost.
    """
    service = SchedulingService(db)
    weights = req.weights if req else None
    as_of = req.as_of if req else None
    respect_existing = req.respect_existing_assignments if req else True
    return service.get_schedule_score(
        weights=weights,
        as_of=as_of,
        respect_existing_assignments=respect_existing,
    )


# =========================================================================
# PHASE 24 – Priority-Aware Optimisation & Conflict Arbitration Endpoints
# =========================================================================

@router.get(
    "/scheduling/priority/job/{job_id}",
    response_model=JobPriorityProfile,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Get multi-criteria priority, technician scarcity, and window tightness profile for a job",
)
@router.get(
    "/jobs/{job_id}/priority-profile",
    response_model=JobPriorityProfile,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def get_job_priority_profile_endpoint(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobPriorityProfile:
    """
    Retrieves the 7-tier priority profile for a job, evaluating technician scarcity
    (qualified technicians with skills, equipment, and zone eligibility), time window tightness,
    slack buffer, and SLA deadlines.
    """
    service = SchedulingService(db)
    try:
        return service.get_job_priority_profile(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/schedule/priority/resolve",
    response_model=CompetingJobResolution,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Deterministically arbitrate between two competing jobs with full explanatory rationale",
)
@router.post(
    "/scheduling/priority/resolve",
    response_model=CompetingJobResolution,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def resolve_competing_jobs_endpoint(
    req: ConflictPairEvaluationRequest,
    db: Session = Depends(get_db),
) -> CompetingJobResolution:
    """
    Arbitrates between two competing jobs that contend for identical technician capabilities,
    territories, or overlapping time windows.
    Applies the documented 7-tier tie-breaking rules:
    1. Priority Level (Urgent > High > Medium > Low)
    2. Technician Scarcity (fewer qualified technicians wins)
    3. Time Window Tightness (tighter window wins)
    4. Soft SLA Deadline (earliest deadline wins)
    5. Hard Window End (earliest expiration wins)
    6. Window Start (earliest opening wins)
    7. Alphanumeric Job ID deterministic tie-breaker
    """
    service = SchedulingService(db)
    try:
        return service.resolve_competing_jobs(req.job_id_a, req.job_id_b)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/schedule/priority/ordered",
    response_model=list[JobPriorityProfile],
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Get all pending jobs ordered by priority-aware multi-criteria hierarchy",
)
@router.get(
    "/scheduling/priority/ordered",
    response_model=list[JobPriorityProfile],
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def get_prioritized_pending_jobs_endpoint(
    db: Session = Depends(get_db),
) -> list[JobPriorityProfile]:
    """
    Returns all pending jobs ranked by the documented 7-tier priority and technician scarcity ordering.
    """
    service = SchedulingService(db)
    return service.get_prioritized_pending_jobs()


# =========================================================================
# PHASE 25 – Travel-Time Optimisation Endpoints
# =========================================================================

@router.post(
    "/schedule/optimize/travel",
    response_model=TravelOptimizationResult,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Optimize technician travel time and minimize unnecessary zone switching",
)
@router.post(
    "/scheduling/optimize/travel",
    response_model=TravelOptimizationResult,
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def optimize_travel_endpoint(
    req: Optional[TravelOptimizationRequest] = None,
    db: Session = Depends(get_db),
) -> TravelOptimizationResult:
    """
    Executes travel-time schedule optimization:
    - Calculates total travel time for each technician (home-to-first + consecutive inter-job legs).
    - Evaluates geographical assignment alternatives.
    - Re-orders technician routes to cluster jobs geographically and minimize zone switching.
    - Strictly preserves all hard operational constraints.
    - Delivers measured improvements and explainable action logs.
    """
    service = SchedulingService(db)
    persist = req.persist if req else False
    run_id = req.run_id if req else None
    return service.optimize_travel(persist=persist, run_id=run_id)


@router.get(
    "/schedule/travel-metrics",
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    summary="Get comprehensive fleet travel metrics and leg-by-leg technician itineraries",
)
@router.get(
    "/scheduling/travel-metrics",
    status_code=status.HTTP_200_OK,
    tags=["Schedule Operations"],
    include_in_schema=False,
)
def get_travel_metrics_endpoint(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns complete fleet travel analytics:
    - Total fleet transit minutes and distance km.
    - Total zone switches and average transit time per job.
    - Leg-by-leg breakdowns for every technician.
    """
    service = SchedulingService(db)
    return service.get_travel_metrics()











