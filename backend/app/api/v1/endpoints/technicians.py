from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.technician import TechnicianCreate, TechnicianUpdate, TechnicianResponse
from app.services.technician_service import (
    create_technician,
    update_technician,
    get_technicians,
    get_technician_by_id,
    DuplicateTechnicianIdError,
    InvalidTechnicianDataError,
    TechnicianNotFoundError,
)

router = APIRouter()


@router.post(
    "/technicians",
    response_model=TechnicianResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Technicians"],
    summary="Register a new field technician",
)
def register_technician(
    technician_in: TechnicianCreate,
    db: Session = Depends(get_db),
) -> TechnicianResponse:
    """
    Register a new technician with skill certificates, onboard tools/equipment,
    home base location, eligible zones, shifts, and overtime policies.
    """
    try:
        technician = create_technician(db=db, payload=technician_in)
        return TechnicianResponse.model_validate(technician)
    except DuplicateTechnicianIdError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except (InvalidTechnicianDataError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/technicians",
    response_model=List[TechnicianResponse],
    status_code=status.HTTP_200_OK,
    tags=["Technicians"],
    summary="List all technicians with optional filtering",
)
def list_technicians(
    zone: Optional[str] = Query(None, description="Filter by operational or home zone ID (e.g. Z1)"),
    skill: Optional[str] = Query(None, description="Filter by required skill (e.g. electrical)"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Maximum records to return"),
    db: Session = Depends(get_db),
) -> List[TechnicianResponse]:
    """Retrieve technician fleet with optional filtering by zone and certified skill."""
    technicians = get_technicians(
        db=db,
        zone=zone,
        skill=skill,
        skip=skip,
        limit=limit,
    )
    return [TechnicianResponse.model_validate(t) for t in technicians]


@router.get(
    "/technicians/{technician_id}",
    response_model=TechnicianResponse,
    status_code=status.HTTP_200_OK,
    tags=["Technicians"],
    summary="Get technician by ID",
)
def retrieve_technician(
    technician_id: str,
    db: Session = Depends(get_db),
) -> TechnicianResponse:
    """Retrieve complete profile, shifts, and operational parameters for a single technician."""
    technician = get_technician_by_id(db=db, technician_id=technician_id)
    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Technician with ID '{technician_id}' not found",
        )
    return TechnicianResponse.model_validate(technician)


@router.patch(
    "/technicians/{technician_id}",
    response_model=TechnicianResponse,
    status_code=status.HTTP_200_OK,
    tags=["Technicians"],
    summary="Update technician profile and operational parameters",
)
def modify_technician(
    technician_id: str,
    payload: TechnicianUpdate,
    db: Session = Depends(get_db),
) -> TechnicianResponse:
    """Update profile attributes, certified skills, onboard equipment, shifts or overtime policy."""
    try:
        updated = update_technician(db=db, technician_id=technician_id, payload=payload)
        return TechnicianResponse.model_validate(updated)
    except TechnicianNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except (InvalidTechnicianDataError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
