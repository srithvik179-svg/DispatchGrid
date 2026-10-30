from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import Job
from app.schemas.job import (
    JobCreate,
    JobUpdate,
    JobCancelRequest,
    JobResponse,
    JobStateHistoryResponse,
)
from app.services.job_service import (
    create_job,
    update_job,
    cancel_job,
    get_job_state_history,
    JobNotFoundError,
    DuplicateJobIdError,
    DuplicateIdempotencyKeyError,
    InvalidZoneError,
    InvalidStateTransitionError,
    ProtectedJobModificationError,
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
    try:
        job = create_job(db=db, job_in=job_in)
        return JobResponse.model_validate(job)
    except (DuplicateJobIdError, DuplicateIdempotencyKeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except (InvalidZoneError, ValueError) as e:
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
    search: Optional[str] = Query(None, description="Search term for ID, title, or customer"),
    status_filter: Optional[str] = Query(None, alias="status"),
    priority_filter: Optional[int] = Query(None, alias="priority"),
    zone_filter: Optional[str] = Query(None, alias="zone_id"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[JobResponse]:
    query = db.query(Job)
    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            (Job.id.ilike(search_pattern))
            | (Job.title.ilike(search_pattern))
            | (Job.customer_name.ilike(search_pattern))
        )
    if status_filter:
        query = query.filter(Job.status == status_filter)
    if priority_filter is not None:
        query = query.filter(Job.priority == priority_filter)
    if zone_filter:
        query = query.filter(Job.zone_id == zone_filter)

    jobs = query.order_by(Job.id.asc()).offset(offset).limit(limit).all()
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
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found",
        )
    return JobResponse.model_validate(job)


@router.patch(
    "/jobs/{job_id}",
    response_model=JobResponse,
    tags=["Jobs"],
    summary="Update a service job or trigger permitted state transition",
)
def update_existing_job(
    job_id: str,
    job_update: JobUpdate,
    db: Session = Depends(get_db),
) -> JobResponse:
    try:
        job = update_job(db=db, job_id=job_id, job_update=job_update)
        return JobResponse.model_validate(job)
    except JobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidStateTransitionError, ProtectedJobModificationError, InvalidZoneError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobResponse,
    tags=["Jobs"],
    summary="Cancel a service job",
)
def cancel_existing_job(
    job_id: str,
    cancel_in: Optional[JobCancelRequest] = None,
    db: Session = Depends(get_db),
) -> JobResponse:
    reason = cancel_in.reason if cancel_in else "Cancelled by operator"
    try:
        job = cancel_job(db=db, job_id=job_id, reason=reason)
        return JobResponse.model_validate(job)
    except JobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in '{e.from_status}' state: {str(e)}",
        )


@router.get(
    "/jobs/{job_id}/history",
    response_model=List[JobStateHistoryResponse],
    tags=["Jobs"],
    summary="Get job state change history",
)
def get_job_history(
    job_id: str,
    db: Session = Depends(get_db),
) -> List[JobStateHistoryResponse]:
    try:
        history = get_job_state_history(db=db, job_id=job_id)
        return [JobStateHistoryResponse.model_validate(h) for h in history]
    except JobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
