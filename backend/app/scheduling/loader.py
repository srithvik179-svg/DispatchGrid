import json
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload

from app.models.job import Job
from app.models.technician import Technician
from app.models.assignment import Assignment
from app.models.system import SystemMetadata
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.schemas.assignment import AssignmentSummary
from app.scheduling.schemas import SchedulingRunConfig, SchedulingInput

# Authoritative simulation constants for fallback
DEFAULT_AS_OF = datetime(2026, 11, 2, 10, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
DEFAULT_HORIZON_START = datetime(2026, 11, 2, 0, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
DEFAULT_HORIZON_END = datetime(2026, 11, 4, 0, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


def parse_iso_datetime(val: Any, default: datetime) -> datetime:
    """Safely parse an ISO datetime string or return datetime/default."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str) and val.strip():
        s = val.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except Exception:
            pass
    return default


def get_simulation_clock(db: Session, override: Optional[datetime] = None) -> datetime:
    """
    Retrieve authoritative simulation reference clock ('as_of') from system_metadata.
    Falls back to authoritative default (2026-11-02T10:00:00+05:30).
    """
    if override:
        return override

    record = db.query(SystemMetadata).filter_by(key="as_of").first()
    if record and record.value:
        return parse_iso_datetime(record.value, DEFAULT_AS_OF)

    return DEFAULT_AS_OF


def get_planning_horizon(
    db: Session,
    start_override: Optional[datetime] = None,
    end_override: Optional[datetime] = None,
) -> Tuple[datetime, datetime]:
    """
    Retrieve the planning horizon (start, end) from system_metadata or defaults.
    """
    start_dt = start_override
    end_dt = end_override

    if not start_dt or not end_dt:
        record = db.query(SystemMetadata).filter_by(key="planning_horizon").first()
        if record and record.value:
            try:
                data = json.loads(record.value)
                if not start_dt and "start" in data:
                    start_dt = parse_iso_datetime(data["start"], DEFAULT_HORIZON_START)
                if not end_dt and "end" in data:
                    end_dt = parse_iso_datetime(data["end"], DEFAULT_HORIZON_END)
            except Exception:
                pass

    return (start_dt or DEFAULT_HORIZON_START, end_dt or DEFAULT_HORIZON_END)


def load_system_metadata(db: Session) -> Dict[str, Any]:
    """Load system-level metadata, constraints, and configuration dictionaries."""
    records = db.query(SystemMetadata).all()
    meta_dict: Dict[str, Any] = {}
    for r in records:
        try:
            meta_dict[r.key] = json.loads(r.value)
        except Exception:
            meta_dict[r.key] = r.value
    return meta_dict


def load_pending_jobs(db: Session) -> List[Job]:
    """
    Query all pending or unassigned jobs awaiting schedule dispatch.
    Ordered by priority (1=urgent first), then earliest time_window_start, then ID.
    """
    return (
        db.query(Job)
        .filter(Job.status.in_(["pending", "unassigned"]))
        .order_by(Job.priority.asc(), Job.time_window_start.asc(), Job.id.asc())
        .all()
    )


def load_eligible_technicians(db: Session) -> List[Technician]:
    """Query all available technicians from PostgreSQL ordered by ID."""
    return db.query(Technician).order_by(Technician.id.asc()).all()


def load_existing_assignments(db: Session) -> List[Assignment]:
    """
    Query all pre-existing assignments from PostgreSQL.
    Eagerly loads related Job and Technician records.
    """
    return (
        db.query(Assignment)
        .options(joinedload(Assignment.job), joinedload(Assignment.technician))
        .order_by(Assignment.start_time.asc(), Assignment.id.asc())
        .all()
    )


def load_scheduling_inputs(
    db: Session,
    run_id: str,
    config: Optional[SchedulingRunConfig] = None,
) -> SchedulingInput:
    """
    Loads all inputs required for a scheduling run from the database into a structured SchedulingInput.
    Does NOT alter any database state or assignments.
    """
    as_of = get_simulation_clock(db, override=config.as_of if config else None)
    horizon_start, horizon_end = get_planning_horizon(
        db,
        start_override=config.horizon_start if config else None,
        end_override=config.horizon_end if config else None,
    )

    pending_jobs_orm = load_pending_jobs(db)
    technicians_orm = load_eligible_technicians(db)
    assignments_orm = load_existing_assignments(db)
    metadata = load_system_metadata(db)

    pending_jobs = [JobResponse.model_validate(j) for j in pending_jobs_orm]
    technicians = [TechnicianResponse.model_validate(t) for t in technicians_orm]

    existing_assignments = [
        AssignmentSummary(
            id=a.id,
            job_id=a.job_id,
            technician_id=a.technician_id,
            start_time=a.start_time,
            end_time=a.end_time,
            actual_start=a.actual_start,
            status=a.status,
            is_existing=a.is_existing,
            job_title=a.job.title if a.job else None,
            technician_name=a.technician.name if a.technician else None,
        )
        for a in assignments_orm
    ]

    return SchedulingInput(
        run_id=run_id,
        as_of=as_of,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        pending_jobs_count=len(pending_jobs),
        technicians_count=len(technicians),
        existing_assignments_count=len(existing_assignments),
        pending_jobs=pending_jobs,
        technicians=technicians,
        existing_assignments=existing_assignments,
        metadata=metadata,
    )
