from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.schemas.assignment import AssignmentSummary


class SchedulingRunConfig(BaseModel):
    """Configuration options supplied when initiating a scheduling run."""
    as_of: Optional[datetime] = Field(None, description="Simulation reference clock timestamp. Defaults to authoritative DB as_of.")
    horizon_start: Optional[datetime] = Field(None, description="Start of scheduling window. Defaults to planning horizon start.")
    horizon_end: Optional[datetime] = Field(None, description="End of scheduling window. Defaults to planning horizon end.")
    mode: str = Field(default="baseline", description="Scheduling mode: 'baseline', 'recovery', 'simulation'.")
    respect_existing_assignments: bool = Field(default=True, description="Strictly preserve all existing assigned jobs.")


class SimulationClockResponse(BaseModel):
    """Current operational simulation clock and planning horizon window."""
    as_of: datetime
    horizon_start: datetime
    horizon_end: datetime
    time_zone: str = "Asia/Kolkata (+05:30)"


class SchedulingInput(BaseModel):
    """Complete consolidated input dataset required for scheduling optimization."""
    run_id: str = Field(..., description="Unique generated scheduling run identifier")
    as_of: datetime = Field(..., description="Simulation reference timestamp")
    horizon_start: datetime = Field(..., description="Start of scheduling planning horizon")
    horizon_end: datetime = Field(..., description="End of scheduling planning horizon")
    pending_jobs_count: int = Field(..., description="Number of pending/unassigned jobs available to schedule")
    technicians_count: int = Field(..., description="Number of eligible active technicians")
    existing_assignments_count: int = Field(..., description="Number of pre-existing locked/in-progress assignments")
    pending_jobs: List[JobResponse] = Field(default_factory=list, description="List of jobs needing dispatch")
    technicians: List[TechnicianResponse] = Field(default_factory=list, description="Available technician roster")
    existing_assignments: List[AssignmentSummary] = Field(default_factory=list, description="Protected pre-existing assignments")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="System metadata including conventions & travel model")

    model_config = ConfigDict(from_attributes=True)


class AssignedJobPlan(BaseModel):
    """Structured plan for an assigned job within a scheduling run."""
    job_id: str
    technician_id: str
    scheduled_start: datetime
    scheduled_end: datetime
    travel_time_minutes: float = 0.0
    is_existing: bool = False
    status: str = "scheduled"
    details: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class UnassignedJobReport(BaseModel):
    """Detailed report for why a job could not be scheduled."""
    job_id: str
    reason: Optional[str] = None
    violated_constraints: List[str] = Field(default_factory=list)


class SchedulingResult(BaseModel):
    """Output structure representing the state and outcome of a scheduling run."""
    run_id: str = Field(..., description="Unique identifier for this scheduling execution")
    status: str = Field(..., description="Status of the run: 'initialized', 'scheduled', 'failed'")
    as_of: datetime = Field(..., description="Simulation clock timestamp used")
    horizon_start: datetime
    horizon_end: datetime
    total_jobs: int = Field(..., description="Total jobs evaluated")
    pending_jobs_count: int = Field(..., description="Count of pending jobs loaded")
    assigned_jobs_count: int = Field(..., description="Count of successfully planned assignments")
    unassigned_jobs_count: int = Field(..., description="Count of jobs left unassigned")
    existing_assignments_preserved: bool = Field(True, description="Safety check confirming existing assignments were preserved")
    assignments: List[AssignedJobPlan] = Field(default_factory=list, description="Planned or locked job assignments")
    unassigned_jobs: List[str] = Field(default_factory=list, description="IDs of jobs that remain unassigned")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Run summary performance and operational metrics")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)


class SkillMatchResult(BaseModel):
    """Detailed skill validation result for an individual technician evaluated against a job."""
    technician_id: str
    technician_name: Optional[str] = None
    is_eligible: bool
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    has_unsupported_skills: bool = False
    unsupported_skills: List[str] = Field(default_factory=list)
    rejection_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CandidateTechnicianSummary(BaseModel):
    """Candidate technician summary containing verified skill proficiencies and operational zones."""
    id: str
    name: str
    skills: List[str] = Field(default_factory=list)
    equipment: List[str] = Field(default_factory=list)
    eligible_zones: List[str] = Field(default_factory=list)
    home_zone_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EquipmentMatchResult(BaseModel):
    """Detailed equipment validation result for an individual technician evaluated against a job."""
    technician_id: str
    technician_name: Optional[str] = None
    is_eligible: bool
    matched_equipment: List[str] = Field(default_factory=list)
    missing_equipment: List[str] = Field(default_factory=list)
    has_unsupported_equipment: bool = False
    unsupported_equipment: List[str] = Field(default_factory=list)
    rejection_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class QualificationMatchResult(BaseModel):
    """Combined validation result verifying both certified skills and required equipment."""
    technician_id: str
    technician_name: Optional[str] = None
    is_eligible: bool
    skill_eligible: bool
    equipment_eligible: bool
    skill_match: SkillMatchResult
    equipment_match: EquipmentMatchResult
    missing_skills: List[str] = Field(default_factory=list)
    missing_equipment: List[str] = Field(default_factory=list)
    failure_categories: List[str] = Field(default_factory=list)
    combined_rejection_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobCandidateEvaluation(BaseModel):
    """Consolidated candidate evaluation for a job combining skills and equipment constraints."""
    job_id: str
    job_title: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    required_equipment: List[str] = Field(default_factory=list)
    has_unsupported_requirements: bool = False
    unsupported_requirements: List[str] = Field(default_factory=list)
    candidate_count: int = 0
    is_assignable: bool = True
    eligible_candidates: List[CandidateTechnicianSummary] = Field(default_factory=list)
    rejected_candidates: List[QualificationMatchResult] = Field(default_factory=list)
    skill_only_matching_candidates: List[str] = Field(
        default_factory=list,
        description="Technicians who possess all required skills but fail mandatory equipment",
    )
    rejection_summary: Dict[str, str] = Field(default_factory=dict, description="technician_id -> reason")
    reason_if_unassignable: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CombinedQualificationRequest(BaseModel):
    """Request payload for evaluating technician compatibility against skill and equipment requirements."""
    job_id: Optional[str] = None
    required_skills: Optional[List[str]] = None
    required_equipment: Optional[List[str]] = None
    technician_ids: Optional[List[str]] = None



class JobSkillCandidates(BaseModel):
    """Structured candidates analysis for a job based strictly on skill proficiencies."""
    job_id: str
    job_title: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    has_unsupported_skills: bool = False
    unsupported_skills: List[str] = Field(default_factory=list)
    candidate_count: int = 0
    is_assignable: bool = True
    eligible_candidates: List[CandidateTechnicianSummary] = Field(default_factory=list)
    rejected_candidates: List[SkillMatchResult] = Field(default_factory=list)
    rejection_summary: Dict[str, str] = Field(default_factory=dict, description="Map of technician_id -> rejection reason")
    reason_if_unassignable: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SkillFilterRequest(BaseModel):
    """Request payload for filtering candidate technicians by custom skill lists or job ID."""
    job_id: Optional[str] = None
    required_skills: Optional[List[str]] = None
    technician_ids: Optional[List[str]] = None

