from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


class LocationSchema(BaseModel):
    lat: float
    lng: float
    address: Optional[str] = None


class ShiftSchema(BaseModel):
    date: str
    start: datetime
    end: datetime


class OvertimeSchema(BaseModel):
    allowed: bool
    max_minutes_per_shift: int = 0


class TechnicianSchema(BaseModel):
    id: str
    name: str
    home_zone_id: Optional[str] = None
    home_location: LocationSchema
    eligible_zones: List[str]
    skills: List[str]
    equipment: List[str]
    shifts: List[ShiftSchema]
    unavailable_periods: List[Dict[str, Any]] = []
    overtime: OvertimeSchema


class JobSchema(BaseModel):
    id: str
    idempotency_key: Optional[str] = None
    customer_name: str
    title: str
    zone_id: Optional[str] = None
    location: LocationSchema
    priority: int = Field(ge=1, le=4)
    priority_label: str
    duration_minutes: int = Field(gt=0)
    required_skills: List[str]
    required_equipment: List[str]
    time_window_start: datetime
    time_window_end: datetime
    sla_deadline: datetime
    status: str
    assigned_technician_id: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    created_at: datetime
    tags: List[str] = []


class ExistingAssignmentSchema(BaseModel):
    job_id: str
    technician_id: str
    start: datetime
    end: datetime
    actual_start: Optional[datetime] = None
    status: str


class DisruptionScenarioSchema(BaseModel):
    id: str
    category: str
    type: str
    name: str
    effective_at: datetime
    payload: Dict[str, Any]
    expected_behaviour: str


class ImportStats(BaseModel):
    zones_imported: int = 0
    technicians_imported: int = 0
    jobs_imported: int = 0
    existing_assignments_imported: int = 0
    disruptions_imported: int = 0
    metadata_keys_imported: int = 0
    records_skipped_or_updated: int = 0
    errors: List[str] = []
    simulation_clock: str
