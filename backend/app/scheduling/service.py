import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.scheduling.schemas import (
    SchedulingRunConfig,
    SchedulingInput,
    SchedulingResult,
    AssignedJobPlan,
)
from app.scheduling.loader import (
    get_simulation_clock,
    get_planning_horizon,
    load_scheduling_inputs,
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

        # 3. Assemble standardized SchedulingResult
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
                "mode": config.mode if config else "baseline",
                "ready_for_optimization": True,
            },
            created_at=datetime.now(timezone.utc),
        )

        return result
