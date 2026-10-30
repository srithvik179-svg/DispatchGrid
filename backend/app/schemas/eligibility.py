from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ValidationIssueSchema(BaseModel):
    category: str = Field(..., description="Validation category: skills, equipment, zone, shift, unavailable, time_window")
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable rejection explanation")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional context parameters")


class EligibilityCheckRequest(BaseModel):
    job_id: Optional[str] = Field(None, description="Optional job ID to check against database record")
    technician_id: Optional[str] = Field(None, description="Optional technician ID to check against database record")
    proposed_start: Optional[datetime] = Field(None, description="Proposed start timestamp for execution")
    proposed_end: Optional[datetime] = Field(None, description="Proposed completion timestamp for execution")
    # Alternatively support inline payloads for offline or simulation evaluation
    required_skills: Optional[List[str]] = None
    required_equipment: Optional[List[str]] = None
    job_zone_id: Optional[str] = None
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    duration_minutes: Optional[int] = None


class EligibilityCheckResponse(BaseModel):
    is_eligible: bool = Field(..., description="True if technician satisfies all hard operational constraints")
    reasons: List[str] = Field(default_factory=list, description="List of all human-readable rejection reasons")
    missing_skills: List[str] = Field(default_factory=list, description="Skills required by job but missing from technician")
    missing_equipment: List[str] = Field(default_factory=list, description="Equipment required by job but missing from technician kit")
    zone_eligible: bool = Field(..., description="Whether job zone is permitted under technician eligible zones")
    shift_available: bool = Field(..., description="Whether technician has shift capacity during the proposed window")
    unavailable_conflict: bool = Field(..., description="Whether proposed window overlaps with pre-scheduled technician leave")
    time_window_valid: bool = Field(..., description="Whether proposed start and end fall within job's allowable time window")
    overtime_required_minutes: int = Field(0, description="Overtime minutes required beyond standard shift end")
    overtime_allowed: bool = Field(False, description="Whether overtime was authorized and within technician max limit")
    issues: List[ValidationIssueSchema] = Field(default_factory=list, description="Detailed list of specific constraint issues")
