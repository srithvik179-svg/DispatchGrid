import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session


from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.models.job import Job
from app.models.technician import Technician
from app.models.assignment import Assignment
from app.models.system import SystemMetadata
from app.scheduling.schemas import (
    SchedulingRunConfig,
    SchedulingInput,
    SchedulingResult,
    AssignedJobPlan,
    JobSkillCandidates,
    JobCandidateEvaluation,
    TravelEstimate,
    GeoEligibilityResult,
    ShiftAvailabilityResult,
    UnavailabilityCheckResult,
    TechnicianAvailabilityEvaluation,
    TimeWindowValidationResult,
    FeasibleWindowResult,
    SchedulingConflict,
    ConflictCheckResult,
    JobFeasibilityReport,
    FleetFeasibilitySummary,
    ScheduleGenerateRequest,
    ScheduleAssignmentItem,
    UnassignedJobExplanation,
    ScheduleGenerateResponse,
    ScheduleCurrentResponse,
    JobAssignmentResponse,
    TechnicianItineraryItem,
    TechnicianScheduleResponse,
    ObjectiveWeightsConfig,
    ScheduleScoreResult,
    JobPriorityProfile,
    CompetingJobResolution,
    TravelOptimizationResult,
    TechnicianTravelSummary,
    TravelMetricsComparison,
    JobSLADetail,
    FleetSLAMetrics,
    SLAOptimizationResult,
    CompetingSLAResolution,
)
from app.scheduling.loader import (
    get_simulation_clock,
    get_planning_horizon,
    load_scheduling_inputs,
    load_pending_jobs,
    load_eligible_technicians,
    load_existing_assignments,
)
from app.scheduling.skills import (
    DEFAULT_UNSUPPORTED_SKILLS,
    filter_technicians_by_skills,
    filter_all_jobs_by_skills,
)
from app.scheduling.equipment import (
    STANDARD_FLEET_EQUIPMENT,
    filter_candidates_for_job,
    filter_all_jobs_candidates,
)
from app.scheduling.geo import (
    DEFAULT_TRANSIT_SPEED_KMH,
    haversine_distance,
    calculate_travel_minutes,
    calculate_home_to_job_travel,
    calculate_inter_job_travel,
    evaluate_geographic_eligibility,
)
from app.scheduling.availability import (
    evaluate_technician_availability,
    check_shift_coverage,
    check_unavailability_collision,
)
from app.scheduling.time_windows import (
    validate_job_time_window as check_time_window,
    validate_job_instance_time_window,
    calculate_feasible_service_window,
)
from app.scheduling.conflicts import detect_scheduling_conflicts
from app.scheduling.algorithm import run_deterministic_initial_scheduler
from app.scheduling.feasibility import classify_job_feasibility, classify_fleet_feasibility




def generate_run_id(prefix: str = "RUN") -> str:
    """
    Generate a unique, chronological, human-readable run ID.
    Example: RUN-20261102-100000-A1B2C3
    """
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand_suffix = uuid.uuid4().hex[:6].upper()
    return f"{prefix}-{now_str}-{rand_suffix}"


class SchedulingService:
    """
    Independent scheduling service for DispatchGrid.
    Decoupled from HTTP routes and presentation logic.
    Responsible for:
      - Loading scheduling inputs (pending jobs, eligible technicians, existing assignments).
      - Respecting simulation reference clock and planning horizons.
      - Generating run tracking IDs.
      - Filtering candidates by certified skill proficiencies and mandatory equipment tooling.
      - Constructing standardized scheduling plan results.
      - Guaranteeing that pre-existing locked/in-progress assignments are strictly preserved.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_clock(self, override: Optional[datetime] = None) -> datetime:
        """Retrieve the active simulation clock."""
        return get_simulation_clock(self.db, override=override)

    def get_simulation_clock(self, override: Optional[datetime] = None) -> datetime:
        """Alias for get_clock retrieving the active simulation clock."""
        return self.get_clock(override=override)

    def get_horizon(
        self,
        start_override: Optional[datetime] = None,
        end_override: Optional[datetime] = None,
    ):
        """Retrieve the active planning horizon."""
        return get_planning_horizon(
            self.db,
            start_override=start_override,
            end_override=end_override,
        )

    def get_unsupported_skills(self) -> List[str]:
        """Retrieve unsupported skills defined in system metadata or fallback defaults."""
        record = self.db.query(SystemMetadata).filter_by(key="unsupported_skills").first()
        if record and record.value:
            try:
                parsed = json.loads(record.value)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return list(DEFAULT_UNSUPPORTED_SKILLS)

    def get_fleet_equipment(self) -> List[str]:
        """Retrieve supported equipment inventory defined in system metadata or fallback defaults."""
        record = self.db.query(SystemMetadata).filter_by(key="equipment").first()
        if record and record.value:
            try:
                parsed = json.loads(record.value)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return list(STANDARD_FLEET_EQUIPMENT)

    def load_inputs(
        self,
        run_id: Optional[str] = None,
        config: Optional[SchedulingRunConfig] = None,
    ) -> SchedulingInput:
        """
        Loads all required data structures from the database into an immutable SchedulingInput container.
        """
        active_run_id = run_id or generate_run_id()
        return load_scheduling_inputs(self.db, run_id=active_run_id, config=config)

    def get_candidates_by_skill(self, job_id: str) -> JobSkillCandidates:
        """
        Evaluates candidate technicians strictly by skills for a given job ID.
        Identifies missing skills, handles unsupported high_voltage requirements,
        and constructs structured rejection reasons.
        """
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        technicians = load_eligible_technicians(self.db)
        unsupported = self.get_unsupported_skills()

        return filter_technicians_by_skills(
            job=job,
            technicians=technicians,
            unsupported_skills=unsupported,
        )

    def get_all_skill_candidates(self) -> Dict[str, JobSkillCandidates]:
        """
        Evaluates candidate technicians by skills for all pending jobs in the database.
        """
        jobs = load_pending_jobs(self.db)
        technicians = load_eligible_technicians(self.db)
        unsupported = self.get_unsupported_skills()

        return filter_all_jobs_by_skills(
            jobs=jobs,
            technicians=technicians,
            unsupported_skills=unsupported,
        )

    def get_candidates_for_job(self, job_id: str) -> JobCandidateEvaluation:
        """
        Evaluates candidate technicians enforcing BOTH mandatory skills and mandatory equipment.
        Identifies missing equipment separately from missing skills.
        """
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        technicians = load_eligible_technicians(self.db)
        unsupported_skills = self.get_unsupported_skills()
        fleet_equipment = self.get_fleet_equipment()

        return filter_candidates_for_job(
            job=job,
            technicians=technicians,
            unsupported_skills=unsupported_skills,
            fleet_equipment_inventory=fleet_equipment,
        )

    def get_all_job_candidates(self) -> Dict[str, JobCandidateEvaluation]:
        """
        Evaluates candidate compatibility combining skills and equipment for all pending jobs.
        """
        jobs = load_pending_jobs(self.db)
        technicians = load_eligible_technicians(self.db)
        unsupported_skills = self.get_unsupported_skills()
        fleet_equipment = self.get_fleet_equipment()

        return filter_all_jobs_candidates(
            jobs=jobs,
            technicians=technicians,
            unsupported_skills=unsupported_skills,
            fleet_equipment_inventory=fleet_equipment,
        )

    def get_travel_model(self) -> Dict[str, Any]:
        """Retrieve travel model configuration from system metadata."""
        record = self.db.query(SystemMetadata).filter_by(key="travel_model").first()
        if record and record.value:
            try:
                parsed = json.loads(record.value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {"method": "haversine", "speed_kmh": DEFAULT_TRANSIT_SPEED_KMH}

    def get_travel_speed(self) -> float:
        """Retrieve transit speed in km/h from travel model configuration."""
        tm = self.get_travel_model()
        try:
            return float(tm.get("speed_kmh", DEFAULT_TRANSIT_SPEED_KMH))
        except (TypeError, ValueError):
            return DEFAULT_TRANSIT_SPEED_KMH

    def calculate_home_travel(self, technician_id: str, job_id: str) -> TravelEstimate:
        """Calculate first-job transit distance and minutes from technician home location."""
        tech = self.db.query(Technician).filter_by(id=technician_id).first()
        if not tech:
            raise ValueError(f"Technician with ID '{technician_id}' not found.")
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")
        speed = self.get_travel_speed()
        return calculate_home_to_job_travel(technician=tech, job=job, speed_kmh=speed)

    def calculate_inter_job_travel(self, from_job_id: str, to_job_id: str) -> TravelEstimate:
        """Calculate transit distance and minutes between consecutive jobs."""
        from_job = self.db.query(Job).filter_by(id=from_job_id).first()
        if not from_job:
            raise ValueError(f"Origin job with ID '{from_job_id}' not found.")
        to_job = self.db.query(Job).filter_by(id=to_job_id).first()
        if not to_job:
            raise ValueError(f"Destination job with ID '{to_job_id}' not found.")
        speed = self.get_travel_speed()
        return calculate_inter_job_travel(from_job=from_job, to_job=to_job, speed_kmh=speed)

    def get_geo_eligibility(
        self,
        job_id: str,
        technician_id: str,
        previous_job_id: Optional[str] = None,
    ) -> GeoEligibilityResult:
        """
        Evaluates technician operational zone certification and computes travel from home or previous job.
        """
        tech = self.db.query(Technician).filter_by(id=technician_id).first()
        if not tech:
            raise ValueError(f"Technician with ID '{technician_id}' not found.")
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")
        prev_job = None
        if previous_job_id:
            prev_job = self.db.query(Job).filter_by(id=previous_job_id).first()
            if not prev_job:
                raise ValueError(f"Previous job with ID '{previous_job_id}' not found.")
        speed = self.get_travel_speed()
        return evaluate_geographic_eligibility(
            technician=tech,
            job=job,
            previous_job=prev_job,
            speed_kmh=speed,
        )

    def evaluate_availability(
        self,
        technician_id: str,
        proposed_start: datetime,
        duration_minutes: int,
        proposed_end: Optional[datetime] = None,
        job_id: Optional[str] = None,
        enforce_simulation_clock: bool = True,
        as_of_override: Optional[datetime] = None,
    ) -> TechnicianAvailabilityEvaluation:
        """
        Evaluates technician shift coverage, permitted overtime, unavailable windows,
        and simulation clock restrictions.
        """
        tech = self.db.query(Technician).filter_by(id=technician_id).first()
        if not tech:
            raise ValueError(f"Technician with ID '{technician_id}' not found.")

        sim_clock = as_of_override or self.get_clock()

        return evaluate_technician_availability(
            technician=tech,
            proposed_start=proposed_start,
            duration_minutes=duration_minutes,
            proposed_end=proposed_end,
            job_id=job_id,
            simulation_clock=sim_clock,
            enforce_simulation_clock=enforce_simulation_clock,
        )

    def check_job_technician_availability(
        self,
        technician_id: str,
        job_id: str,
        proposed_start: Optional[datetime] = None,
        enforce_simulation_clock: bool = True,
    ) -> TechnicianAvailabilityEvaluation:
        """
        Evaluates technician availability for a specific job in the database.
        Defaults to job.time_window_start and job.duration_minutes if not overridden.
        """
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        start_dt = proposed_start or job.time_window_start
        return self.evaluate_availability(
            technician_id=technician_id,
            proposed_start=start_dt,
            duration_minutes=job.duration_minutes,
            job_id=job_id,
            enforce_simulation_clock=enforce_simulation_clock,
        )

    def validate_job_time_window(
        self,
        job_id: str,
        proposed_start: datetime,
        proposed_end: Optional[datetime] = None,
        origin_departure_time: Optional[datetime] = None,
        travel_minutes: float = 0.0,
        as_of: Optional[datetime] = None,
        enforce_simulation_clock: bool = True,
    ) -> TimeWindowValidationResult:
        """
        Validates hard time window constraints, service duration, travel time feasibility,
        and simulation clock bounds for a specific database job.
        """
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        ref_clock = as_of or self.get_simulation_clock()

        return validate_job_instance_time_window(
            job=job,
            proposed_start=proposed_start,
            proposed_end=proposed_end,
            origin_departure_time=origin_departure_time,
            travel_minutes=travel_minutes,
            as_of=ref_clock,
            enforce_simulation_clock=enforce_simulation_clock,
        )

    def calculate_job_feasible_window(
        self,
        job_id: str,
        origin_departure_time: Optional[datetime] = None,
        travel_minutes: float = 0.0,
        as_of: Optional[datetime] = None,
        enforce_simulation_clock: bool = True,
    ) -> FeasibleWindowResult:
        """
        Calculates the permissible scheduling window [earliest_feasible_start, latest_feasible_start]
        for a job taking into account transit time, duration, and simulation reference clock.
        """
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        ref_clock = as_of or self.get_simulation_clock()

        return calculate_feasible_service_window(
            time_window_start=job.time_window_start,
            time_window_end=job.time_window_end,
            duration_minutes=job.duration_minutes,
            sla_deadline=job.sla_deadline,
            origin_departure_time=origin_departure_time,
            travel_minutes=travel_minutes,
            as_of=ref_clock,
            enforce_simulation_clock=enforce_simulation_clock,
            job_id=job.id,
        )

    def check_technician_conflicts(
        self,
        technician_id: str,
        proposed_start: datetime,
        proposed_end: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
        job_id: Optional[str] = None,
        job_lat: Optional[float] = None,
        job_lng: Optional[float] = None,
        include_travel: bool = True,
        as_of: Optional[datetime] = None,
        enforce_simulation_clock: bool = True,
    ) -> ConflictCheckResult:
        """
        Evaluates scheduling conflicts, travel buffers, protected active assignments,
        and multi-date boundaries for a technician against existing assignments.
        """
        technician = self.db.query(Technician).filter_by(id=technician_id).first()
        if not technician:
            raise ValueError(f"Technician with ID '{technician_id}' not found.")

        # If job_id supplied, resolve missing duration and coordinates
        actual_lat = job_lat
        actual_lng = job_lng
        actual_duration = duration_minutes

        if job_id:
            job = self.db.query(Job).filter_by(id=job_id).first()
            if job:
                if actual_lat is None:
                    actual_lat = job.lat
                if actual_lng is None:
                    actual_lng = job.lng
                if actual_duration is None:
                    actual_duration = job.duration_minutes

        # Resolve end timestamp
        actual_end = proposed_end
        if actual_end is None and actual_duration:
            actual_end = proposed_start + timedelta(minutes=actual_duration)
        elif actual_end is None:
            raise ValueError("Either proposed_end or duration_minutes (or job_id) must be provided.")

        ref_clock = as_of or self.get_clock()
        existing_assignments = load_existing_assignments(self.db)

        return detect_scheduling_conflicts(
            technician_id=technician_id,
            proposed_start=proposed_start,
            proposed_end=actual_end,
            job_id=job_id,
            job_lat=actual_lat,
            job_lng=actual_lng,
            existing_assignments=existing_assignments,
            technician=technician,
            as_of=ref_clock,
            include_travel=include_travel,
            enforce_simulation_clock=enforce_simulation_clock,
        )





    def initialize_run(
        self,
        config: Optional[SchedulingRunConfig] = None,
    ) -> SchedulingResult:
        """
        Establishes a new scheduling run session.
        Loads all inputs, preserves existing assignments, and forms the initial baseline scheduling state.
        
        SAFETY GUARANTEE: Does NOT modify any assignments or records in the database.
        """
        run_id = generate_run_id()
        inputs = self.load_inputs(run_id=run_id, config=config)

        # 1. Convert pre-existing assignments into protected plans
        preserved_plans = []
        for existing in inputs.existing_assignments:
            plan = AssignedJobPlan(
                job_id=existing.job_id,
                technician_id=existing.technician_id,
                scheduled_start=existing.start_time,
                scheduled_end=existing.end_time,
                travel_time_minutes=0.0,
                is_existing=True,
                status=existing.status,
                details={
                    "assignment_id": existing.id,
                    "actual_start": existing.actual_start.isoformat() if existing.actual_start else None,
                    "job_title": existing.job_title,
                    "technician_name": existing.technician_name,
                },
            )
            preserved_plans.append(plan)

        # 2. In this foundation phase, pending jobs remain unassigned until optimizer executes
        unassigned_job_ids = [job.id for job in inputs.pending_jobs]

        total_evaluated_jobs = len(inputs.existing_assignments) + len(inputs.pending_jobs)

        # 3. Analyze combined skill & equipment candidate availability
        candidate_evaluations = self.get_all_job_candidates()
        unassignable_jobs = [
            jid for jid, cand in candidate_evaluations.items() if not cand.is_assignable
        ]
        skill_only_jobs = {
            jid: cand.skill_only_matching_candidates
            for jid, cand in candidate_evaluations.items()
            if cand.skill_only_matching_candidates
        }

        # Also compute skill-specific unassignable count for backwards compatibility
        skill_analysis = self.get_all_skill_candidates()
        unassignable_by_skills = [
            jid for jid, cand in skill_analysis.items() if not cand.is_assignable
        ]

        # 4. Assemble standardized SchedulingResult
        result = SchedulingResult(
            run_id=run_id,
            status="initialized",
            as_of=inputs.as_of,
            horizon_start=inputs.horizon_start,
            horizon_end=inputs.horizon_end,
            total_jobs=total_evaluated_jobs,
            pending_jobs_count=inputs.pending_jobs_count,
            assigned_jobs_count=len(preserved_plans),
            unassigned_jobs_count=len(unassigned_job_ids),
            existing_assignments_preserved=True,
            assignments=preserved_plans,
            unassigned_jobs=unassigned_job_ids,
            metrics={
                "technicians_available": inputs.technicians_count,
                "locked_assignments_count": len(preserved_plans),
                "unassigned_backlog_count": len(unassigned_job_ids),
                "unassignable_skills_jobs_count": len(unassignable_by_skills),
                "unassignable_skills_jobs": unassignable_by_skills,
                "unassignable_jobs_count": len(unassignable_jobs),
                "unassignable_jobs": unassignable_jobs,
                "jobs_with_equipment_lacking_candidates": list(skill_only_jobs.keys()),
                "unsupported_skills": self.get_unsupported_skills(),
                "fleet_equipment_inventory": self.get_fleet_equipment(),
                "travel_model": self.get_travel_model(),
                "mode": config.mode if config else "baseline",
                "ready_for_optimization": True,
            },
            created_at=datetime.now(timezone.utc),
        )


        return result

    def generate_initial_schedule(
        self,
        config: Optional[SchedulingRunConfig] = None,
    ) -> SchedulingResult:
        """
        Executes the initial automatic deterministic scheduling algorithm.
        Generates optimal, conflict-free assignments across the technician roster
        while strictly preserving all pre-existing assignments.
        """
        run_id = generate_run_id()
        inputs = self.load_inputs(run_id=run_id, config=config)
        unsupported = self.get_unsupported_skills()
        return run_deterministic_initial_scheduler(inputs, unsupported_skills=unsupported)

    def get_job_feasibility(
        self,
        job_id: str,
        as_of: Optional[datetime] = None,
    ) -> JobFeasibilityReport:
        """
        Classifies scheduling feasibility for a job into:
        - 'feasible'
        - 'currently_infeasible'
        - 'permanently_impossible'
        along with primary category and actionable explanations.
        """
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        from app.schemas.job import JobResponse
        from app.scheduling.conflicts import extract_assignment_info

        inputs = self.load_inputs(config=SchedulingRunConfig(as_of=as_of) if as_of else None)
        job_resp = JobResponse.model_validate(job)
        unsupported = self.get_unsupported_skills()
        fleet_equip = self.get_fleet_equipment()

        itineraries = {t.id: [] for t in inputs.technicians}
        for a in inputs.existing_assignments:
            info = extract_assignment_info(a)
            if a.technician_id in itineraries:
                itineraries[a.technician_id].append(info)

        return classify_job_feasibility(
            job=job_resp,
            technicians=inputs.technicians,
            technician_itineraries=itineraries,
            as_of=inputs.as_of,
            unsupported_skills=unsupported,
            fleet_equipment=fleet_equip,
        )

    def get_fleet_feasibility(
        self,
        as_of: Optional[datetime] = None,
    ) -> FleetFeasibilitySummary:
        """
        Evaluates and aggregates feasibility classifications for all pending jobs in the fleet.
        """
        from app.scheduling.conflicts import extract_assignment_info

        inputs = self.load_inputs(config=SchedulingRunConfig(as_of=as_of) if as_of else None)
        unsupported = self.get_unsupported_skills()
        fleet_equip = self.get_fleet_equipment()

        itineraries = {t.id: [] for t in inputs.technicians}
        for a in inputs.existing_assignments:
            info = extract_assignment_info(a)
            if a.technician_id in itineraries:
                itineraries[a.technician_id].append(info)

        return classify_fleet_feasibility(
            jobs=inputs.pending_jobs,
            technicians=inputs.technicians,
            technician_itineraries=itineraries,
            as_of=inputs.as_of,
            unsupported_skills=unsupported,
            fleet_equipment=fleet_equip,
            run_id=inputs.run_id,
        )

    def generate_and_persist_schedule(
        self,
        req: Optional[ScheduleGenerateRequest] = None,
    ) -> ScheduleGenerateResponse:
        """
        Generates an automatic deterministic schedule across all pending jobs,
        persisting new assignments safely while strictly preserving existing assignments.
        Returns complete assigned plans and unassigned job feasibility explanations.
        """
        request = req or ScheduleGenerateRequest()
        clock_as_of = request.as_of
        persist = request.persist

        run_id = generate_run_id()
        config = SchedulingRunConfig(
            as_of=clock_as_of,
            mode=request.mode,
            respect_existing_assignments=request.respect_existing_assignments,
        )
        inputs = self.load_inputs(run_id=run_id, config=config)
        unsupported = self.get_unsupported_skills()
        fleet_equip = self.get_fleet_equipment()

        # Run the deterministic initial scheduling algorithm
        sched_result = run_deterministic_initial_scheduler(inputs, unsupported_skills=unsupported)

        # Lookup maps for fast enrichment
        jobs_map = {j.id: j for j in self.db.query(Job).all()}
        techs_map = {t.id: t for t in self.db.query(Technician).all()}

        # 1. Persist to database if requested
        if persist:
            # Strictly identify existing assignment job IDs to protect
            existing_records = self.db.query(Assignment).filter(
                (Assignment.is_existing == True) | (Assignment.status.in_(["completed", "in_progress"]))
            ).all()
            protected_job_ids = {a.job_id for a in existing_records}

            # Delete previous non-existing generated assignments
            self.db.query(Assignment).filter_by(is_existing=False).delete()

            # Reset previous non-existing jobs back to pending
            non_existing_jobs = self.db.query(Job).filter(
                ~Job.id.in_(protected_job_ids),
                Job.status == "assigned"
            ).all()
            for j in non_existing_jobs:
                j.status = "pending"
                j.assigned_technician_id = None
                j.scheduled_start = None
                j.scheduled_end = None

            # Persist newly scheduled job plans
            for plan in sched_result.assignments:
                if plan.is_existing or plan.job_id in protected_job_ids:
                    continue

                new_assignment = Assignment(
                    job_id=plan.job_id,
                    technician_id=plan.technician_id,
                    start_time=plan.scheduled_start,
                    end_time=plan.scheduled_end,
                    status=plan.status or "scheduled",
                    is_existing=False,
                )
                self.db.add(new_assignment)

                job_record = jobs_map.get(plan.job_id)
                if job_record:
                    job_record.status = "assigned"
                    job_record.assigned_technician_id = plan.technician_id
                    job_record.scheduled_start = plan.scheduled_start
                    job_record.scheduled_end = plan.scheduled_end

            self.db.commit()

        # Reload assignments with generated IDs
        assignments_records = self.db.query(Assignment).all() if persist else []
        assign_id_map = {a.job_id: a.id for a in assignments_records}

        # Build structured ScheduleAssignmentItems
        structured_assignments: List[ScheduleAssignmentItem] = []
        assigned_tech_ids = set()

        for plan in sched_result.assignments:
            assigned_tech_ids.add(plan.technician_id)
            job = jobs_map.get(plan.job_id)
            tech = techs_map.get(plan.technician_id)
            dist_km = 0.0
            if job and tech:
                dist_km = haversine_distance(tech.home_lat, tech.home_lng, job.lat, job.lng)

            item = ScheduleAssignmentItem(
                assignment_id=assign_id_map.get(plan.job_id),
                job_id=plan.job_id,
                technician_id=plan.technician_id,
                technician_name=tech.name if tech else plan.technician_id,
                job_title=job.title if job else None,
                customer_name=job.customer_name if job else None,
                zone_id=job.zone_id if job else None,
                priority=job.priority if job else None,
                priority_label=job.priority_label if job else None,
                start_time=plan.scheduled_start,
                end_time=plan.scheduled_end,
                duration_minutes=int((plan.scheduled_end - plan.scheduled_start).total_seconds() / 60),
                travel_time_minutes=plan.travel_time_minutes,
                distance_km=round(dist_km, 2),
                status=plan.status,
                is_existing=plan.is_existing,
            )
            structured_assignments.append(item)

        # 2. Build unassigned job diagnostic explanations
        itineraries = {t.id: [] for t in inputs.technicians}
        for plan in sched_result.assignments:
            job = jobs_map.get(plan.job_id)
            if job and plan.technician_id in itineraries:
                itineraries[plan.technician_id].append({
                    "job_id": plan.job_id,
                    "technician_id": plan.technician_id,
                    "start_time": plan.scheduled_start,
                    "end_time": plan.scheduled_end,
                    "status": plan.status,
                    "lat": job.lat,
                    "lng": job.lng,
                    "zone_id": job.zone_id,
                })

        unassigned_explanations: List[UnassignedJobExplanation] = []
        from app.schemas.job import JobResponse
        for unassigned_id in sched_result.unassigned_jobs:
            job = jobs_map.get(unassigned_id)
            if not job:
                continue
            job_resp = JobResponse.model_validate(job)
            feasibility = classify_job_feasibility(
                job=job_resp,
                technicians=inputs.technicians,
                technician_itineraries=itineraries,
                as_of=inputs.as_of,
                unsupported_skills=unsupported,
                fleet_equipment=fleet_equip,
            )
            unassigned_explanations.append(
                UnassignedJobExplanation(
                    job_id=job.id,
                    title=job.title,
                    customer_name=job.customer_name,
                    zone_id=job.zone_id,
                    priority=job.priority,
                    priority_label=job.priority_label,
                    duration_minutes=job.duration_minutes,
                    classification=feasibility.classification,
                    primary_category=feasibility.primary_category,
                    rejection_summary=feasibility.rejection_summary,
                    actionable_recommendation=feasibility.actionable_recommendation,
                    required_skills=job.required_skills or [],
                    required_equipment=job.required_equipment or [],
                )
            )

        return ScheduleGenerateResponse(
            run_id=sched_result.run_id,
            as_of=sched_result.as_of,
            total_jobs=sched_result.total_jobs,
            assigned_count=len(structured_assignments),
            unassigned_count=len(unassigned_explanations),
            technicians_count=len(inputs.technicians),
            technicians_utilized=len(assigned_tech_ids),
            persisted=persist,
            existing_assignments_preserved=sched_result.existing_assignments_preserved,
            assignments=structured_assignments,
            unassigned_jobs=unassigned_explanations,
            metrics=sched_result.metrics,
        )

    def get_current_schedule(self) -> ScheduleCurrentResponse:
        """
        Retrieves the current operational schedule from the database,
        reflecting all saved assignments and pending/unassigned jobs with feasibility explanations.
        """
        as_of = self.get_clock()
        assignments = self.db.query(Assignment).order_by(Assignment.start_time.asc()).all()
        jobs_map = {j.id: j for j in self.db.query(Job).all()}
        techs_map = {t.id: t for t in self.db.query(Technician).all()}

        structured_assignments: List[ScheduleAssignmentItem] = []
        assigned_tech_ids = set()

        for a in assignments:
            assigned_tech_ids.add(a.technician_id)
            job = jobs_map.get(a.job_id)
            tech = techs_map.get(a.technician_id)
            dist_km = 0.0
            travel_mins = 0.0
            if job and tech:
                dist_km = haversine_distance(tech.home_lat, tech.home_lng, job.lat, job.lng)
                travel_mins = calculate_travel_minutes(dist_km)

            structured_assignments.append(
                ScheduleAssignmentItem(
                    assignment_id=a.id,
                    job_id=a.job_id,
                    technician_id=a.technician_id,
                    technician_name=tech.name if tech else a.technician_id,
                    job_title=job.title if job else None,
                    customer_name=job.customer_name if job else None,
                    zone_id=job.zone_id if job else None,
                    priority=job.priority if job else None,
                    priority_label=job.priority_label if job else None,
                    start_time=a.start_time,
                    end_time=a.end_time,
                    duration_minutes=int((a.end_time - a.start_time).total_seconds() / 60),
                    travel_time_minutes=round(travel_mins, 2),
                    distance_km=round(dist_km, 2),
                    status=a.status,
                    is_existing=a.is_existing,
                )
            )

        # Unassigned jobs
        assigned_job_ids = {a.job_id for a in assignments}
        unassigned_jobs = [
            j for j in jobs_map.values()
            if j.id not in assigned_job_ids and j.status in ["pending", "unassigned"]
        ]

        # Feasibility explanations for unassigned jobs
        unassigned_explanations: List[UnassignedJobExplanation] = []
        for job in unassigned_jobs:
            feasibility = self.get_job_feasibility(job.id, as_of=as_of)
            unassigned_explanations.append(
                UnassignedJobExplanation(
                    job_id=job.id,
                    title=job.title,
                    customer_name=job.customer_name,
                    zone_id=job.zone_id,
                    priority=job.priority,
                    priority_label=job.priority_label,
                    duration_minutes=job.duration_minutes,
                    classification=feasibility.classification,
                    primary_category=feasibility.primary_category,
                    rejection_summary=feasibility.rejection_summary,
                    actionable_recommendation=feasibility.actionable_recommendation,
                    required_skills=job.required_skills or [],
                    required_equipment=job.required_equipment or [],
                )
            )

        return ScheduleCurrentResponse(
            as_of=as_of,
            total_jobs=len(jobs_map),
            assigned_count=len(structured_assignments),
            unassigned_count=len(unassigned_explanations),
            technicians_count=len(techs_map),
            technicians_utilized=len(assigned_tech_ids),
            assignments=structured_assignments,
            unassigned_jobs=unassigned_explanations,
            metrics={
                "locked_existing_assignments": sum(1 for a in assignments if a.is_existing),
                "scheduled_assignments": sum(1 for a in assignments if not a.is_existing),
            },
        )

    def get_job_assignment(self, job_id: str) -> JobAssignmentResponse:
        """
        Retrieves assignment details for a specific job, or feasibility diagnostic if unassigned.
        """
        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found.")

        assign = self.db.query(Assignment).filter_by(job_id=job_id).first()
        if assign:
            tech = self.db.query(Technician).filter_by(id=assign.technician_id).first()
            dist_km = 0.0
            travel_mins = 0.0
            if tech:
                dist_km = haversine_distance(tech.home_lat, tech.home_lng, job.lat, job.lng)
                travel_mins = calculate_travel_minutes(dist_km)

            item = ScheduleAssignmentItem(
                assignment_id=assign.id,
                job_id=assign.job_id,
                technician_id=assign.technician_id,
                technician_name=tech.name if tech else assign.technician_id,
                job_title=job.title,
                customer_name=job.customer_name,
                zone_id=job.zone_id,
                priority=job.priority,
                priority_label=job.priority_label,
                start_time=assign.start_time,
                end_time=assign.end_time,
                duration_minutes=int((assign.end_time - assign.start_time).total_seconds() / 60),
                travel_time_minutes=round(travel_mins, 2),
                distance_km=round(dist_km, 2),
                status=assign.status,
                is_existing=assign.is_existing,
            )
            return JobAssignmentResponse(
                job_id=job.id,
                is_assigned=True,
                status=job.status,
                assignment=item,
            )

        # Unassigned: retrieve feasibility
        feasibility = self.get_job_feasibility(job_id)
        return JobAssignmentResponse(
            job_id=job.id,
            is_assigned=False,
            status=job.status,
            feasibility=feasibility,
        )

    def get_technician_schedule(self, technician_id: str) -> TechnicianScheduleResponse:
        """
        Retrieves the complete itinerary and sequential schedule for a technician,
        including Haversine travel times and distances between consecutive stops.
        """
        tech = self.db.query(Technician).filter_by(id=technician_id).first()
        if not tech:
            raise ValueError(f"Technician with ID '{technician_id}' not found.")

        assignments = self.db.query(Assignment).filter_by(technician_id=technician_id).order_by(Assignment.start_time.asc()).all()
        jobs_map = {j.id: j for j in self.db.query(Job).all()}

        itinerary: List[TechnicianItineraryItem] = []
        prev_lat = tech.home_lat
        prev_lng = tech.home_lng
        total_work_mins = 0
        total_travel_mins = 0.0

        for a in assignments:
            job = jobs_map.get(a.job_id)
            if not job:
                continue

            dist_km = haversine_distance(prev_lat, prev_lng, job.lat, job.lng)
            travel_mins = calculate_travel_minutes(dist_km)
            duration_mins = int((a.end_time - a.start_time).total_seconds() / 60)

            total_work_mins += duration_mins
            total_travel_mins += travel_mins

            itinerary.append(
                TechnicianItineraryItem(
                    assignment_id=a.id,
                    job_id=job.id,
                    job_title=job.title,
                    customer_name=job.customer_name,
                    zone_id=job.zone_id,
                    lat=job.lat,
                    lng=job.lng,
                    start_time=a.start_time,
                    end_time=a.end_time,
                    duration_minutes=duration_mins,
                    travel_from_previous_minutes=round(travel_mins, 2),
                    distance_from_previous_km=round(dist_km, 2),
                    status=a.status,
                    is_existing=a.is_existing,
                )
            )

            prev_lat = job.lat
            prev_lng = job.lng

        return TechnicianScheduleResponse(
            technician_id=tech.id,
            technician_name=tech.name,
            home_zone_id=tech.home_zone_id,
            home_lat=tech.home_lat,
            home_lng=tech.home_lng,
            eligible_zones=tech.eligible_zones or [],
            skills=tech.skills or [],
            equipment=tech.equipment or [],
            total_assigned_jobs=len(itinerary),
            total_working_minutes=total_work_mins,
            total_travel_minutes=round(total_travel_mins, 2),
            itinerary=itinerary,
        )

    def reset_schedule_to_baseline(self) -> Dict[str, Any]:
        """
        Clears all non-existing generated assignments and reverts modified jobs back to pending,
        strictly preserving the 7 seeded existing assignments.
        """
        existing_records = self.db.query(Assignment).filter(
            (Assignment.is_existing == True) | (Assignment.status.in_(["completed", "in_progress"]))
        ).all()
        protected_job_ids = {a.job_id for a in existing_records}

        deleted_count = self.db.query(Assignment).filter_by(is_existing=False).delete()

        reverted_jobs = self.db.query(Job).filter(
            ~Job.id.in_(protected_job_ids),
            Job.status == "assigned"
        ).all()
        for j in reverted_jobs:
            j.status = "pending"
            j.assigned_technician_id = None
            j.scheduled_start = None
            j.scheduled_end = None

        self.db.commit()

        return {
            "deleted_assignments": deleted_count,
            "reverted_jobs": len(reverted_jobs),
            "preserved_existing_assignments": len(existing_records),
        }

    def get_schedule_score(
        self,
        weights: Optional[ObjectiveWeightsConfig] = None,
        as_of: Optional[datetime] = None,
        respect_existing_assignments: bool = True,
    ) -> ScheduleScoreResult:
        """
        Evaluates the objective score and feasibility of the current schedule in the database.
        """
        from app.scheduling.scoring import evaluate_schedule_score

        as_of_dt = as_of or self.get_clock()
        inputs = self.load_inputs(
            config=SchedulingRunConfig(
                as_of=as_of_dt,
                respect_existing_assignments=respect_existing_assignments,
            )
        )

        db_assignments = self.db.query(Assignment).all()
        jobs = self.db.query(Job).all()
        technicians = self.db.query(Technician).all()

        return evaluate_schedule_score(
            jobs=jobs,
            technicians=technicians,
            assignments=db_assignments,
            baseline_assignments=inputs.existing_assignments,
            weights=weights,
            as_of=as_of_dt,
        )

    # =========================================================================
    # PHASE 24 – Priority-Aware Optimisation & Conflict Arbitration
    # =========================================================================

    def get_job_priority_profile(self, job_id: str) -> JobPriorityProfile:
        """
        Calculates the multi-criteria priority, technician scarcity, and window tightness profile for a job.
        """
        from app.scheduling.priority import calculate_job_priority_profile

        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        technicians = self.db.query(Technician).all()
        job_resp = JobResponse.model_validate(job)
        tech_resps = [TechnicianResponse.model_validate(t) for t in technicians]

        return calculate_job_priority_profile(
            job=job_resp,
            technicians=tech_resps,
            unsupported_skills=self.get_unsupported_skills(),
        )

    def resolve_competing_jobs(self, job_id_a: str, job_id_b: str) -> CompetingJobResolution:
        """
        Deterministically arbitrates between two competing jobs using the documented 7-tier priority hierarchy.
        """
        from app.scheduling.priority import resolve_competing_jobs

        job_a = self.db.query(Job).filter_by(id=job_id_a).first()
        if not job_a:
            raise ValueError(f"Job {job_id_a} not found")

        job_b = self.db.query(Job).filter_by(id=job_id_b).first()
        if not job_b:
            raise ValueError(f"Job {job_id_b} not found")

        technicians = self.db.query(Technician).all()
        job_a_resp = JobResponse.model_validate(job_a)
        job_b_resp = JobResponse.model_validate(job_b)
        tech_resps = [TechnicianResponse.model_validate(t) for t in technicians]

        return resolve_competing_jobs(
            job_a=job_a_resp,
            job_b=job_b_resp,
            technicians=tech_resps,
            unsupported_skills=self.get_unsupported_skills(),
        )

    def get_prioritized_pending_jobs(self) -> List[JobPriorityProfile]:
        """
        Returns all pending jobs ordered by the documented 7-tier priority and scarcity hierarchy.
        """
        from app.scheduling.priority import prioritize_jobs_with_scarcity, calculate_job_priority_profile

        inputs = self.load_inputs()
        sorted_jobs = prioritize_jobs_with_scarcity(
            jobs=inputs.pending_jobs,
            technicians=inputs.technicians,
            unsupported_skills=self.get_unsupported_skills(),
        )

        return [
            calculate_job_priority_profile(
                job=j,
                technicians=inputs.technicians,
                unsupported_skills=self.get_unsupported_skills(),
            )
            for j in sorted_jobs
        ]

    # =========================================================================
    # PHASE 25 – Travel-Time Optimisation & Geographical Route Refinement
    # =========================================================================

    def optimize_travel(
        self,
        persist: bool = False,
        run_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> TravelOptimizationResult:
        """
        Executes travel-time schedule optimization:
        1. Evaluates baseline initial schedule.
        2. Applies 2-opt route re-sequencing per shift date to eliminate back-and-forth travel and zone switching.
        3. Strictly preserves all hard operational constraints (zero violations).
        4. Optionally persists optimized schedules to PostgreSQL.
        """
        from app.scheduling.travel_opt import optimize_schedule_travel
        from app.scheduling.algorithm import run_deterministic_initial_scheduler

        as_of_dt = as_of or self.get_clock()
        inputs = self.load_inputs(config=SchedulingRunConfig(as_of=as_of_dt))

        # Check existing assignments in DB
        db_assignments = self.db.query(Assignment).all()
        if len(db_assignments) <= 7:
            # Generate initial assignments first
            init_res = run_deterministic_initial_scheduler(
                inputs=inputs,
                unsupported_skills=self.get_unsupported_skills(),
            )
            initial_plans = init_res.assignments
        else:
            # Load active plans from DB
            initial_plans = []
            for a in db_assignments:
                job = self.db.query(Job).filter_by(id=a.job_id).first()
                initial_plans.append(
                    AssignedJobPlan(
                        job_id=a.job_id,
                        technician_id=a.technician_id,
                        scheduled_start=a.start_time,
                        scheduled_end=a.end_time,
                        travel_time_minutes=0.0,
                        is_existing=a.is_existing,
                        status=a.status,
                        details={
                            "job_title": job.title if job else "",
                            "zone_id": job.zone_id if job else None,
                        },
                    )
                )

        jobs_all = [JobResponse.model_validate(j) for j in self.db.query(Job).all()]
        technicians_all = [TechnicianResponse.model_validate(t) for t in self.db.query(Technician).all()]

        result = optimize_schedule_travel(
            initial_assignments=initial_plans,
            technicians=technicians_all,
            jobs=jobs_all,
            baseline_assignments=inputs.existing_assignments,
            as_of=as_of_dt,
            run_id=run_id or generate_run_id("RUN-OPT"),
        )

        if persist:
            # Persist optimized assignments
            for p in result.assignments:
                if p.is_existing:
                    continue
                db_a = self.db.query(Assignment).filter_by(job_id=p.job_id).first()
                if not db_a:
                    db_a = Assignment(
                        id=f"ASN-{uuid.uuid4().hex[:8].upper()}",
                        job_id=p.job_id,
                        technician_id=p.technician_id,
                        start_time=p.scheduled_start,
                        end_time=p.scheduled_end,
                        status="scheduled",
                        is_existing=False,
                    )
                    self.db.add(db_a)
                else:
                    db_a.technician_id = p.technician_id
                    db_a.start_time = p.scheduled_start
                    db_a.end_time = p.scheduled_end

                # Update job
                job_rec = self.db.query(Job).filter_by(id=p.job_id).first()
                if job_rec and not (job_rec.status in ["completed", "in_progress"]):
                    job_rec.status = "assigned"
                    job_rec.assigned_technician_id = p.technician_id
                    job_rec.scheduled_start = p.scheduled_start
                    job_rec.scheduled_end = p.scheduled_end

            self.db.commit()
            result.persisted = True

        return result

    def get_travel_metrics(self) -> Dict[str, Any]:
        """
        Calculates and returns current leg-by-leg travel summaries and fleet transit metrics.
        """
        from app.scheduling.travel_opt import calculate_fleet_travel_breakdown

        db_assignments = self.db.query(Assignment).all()
        if len(db_assignments) <= 7:
            # Generate initial schedule to compute metrics
            inputs = self.load_inputs()
            from app.scheduling.algorithm import run_deterministic_initial_scheduler
            init_res = run_deterministic_initial_scheduler(
                inputs=inputs,
                unsupported_skills=self.get_unsupported_skills(),
            )
            plans = init_res.assignments
        else:
            plans = []
            for a in db_assignments:
                plans.append(
                    AssignedJobPlan(
                        job_id=a.job_id,
                        technician_id=a.technician_id,
                        scheduled_start=a.start_time,
                        scheduled_end=a.end_time,
                        travel_time_minutes=0.0,
                        is_existing=a.is_existing,
                        status=a.status,
                    )
                )

        jobs_all = {j.id: JobResponse.model_validate(j) for j in self.db.query(Job).all()}
        technicians_all = [TechnicianResponse.model_validate(t) for t in self.db.query(Technician).all()]

        summaries, metrics = calculate_fleet_travel_breakdown(
            technicians=technicians_all,
            assignments=plans,
            jobs_lookup=jobs_all,
        )

        return {
            "fleet_metrics": metrics,
            "technician_travel": summaries,
        }

    # =========================================================================
    # PHASE 26 – SLA Optimisation & Deadline Performance Engine
    # =========================================================================

    def get_sla_metrics(
        self,
        lateness_weight: float = 2.0,
        at_risk_threshold_minutes: int = 30,
    ) -> Dict[str, Any]:
        """
        Calculates and returns fleet-wide SLA timeliness metrics and granular job status.
        """
        from app.scheduling.sla_opt import calculate_fleet_sla_metrics
        from app.scheduling.algorithm import run_deterministic_initial_scheduler

        db_assignments = self.db.query(Assignment).all()
        if len(db_assignments) <= 7:
            inputs = self.load_inputs()
            init_res = run_deterministic_initial_scheduler(
                inputs=inputs,
                unsupported_skills=self.get_unsupported_skills(),
            )
            plans = init_res.assignments
        else:
            plans = []
            for a in db_assignments:
                job = self.db.query(Job).filter_by(id=a.job_id).first()
                plans.append(
                    AssignedJobPlan(
                        job_id=a.job_id,
                        technician_id=a.technician_id,
                        scheduled_start=a.start_time,
                        scheduled_end=a.end_time,
                        travel_time_minutes=0.0,
                        is_existing=a.is_existing,
                        status=a.status,
                        details={"job_title": job.title if job else ""},
                    )
                )

        jobs_all = [JobResponse.model_validate(j) for j in self.db.query(Job).all()]
        details, metrics = calculate_fleet_sla_metrics(
            jobs=jobs_all,
            assignments=plans,
            as_of=self.get_clock(),
            lateness_weight=lateness_weight,
            at_risk_threshold_minutes=at_risk_threshold_minutes,
        )

        return {
            "fleet_metrics": metrics,
            "job_sla_details": details,
        }

    def get_job_sla_detail(
        self,
        job_id: str,
        lateness_weight: float = 2.0,
        at_risk_threshold_minutes: int = 30,
    ) -> JobSLADetail:
        """
        Retrieves SLA timeliness status and delay metrics for an individual job.
        """
        from app.scheduling.sla_opt import calculate_job_sla_detail

        job = self.db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        assignment = self.db.query(Assignment).filter_by(job_id=job_id).first()
        plan = None
        if assignment:
            plan = AssignedJobPlan(
                job_id=assignment.job_id,
                technician_id=assignment.technician_id,
                scheduled_start=assignment.start_time,
                scheduled_end=assignment.end_time,
                travel_time_minutes=0.0,
                is_existing=assignment.is_existing,
                status=assignment.status,
            )
        else:
            db_assignments = self.db.query(Assignment).all()
            if len(db_assignments) <= 7:
                inputs = self.load_inputs()
                init_res = run_deterministic_initial_scheduler(
                    inputs=inputs,
                    unsupported_skills=self.get_unsupported_skills(),
                )
                plan = next((p for p in init_res.assignments if p.job_id == job_id), None)

        return calculate_job_sla_detail(
            job=JobResponse.model_validate(job),
            assignment=plan,
            as_of=self.get_clock(),
            lateness_weight=lateness_weight,
            at_risk_threshold_minutes=at_risk_threshold_minutes,
        )

    def resolve_competing_sla_deadlines(
        self,
        job_id_a: str,
        job_id_b: str,
    ) -> CompetingSLAResolution:
        """
        Deterministically arbitrates between two competing jobs with approaching SLA targets.
        """
        from app.scheduling.sla_opt import resolve_competing_sla_deadlines

        job_a = self.db.query(Job).filter_by(id=job_id_a).first()
        if not job_a:
            raise ValueError(f"Job {job_id_a} not found")

        job_b = self.db.query(Job).filter_by(id=job_id_b).first()
        if not job_b:
            raise ValueError(f"Job {job_id_b} not found")

        return resolve_competing_sla_deadlines(
            job_a=JobResponse.model_validate(job_a),
            job_b=JobResponse.model_validate(job_b),
            as_of=self.get_clock(),
        )

    def optimize_sla(
        self,
        lateness_weight: float = 2.0,
        at_risk_threshold_minutes: int = 30,
        persist: bool = False,
        run_id: Optional[str] = None,
    ) -> SLAOptimizationResult:
        """
        Executes SLA schedule optimization pass to mitigate lateness and protect at-risk jobs.
        """
        from app.scheduling.sla_opt import optimize_schedule_sla
        from app.scheduling.algorithm import run_deterministic_initial_scheduler

        as_of = self.get_clock()
        inputs = self.load_inputs(config=SchedulingRunConfig(as_of=as_of))

        db_assignments = self.db.query(Assignment).all()
        if len(db_assignments) <= 7:
            init_res = run_deterministic_initial_scheduler(
                inputs=inputs,
                unsupported_skills=self.get_unsupported_skills(),
            )
            plans = init_res.assignments
        else:
            plans = []
            for a in db_assignments:
                job = self.db.query(Job).filter_by(id=a.job_id).first()
                plans.append(
                    AssignedJobPlan(
                        job_id=a.job_id,
                        technician_id=a.technician_id,
                        scheduled_start=a.start_time,
                        scheduled_end=a.end_time,
                        travel_time_minutes=0.0,
                        is_existing=a.is_existing,
                        status=a.status,
                        details={"job_title": job.title if job else ""},
                    )
                )

        jobs_all = [JobResponse.model_validate(j) for j in self.db.query(Job).all()]
        technicians_all = [TechnicianResponse.model_validate(t) for t in self.db.query(Technician).all()]

        result = optimize_schedule_sla(
            initial_assignments=plans,
            technicians=technicians_all,
            jobs=jobs_all,
            as_of=as_of,
            lateness_weight=lateness_weight,
            at_risk_threshold_minutes=at_risk_threshold_minutes,
            run_id=run_id or generate_run_id("RUN-OPT-SLA"),
        )

        if persist:
            for p in result.assignments:
                if p.is_existing:
                    continue
                db_a = self.db.query(Assignment).filter_by(job_id=p.job_id).first()
                if not db_a:
                    db_a = Assignment(
                        id=f"ASN-{uuid.uuid4().hex[:8].upper()}",
                        job_id=p.job_id,
                        technician_id=p.technician_id,
                        start_time=p.scheduled_start,
                        end_time=p.scheduled_end,
                        status="scheduled",
                        is_existing=False,
                    )
                    self.db.add(db_a)
                else:
                    db_a.start_time = p.scheduled_start
                    db_a.end_time = p.scheduled_end

                job_rec = self.db.query(Job).filter_by(id=p.job_id).first()
                if job_rec and not (job_rec.status in ["completed", "in_progress"]):
                    job_rec.scheduled_start = p.scheduled_start
                    job_rec.scheduled_end = p.scheduled_end

            self.db.commit()
            result.persisted = True

        return result






