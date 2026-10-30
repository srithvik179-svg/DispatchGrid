from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.models.job import Job
from app.models.technician import Technician
from app.models.assignment import Assignment
from app.models.zone import Zone
from app.models.system import SystemMetadata
from app.core.config import settings

router = APIRouter()


class JobSummaryItem(BaseModel):
    id: str
    title: str
    customer_name: str
    zone_id: Optional[str] = None
    priority: int
    priority_label: str
    duration_minutes: int
    status: str
    required_skills: List[str]
    time_window_start: datetime
    time_window_end: datetime
    sla_deadline: datetime
    assigned_technician_id: Optional[str] = None


class TechnicianSummaryItem(BaseModel):
    id: str
    name: str
    home_zone_id: Optional[str] = None
    skills: List[str]
    equipment: List[str]
    eligible_zones: List[str]
    shifts_count: int
    overtime_allowed: bool


class OverviewStats(BaseModel):
    total_jobs: int
    job_counts_by_status: Dict[str, int]
    job_counts_by_priority: Dict[str, int]
    total_technicians: int
    total_assignments: int
    total_zones: int
    simulation_clock: str
    jobs: List[JobSummaryItem]
    technicians: List[TechnicianSummaryItem]


@router.get("/overview", response_model=OverviewStats, tags=["Overview"])
def get_overview_data(
    jobs_limit: int = Query(15, ge=1, le=108, description="Number of jobs to return in preview list"),
    techs_limit: int = Query(20, ge=1, le=50, description="Number of technicians to return"),
    db: Session = Depends(get_db),
) -> OverviewStats:
    """
    Returns authentic system overview statistics, status breakdowns,
    and preview lists of service jobs and technicians directly from the database.
    """
    # 1. Total jobs and status distribution
    total_jobs = db.query(Job).count()
    status_counts_raw = (
        db.query(Job.status, func.count(Job.id))
        .group_by(Job.status)
        .all()
    )
    job_counts_by_status: Dict[str, int] = {
        "pending": 0,
        "completed": 0,
        "in_progress": 0,
        "cancelled": 0,
    }
    for status, count in status_counts_raw:
        job_counts_by_status[status] = count

    # 2. Priority breakdown
    priority_counts_raw = (
        db.query(Job.priority_label, func.count(Job.id))
        .group_by(Job.priority_label)
        .all()
    )
    job_counts_by_priority: Dict[str, int] = {}
    for plabel, count in priority_counts_raw:
        job_counts_by_priority[plabel] = count

    # 3. Technician and zone counts
    total_technicians = db.query(Technician).count()
    total_assignments = db.query(Assignment).count()
    total_zones = db.query(Zone).count()

    # 4. Simulation clock
    clock_rec = db.query(SystemMetadata).filter_by(key="as_of").first()
    simulation_clock = clock_rec.value if clock_rec else settings.SIMULATION_CLOCK_DEFAULT

    # 5. Job preview list (order: in_progress, completed, priority asc, time window asc)
    jobs_query = (
        db.query(Job)
        .order_by(
            # completed/in_progress first, then pending by priority
            Job.status.desc(),
            Job.priority.asc(),
            Job.time_window_start.asc(),
        )
        .limit(jobs_limit)
        .all()
    )
    job_items = [
        JobSummaryItem(
            id=j.id,
            title=j.title,
            customer_name=j.customer_name,
            zone_id=j.zone_id,
            priority=j.priority,
            priority_label=j.priority_label,
            duration_minutes=j.duration_minutes,
            status=j.status,
            required_skills=j.required_skills or [],
            time_window_start=j.time_window_start,
            time_window_end=j.time_window_end,
            sla_deadline=j.sla_deadline,
            assigned_technician_id=j.assigned_technician_id,
        )
        for j in jobs_query
    ]

    # 6. Technician preview list
    techs_query = db.query(Technician).order_by(Technician.id.asc()).limit(techs_limit).all()
    tech_items = [
        TechnicianSummaryItem(
            id=t.id,
            name=t.name,
            home_zone_id=t.home_zone_id,
            skills=t.skills or [],
            equipment=t.equipment or [],
            eligible_zones=t.eligible_zones or [],
            shifts_count=len(t.shifts or []),
            overtime_allowed=t.overtime_allowed,
        )
        for t in techs_query
    ]

    return OverviewStats(
        total_jobs=total_jobs,
        job_counts_by_status=job_counts_by_status,
        job_counts_by_priority=job_counts_by_priority,
        total_technicians=total_technicians,
        total_assignments=total_assignments,
        total_zones=total_zones,
        simulation_clock=simulation_clock,
        jobs=job_items,
        technicians=tech_items,
    )
