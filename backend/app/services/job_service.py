import math
import re
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.zone import Zone
from app.models.assignment import Assignment
from app.models.job_history import JobStateHistory
from app.models.system import SystemMetadata
from app.schemas.job import (
    JobCreate,
    JobUpdate,
    PRIORITY_MAP,
    VALID_TRANSITIONS,
    VALID_STATUSES,
)


class JobServiceError(Exception):
    """Base exception for job service operations."""
    pass


class JobNotFoundError(JobServiceError):
    def __init__(self, job_id: str):
        super().__init__(f"Job with ID '{job_id}' not found")
        self.job_id = job_id


class DuplicateJobIdError(JobServiceError):
    def __init__(self, job_id: str):
        super().__init__(f"Job with ID '{job_id}' already exists")
        self.job_id = job_id


class DuplicateIdempotencyKeyError(JobServiceError):
    def __init__(self, key: str, existing_job_id: str):
        super().__init__(f"Duplicate request: Job with idempotency key '{key}' already exists ({existing_job_id})")
        self.key = key
        self.existing_job_id = existing_job_id


class InvalidZoneError(JobServiceError):
    def __init__(self, zone_id: str):
        super().__init__(f"Service zone '{zone_id}' is invalid or does not exist")
        self.zone_id = zone_id


class InvalidStateTransitionError(JobServiceError):
    def __init__(self, from_status: str, to_status: str):
        super().__init__(
            f"Invalid state transition: Cannot move job from '{from_status}' to '{to_status}'"
        )
        self.from_status = from_status
        self.to_status = to_status


class ProtectedJobModificationError(JobServiceError):
    def __init__(self, status: str):
        super().__init__(f"Cannot modify protected job in terminal state '{status}'")
        self.status = status


def generate_next_job_id(db: Session) -> str:
    all_job_ids = db.query(Job.id).all()
    max_num = 0
    for (jid,) in all_job_ids:
        match = re.search(r"^JOB-(\d+)$", jid)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num

    next_num = max_num + 1
    return f"JOB-{next_num:03d}"


def find_nearest_zone(db: Session, lat: float, lng: float) -> Optional[str]:
    zones = db.query(Zone).all()
    if not zones:
        return None

    best_zone = None
    min_dist = float("inf")
    for z in zones:
        dist = math.hypot(z.lat - lat, z.lng - lng)
        if dist < min_dist:
            min_dist = dist
            best_zone = z.id
    return best_zone


def validate_state_transition(from_status: str, to_status: str) -> None:
    """Validates permitted job state transitions according to lifecycle state machine."""
    if to_status not in VALID_STATUSES:
        raise ValueError(f"Unknown target status '{to_status}'")

    if from_status == to_status:
        return  # No-op

    allowed = VALID_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidStateTransitionError(from_status, to_status)


def create_job(db: Session, job_in: JobCreate) -> Job:
    if job_in.idempotency_key:
        existing_by_key = db.query(Job).filter_by(idempotency_key=job_in.idempotency_key).first()
        if existing_by_key:
            raise DuplicateIdempotencyKeyError(job_in.idempotency_key, existing_by_key.id)

    if job_in.id:
        existing_by_id = db.query(Job).filter_by(id=job_in.id).first()
        if existing_by_id:
            raise DuplicateJobIdError(job_in.id)
        job_id = job_in.id
    else:
        job_id = generate_next_job_id(db)

    zone_id = job_in.zone_id
    if zone_id:
        zone_exists = db.query(Zone).filter_by(id=zone_id).first()
        if not zone_exists:
            raise InvalidZoneError(zone_id)
    else:
        zone_id = find_nearest_zone(db, job_in.lat, job_in.lng)

    clock_rec = db.query(SystemMetadata).filter_by(key="as_of").first()
    if clock_rec:
        try:
            created_at = datetime.fromisoformat(clock_rec.value)
        except Exception:
            created_at = datetime.now(timezone.utc)
    else:
        created_at = datetime.now(timezone.utc)

    job = Job(
        id=job_id,
        idempotency_key=job_in.idempotency_key,
        customer_name=job_in.customer_name,
        title=job_in.title,
        zone_id=zone_id,
        lat=job_in.lat,
        lng=job_in.lng,
        address=job_in.address,
        priority=job_in.priority,
        priority_label=PRIORITY_MAP[job_in.priority],
        duration_minutes=job_in.duration_minutes,
        required_skills=job_in.required_skills,
        required_equipment=job_in.required_equipment,
        time_window_start=job_in.time_window_start,
        time_window_end=job_in.time_window_end,
        sla_deadline=job_in.sla_deadline,
        status="pending",
        assigned_technician_id=None,
        scheduled_start=None,
        scheduled_end=None,
        created_at=created_at,
        tags=job_in.tags,
    )

    db.add(job)
    # Record initial creation state history
    history = JobStateHistory(
        job_id=job_id,
        from_status=None,
        to_status="pending",
        reason="Initial service job registration",
        changed_at=created_at,
    )
    db.add(history)

    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, job_id: str, job_update: JobUpdate) -> Job:
    """Updates a service job, enforcing state machine transitions and protecting completed work."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise JobNotFoundError(job_id)

    # Protection of completed or cancelled jobs
    if job.status in ("completed", "cancelled"):
        raise ProtectedJobModificationError(job.status)

    # 1. State Transition Check
    if job_update.status and job_update.status != job.status:
        validate_state_transition(job.status, job_update.status)
        old_status = job.status
        new_status = job_update.status

        # If transitioning to cancelled, release assignments
        if new_status == "cancelled":
            job.assigned_technician_id = None
            job.scheduled_start = None
            job.scheduled_end = None
            # Update any assignment record
            assigns = db.query(Assignment).filter_by(job_id=job.id).all()
            for a in assigns:
                a.status = "cancelled"

        job.status = new_status
        history = JobStateHistory(
            job_id=job.id,
            from_status=old_status,
            to_status=new_status,
            reason=job_update.reason or "Job status updated via API",
            changed_at=datetime.now(timezone.utc),
        )
        db.add(history)

    # 2. Update editable fields
    if job_update.title is not None:
        t = job_update.title.strip()
        if not t:
            raise ValueError("title cannot be empty")
        job.title = t

    if job_update.customer_name is not None:
        c = job_update.customer_name.strip()
        if not c:
            raise ValueError("customer_name cannot be empty")
        job.customer_name = c

    if job_update.priority is not None:
        job.priority = job_update.priority
        job.priority_label = PRIORITY_MAP[job_update.priority]

    if job_update.duration_minutes is not None:
        if job_update.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        job.duration_minutes = job_update.duration_minutes

    if job_update.zone_id is not None:
        zone = db.query(Zone).filter_by(id=job_update.zone_id).first()
        if not zone:
            raise InvalidZoneError(job_update.zone_id)
        job.zone_id = job_update.zone_id

    if job_update.lat is not None:
        job.lat = job_update.lat
    if job_update.lng is not None:
        job.lng = job_update.lng
    if job_update.address is not None:
        job.address = job_update.address

    if job_update.required_skills is not None:
        skills = [s.strip().lower() for s in job_update.required_skills if s.strip()]
        if not skills:
            raise ValueError("required_skills cannot be empty")
        job.required_skills = skills

    if job_update.required_equipment is not None:
        job.required_equipment = job_update.required_equipment

    # Validate timing consistency if updated
    start_time = job_update.time_window_start or job.time_window_start
    end_time = job_update.time_window_end or job.time_window_end
    duration = job_update.duration_minutes or job.duration_minutes

    if start_time >= end_time:
        raise ValueError("time_window_start must be strictly earlier than time_window_end")

    window_mins = (end_time - start_time).total_seconds() / 60.0
    if window_mins < duration:
        raise ValueError(f"Time window ({window_mins:.0f} mins) is shorter than duration ({duration} mins)")

    if job_update.time_window_start is not None:
        job.time_window_start = job_update.time_window_start
    if job_update.time_window_end is not None:
        job.time_window_end = job_update.time_window_end

    if job_update.sla_deadline is not None:
        if job_update.sla_deadline < start_time:
            raise ValueError("sla_deadline cannot be earlier than time_window_start")
        job.sla_deadline = job_update.sla_deadline

    db.commit()
    db.refresh(job)
    return job


def cancel_job(db: Session, job_id: str, reason: Optional[str] = None) -> Job:
    """Cancels a job, enforcing that completed or already cancelled jobs cannot be cancelled."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise JobNotFoundError(job_id)

    if job.status in ("completed", "cancelled"):
        raise InvalidStateTransitionError(job.status, "cancelled")

    validate_state_transition(job.status, "cancelled")
    old_status = job.status

    job.status = "cancelled"
    job.assigned_technician_id = None
    job.scheduled_start = None
    job.scheduled_end = None

    assigns = db.query(Assignment).filter_by(job_id=job.id).all()
    for a in assigns:
        a.status = "cancelled"

    history = JobStateHistory(
        job_id=job.id,
        from_status=old_status,
        to_status="cancelled",
        reason=reason or "Cancelled by operator",
        changed_at=datetime.now(timezone.utc),
    )
    db.add(history)

    db.commit()
    db.refresh(job)
    return job


def get_job_state_history(db: Session, job_id: str) -> List[JobStateHistory]:
    """Retrieves full chronological state change history for a job."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise JobNotFoundError(job_id)
    return db.query(JobStateHistory).filter_by(job_id=job_id).order_by(JobStateHistory.changed_at.asc()).all()
