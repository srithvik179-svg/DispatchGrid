from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobResponse
from app.services.job_service import (
    create_job,
    DuplicateJobIdError,
    DuplicateIdempotencyKeyError,
    InvalidZoneError,
)

router = APIRouter()


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Jobs"],
    summary="Create a new service job",
)
def create_new_job(
    job_in: JobCreate,
    db: Session = Depends(get_db),
) -> JobResponse:
    """
    Creates a new service job with rigorous constraint validation:
    - Customer name and job title must not be empty.
    - Priority must be between 1 (urgent) and 4 (low).
    - Duration must be positive.
    - Time window start must be earlier than window end and duration must fit in window.
    - SLA deadline cannot be earlier than window start.
    - Idempotency key and unique ID conflicts are rejected with HTTP 409 Conflict.
    - Non-existent zones are rejected with HTTP 400 Bad Request.
    """
    try:
        job = create_job(db=db, job_in=job_in)
        return JobResponse.model_validate(job)
    except DuplicateJobIdError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except DuplicateIdempotencyKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except InvalidZoneError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/jobs",
    response_model=List[JobResponse],
    tags=["Jobs"],
    summary="List all service jobs",
)
def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    priority_filter: Optional[int] = Query(None, alias="priority"),
    zone_filter: Optional[str] = Query(None, alias="zone_id"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[JobResponse]:
    """Lists service jobs with optional status, priority, and zone filtering."""
    query = db.query(Job)
    if status_filter:
        query = query.filter(Job.status == status_filter)
    if priority_filter is not None:
        query = query.filter(Job.priority == priority_filter)
    if zone_filter:
        query = query.filter(Job.zone_id == zone_filter)

    jobs = query.order_by(Job.created_at.asc(), Job.id.asc()).offset(offset).limit(limit).all()
    return [JobResponse.model_validate(j) for j in jobs]


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    tags=["Jobs"],
    summary="Get job by ID",
)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobResponse:
    """Retrieves a specific service job by its ID."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found",
        )
    return JobResponse.model_validate(job)
