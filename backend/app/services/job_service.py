import math
import re
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.job import Job
from app.models.zone import Zone
from app.models.system import SystemMetadata
from app.schemas.job import JobCreate, PRIORITY_MAP


class JobCreationError(Exception):
    """Base exception for job creation errors."""
    pass


class DuplicateJobIdError(JobCreationError):
    def __init__(self, job_id: str):
        super().__init__(f"Job with ID '{job_id}' already exists")
        self.job_id = job_id


class DuplicateIdempotencyKeyError(JobCreationError):
    def __init__(self, key: str, existing_job_id: str):
        super().__init__(f"Duplicate request: Job with idempotency key '{key}' already exists ({existing_job_id})")
        self.key = key
        self.existing_job_id = existing_job_id


class InvalidZoneError(JobCreationError):
    def __init__(self, zone_id: str):
        super().__init__(f"Service zone '{zone_id}' is invalid or does not exist")
        self.zone_id = zone_id


def generate_next_job_id(db: Session) -> str:
    """
    Deterministically generates the next sequential JOB-xxx ID based on existing records.
    Finds the maximum integer suffix among JOB-xxx records and increments it by 1.
    """
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
    """Finds the closest service zone using Euclidean distance to zone center coordinates."""
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


def create_job(db: Session, job_in: JobCreate) -> Job:
    """
    Creates a new service job with complete constraint validation,
    unique ID enforcement, idempotency checks, and persistent storage.
    """
    # 1. Check idempotency key if provided
    if job_in.idempotency_key:
        existing_by_key = db.query(Job).filter_by(idempotency_key=job_in.idempotency_key).first()
        if existing_by_key:
            raise DuplicateIdempotencyKeyError(job_in.idempotency_key, existing_by_key.id)

    # 2. Assign or validate Job ID
    if job_in.id:
        existing_by_id = db.query(Job).filter_by(id=job_in.id).first()
        if existing_by_id:
            raise DuplicateJobIdError(job_in.id)
        job_id = job_in.id
    else:
        job_id = generate_next_job_id(db)

    # 3. Validate or auto-resolve zone_id
    zone_id = job_in.zone_id
    if zone_id:
        zone_exists = db.query(Zone).filter_by(id=zone_id).first()
        if not zone_exists:
            raise InvalidZoneError(zone_id)
    else:
        zone_id = find_nearest_zone(db, job_in.lat, job_in.lng)

    # 4. Determine created_at timestamp
    clock_rec = db.query(SystemMetadata).filter_by(key="as_of").first()
    if clock_rec:
        try:
            created_at = datetime.fromisoformat(clock_rec.value)
        except Exception:
            created_at = datetime.now(timezone.utc)
    else:
        created_at = datetime.now(timezone.utc)

    # 5. Build and persist model
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
    db.commit()
    db.refresh(job)
    return job
