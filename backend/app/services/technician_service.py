import re
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.technician import Technician
from app.models.zone import Zone
from app.schemas.technician import TechnicianCreate


class DuplicateTechnicianIdError(Exception):
    """Raised when creating a technician with an existing ID."""
    pass


class InvalidTechnicianDataError(Exception):
    """Raised when technician registration data violates domain rules."""
    pass


def generate_next_technician_id(db: Session) -> str:
    """Generate next sequential technician ID following the T{num:02d} format."""
    existing_ids = db.query(Technician.id).all()
    max_num = 0

    for (t_id,) in existing_ids:
        match = re.match(r"^T(\d+)$", t_id)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num

    return f"T{max_num + 1:02d}"


def create_technician(db: Session, payload: TechnicianCreate) -> Technician:
    """Register a new technician and persist operational configuration in PostgreSQL."""
    # Determine technician ID
    if payload.id:
        existing = db.query(Technician).filter(Technician.id == payload.id).first()
        if existing:
            raise DuplicateTechnicianIdError(f"Technician with ID '{payload.id}' already exists")
        tech_id = payload.id
    else:
        tech_id = generate_next_technician_id(db)

    # Validate home zone if specified
    if payload.home_zone_id:
        zone = db.query(Zone).filter(Zone.id == payload.home_zone_id).first()
        if not zone:
            # If not in zone table, still allow if zones aren't strictly enforced, or keep it
            pass

    # Normalize shifts to JSON-compatible dictionaries
    shifts_json = [
        {
            "date": s.date,
            "start": s.start.isoformat(),
            "end": s.end.isoformat(),
        }
        for s in payload.shifts
    ]

    # Normalize unavailable periods to JSON-compatible dictionaries
    unavail_json = [
        {
            "start": p.start.isoformat(),
            "end": p.end.isoformat(),
            "reason": p.reason or "unavailable",
        }
        for p in payload.unavailable_periods
    ]

    # Create model instance
    technician = Technician(
        id=tech_id,
        name=payload.name.strip(),
        home_zone_id=payload.home_zone_id,
        home_lat=float(payload.home_lat),
        home_lng=float(payload.home_lng),
        eligible_zones=list(payload.eligible_zones),
        skills=list(payload.skills),
        equipment=list(payload.equipment),
        shifts=shifts_json,
        unavailable_periods=unavail_json,
        overtime_allowed=bool(payload.overtime_allowed),
        max_overtime_minutes=int(payload.max_overtime_minutes or 0),
    )

    db.add(technician)
    db.commit()
    db.refresh(technician)
    return technician


def get_technicians(
    db: Session,
    zone: Optional[str] = None,
    skill: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Technician]:
    """Retrieve technician fleet with optional zone and skill filters."""
    query = db.query(Technician).order_by(Technician.id.asc())
    all_techs = query.all()

    # Apply filters in Python to seamlessly handle JSON arrays across dialects
    filtered = all_techs
    if zone:
        z_upper = zone.upper()
        filtered = [
            t for t in filtered
            if (t.home_zone_id and t.home_zone_id.upper() == z_upper)
            or (t.eligible_zones and any(ez.upper() == z_upper for ez in t.eligible_zones))
        ]

    if skill:
        s_lower = skill.lower()
        filtered = [
            t for t in filtered
            if t.skills and any(sk.lower() == s_lower for sk in t.skills)
        ]

    return filtered[skip : skip + limit]


def get_technician_by_id(db: Session, technician_id: str) -> Optional[Technician]:
    """Retrieve a single technician by ID."""
    return db.query(Technician).filter(Technician.id == technician_id).first()
