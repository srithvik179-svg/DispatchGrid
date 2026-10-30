import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict
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
)
from app.scheduling.loader import (
    get_simulation_clock,
    get_planning_horizon,
    load_scheduling_inputs,
    load_pending_jobs,
    load_eligible_technicians,
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
                "mode": config.mode if config else "baseline",
                "ready_for_optimization": True,
            },
            created_at=datetime.now(timezone.utc),
        )


        return result
