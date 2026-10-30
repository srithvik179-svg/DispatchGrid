import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session


from app.models.job import Job
from app.models.technician import Technician
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

