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
    """Candidate technician summary containing verified skill proficiencies, equipment, zones, and travel info."""
    id: str
    name: str
    skills: List[str] = Field(default_factory=list)
    equipment: List[str] = Field(default_factory=list)
    eligible_zones: List[str] = Field(default_factory=list)
    home_zone_id: Optional[str] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None
    distance_km: Optional[float] = None
    travel_minutes: Optional[float] = None

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


class TravelEstimate(BaseModel):
    """Structured deterministic travel calculation between two geographic points."""
    origin_type: str = Field(..., description="'home' or 'job'")
    origin_id: str = Field(..., description="Technician ID or origin Job ID")
    origin_lat: float
    origin_lng: float
    destination_job_id: str
    destination_lat: float
    destination_lng: float
    distance_km: float = Field(..., description="Deterministic Haversine distance in kilometers")
    travel_minutes: float = Field(..., description="Estimated travel time in minutes based on travel speed")
    speed_kmh: float = Field(default=30.0, description="Assumed average transit velocity in km/h")

    model_config = ConfigDict(from_attributes=True)


class ZoneMatchResult(BaseModel):
    """Detailed validation result verifying technician operational territory against job zone."""
    technician_id: str
    technician_name: Optional[str] = None
    is_eligible: bool
    job_zone_id: Optional[str] = None
    eligible_zones: List[str] = Field(default_factory=list)
    home_zone_id: Optional[str] = None
    rejection_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GeoEligibilityResult(BaseModel):
    """Combined geographical eligibility analysis including zone certification and travel metrics."""
    technician_id: str
    technician_name: Optional[str] = None
    job_id: str
    is_eligible: bool
    zone_match: ZoneMatchResult
    travel_estimate: Optional[TravelEstimate] = None
    distance_km: Optional[float] = None
    travel_minutes: Optional[float] = None
    rejection_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TravelCalculationRequest(BaseModel):
    """Payload for calculating travel distance and minutes between two coordinates."""
    origin_lat: float = Field(..., ge=-90.0, le=90.0)
    origin_lng: float = Field(..., ge=-180.0, le=180.0)
    destination_lat: float = Field(..., ge=-90.0, le=90.0)
    destination_lng: float = Field(..., ge=-180.0, le=180.0)
    speed_kmh: Optional[float] = Field(default=30.0, gt=0.0)


class TravelCalculationResponse(BaseModel):
    """Response containing calculated distance and travel duration."""
    distance_km: float
    travel_minutes: float
    speed_kmh: float
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float


class ShiftAvailabilityResult(BaseModel):
    """Evaluation result for technician working shift coverage and overtime rules."""
    technician_id: str
    technician_name: Optional[str] = None
    is_available: bool
    proposed_start: datetime
    proposed_end: datetime
    matched_shift_date: Optional[str] = None
    is_within_regular_shift: bool = False
    requires_overtime: bool = False
    overtime_minutes: int = 0
    is_overtime_permitted: bool = False
    max_overtime_minutes: int = 0
    overtime_penalty_cost: float = 0.0
    rejection_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UnavailabilityCheckResult(BaseModel):
    """Evaluation result for collision detection against scheduled leaves or breaks."""
    technician_id: str
    technician_name: Optional[str] = None
    is_free: bool
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    rejection_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TechnicianAvailabilityEvaluation(BaseModel):
    """Consolidated availability evaluation across shifts, unavailabilities, and simulation clock."""
    technician_id: str
    technician_name: Optional[str] = None
    job_id: Optional[str] = None
    is_available: bool
    shift_result: ShiftAvailabilityResult
    unavailability_result: UnavailabilityCheckResult
    is_before_simulation_clock: bool = False
    proposed_start: datetime
    proposed_end: datetime
    duration_minutes: int
    overtime_minutes: int = 0
    overtime_penalty: float = 0.0
    failure_reasons: List[str] = Field(default_factory=list)
    combined_rejection_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AvailabilityCheckRequest(BaseModel):
    """Request payload for validating technician schedule availability."""
    technician_id: str
    job_id: Optional[str] = None
    proposed_start: datetime
    duration_minutes: Optional[int] = Field(None, gt=0)
    proposed_end: Optional[datetime] = None
    enforce_simulation_clock: bool = True
    as_of: Optional[datetime] = None


class TimeWindowValidationResult(BaseModel):
    """Validation result evaluating hard time windows, travel reachability, and soft SLA deadlines."""
    job_id: Optional[str] = None
    is_eligible: bool = Field(..., description="Whether all hard time-window and travel constraints are satisfied")
    proposed_start: datetime
    proposed_end: datetime
    duration_minutes: int
    time_window_start: datetime
    time_window_end: datetime
    sla_deadline: Optional[datetime] = None

    # Hard constraint flags
    is_window_expired: bool = False
    starts_too_early: bool = False
    ends_too_late: bool = False
    duration_mismatch: bool = False
    travel_infeasible: bool = False
    starts_before_simulation_clock: bool = False

    # Travel transit details
    travel_minutes: float = 0.0
    origin_departure_time: Optional[datetime] = None
    earliest_arrival_time: Optional[datetime] = None

    # Soft SLA metrics (crucial: SLA lateness does NOT automatically cause hard rejection)
    is_sla_violated: bool = False
    sla_lateness_minutes: int = 0
    sla_status: str = Field(default="on_time", description="'on_time', 'late', 'not_applicable'")

    # Detailed rejection reporting
    rejection_reasons: List[str] = Field(default_factory=list)
    rejection_codes: List[str] = Field(default_factory=list)
    summary: str = ""

    model_config = ConfigDict(from_attributes=True)


class FeasibleWindowResult(BaseModel):
    """Feasible scheduling start and completion interval for a job given operational constraints."""
    job_id: Optional[str] = None
    earliest_feasible_start: datetime
    latest_feasible_start: datetime
    earliest_feasible_completion: datetime
    latest_feasible_completion: datetime
    duration_minutes: int
    is_feasible: bool
    travel_minutes: float = 0.0
    time_window_start: datetime
    time_window_end: datetime
    sla_deadline: Optional[datetime] = None
    on_time_sla_latest_start: Optional[datetime] = None
    infeasibility_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TimeWindowCheckRequest(BaseModel):
    """Request payload for evaluating job time-window and SLA compatibility."""
    job_id: Optional[str] = None
    proposed_start: datetime
    proposed_end: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    sla_deadline: Optional[datetime] = None
    travel_minutes: Optional[float] = Field(default=0.0, ge=0.0)
    origin_departure_time: Optional[datetime] = None
    as_of: Optional[datetime] = None
    enforce_simulation_clock: bool = True


class SchedulingConflict(BaseModel):
    """Specific conflict detected between a proposed assignment and technician itinerary."""
    conflict_type: str = Field(
        ...,
        description="'double_booking', 'travel_buffer_preceding', 'travel_buffer_succeeding', 'in_progress_collision', 'completed_collision', 'home_travel_conflict', 'shift_boundary_conflict', 'unavailability_collision'",
    )
    code: str = Field(..., description="Machine-readable conflict error code")
    conflicting_job_id: Optional[str] = None
    conflicting_assignment_id: Optional[int] = None
    conflicting_status: Optional[str] = None
    conflicting_start: Optional[datetime] = None
    conflicting_end: Optional[datetime] = None
    travel_minutes_required: Optional[float] = None
    travel_buffer_deficit_minutes: Optional[float] = None
    message: str

    model_config = ConfigDict(from_attributes=True)


class ConflictCheckResult(BaseModel):
    """Comprehensive result of conflict detection for a proposed assignment against technician schedule."""
    technician_id: str
    technician_name: Optional[str] = None
    job_id: Optional[str] = None
    has_conflict: bool
    is_eligible: bool
    proposed_start: datetime
    proposed_end: datetime
    duration_minutes: int
    conflicts: List[SchedulingConflict] = Field(default_factory=list)
    preceding_assignment: Optional[Dict[str, Any]] = None
    succeeding_assignment: Optional[Dict[str, Any]] = None
    requires_overtime: bool = False
    overtime_minutes: int = 0
    overtime_penalty: float = 0.0
    summary: str = ""

    model_config = ConfigDict(from_attributes=True)


class ConflictCheckRequest(BaseModel):
    """Request payload for validating scheduling conflicts against technician itinerary."""
    technician_id: str
    job_id: Optional[str] = None
    proposed_start: datetime
    duration_minutes: Optional[int] = Field(None, gt=0)
    proposed_end: Optional[datetime] = None
    job_lat: Optional[float] = None
    job_lng: Optional[float] = None
    include_travel: bool = True
    as_of: Optional[datetime] = None
    enforce_simulation_clock: bool = True


class TechnicianRejectionDetail(BaseModel):
    """Detailed explanation of why an individual technician cannot be assigned to a job."""
    technician_id: str
    technician_name: Optional[str] = None
    is_structurally_capable: bool = False
    rejection_category: str = Field(..., description="'skills', 'equipment', 'zone', 'shift', 'time_window', 'travel', 'conflict'")
    rejection_code: str
    missing_skills: List[str] = Field(default_factory=list)
    missing_equipment: List[str] = Field(default_factory=list)
    zone_certified: bool = True
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class JobFeasibilityReport(BaseModel):
    """Diagnostic categorization distinguishing feasibility, temporary constraints, and permanent impossibility."""
    job_id: str
    classification: str = Field(..., description="'feasible', 'currently_infeasible', 'permanently_impossible'")
    primary_category: str = Field(..., description="'none', 'unsupported_skill', 'missing_skill', 'missing_equipment', 'uncovered_zone', 'shift_hours', 'travel_deficit', 'schedule_conflict', 'time_window'")
    is_structurally_feasible: bool = Field(..., description="Whether the fleet possesses skills, equipment, and zone to execute this job")
    qualified_technician_count: int = 0
    qualified_technician_ids: List[str] = Field(default_factory=list)
    is_sla_delayed: bool = False
    sla_lateness_minutes: int = 0
    rejection_summary: str
    actionable_recommendation: str
    technician_rejections: List[TechnicianRejectionDetail] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class FleetFeasibilitySummary(BaseModel):
    """Fleet-wide diagnostic summary classifying all evaluated jobs."""
    run_id: Optional[str] = None
    as_of: datetime
    total_jobs: int
    feasible_count: int
    currently_infeasible_count: int
    permanently_impossible_count: int
    job_reports: Dict[str, JobFeasibilityReport] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class FeasibilityEvaluationRequest(BaseModel):
    """Request payload for assessing job scheduling feasibility."""
    job_id: Optional[str] = None
    as_of: Optional[datetime] = None
    include_technician_details: bool = True


class ScheduleGenerateRequest(BaseModel):
    """Request payload for triggering automatic schedule generation."""
    as_of: Optional[datetime] = Field(None, description="Simulation reference clock timestamp.")
    persist: bool = Field(default=True, description="Whether to persist newly planned assignments to database.")
    mode: str = Field(default="baseline", description="Scheduling mode: 'baseline', 'recovery', 'simulation'.")
    respect_existing_assignments: bool = Field(default=True, description="Strictly preserve all pre-existing assignments.")


class ScheduleAssignmentItem(BaseModel):
    """Structured assignment entry for a job dispatched to a technician."""
    assignment_id: Optional[int] = None
    job_id: str
    technician_id: str
    technician_name: Optional[str] = None
    job_title: Optional[str] = None
    customer_name: Optional[str] = None
    zone_id: Optional[str] = None
    priority: Optional[int] = None
    priority_label: Optional[str] = None
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    travel_time_minutes: float = 0.0
    distance_km: float = 0.0
    status: str = "scheduled"
    is_existing: bool = False

    model_config = ConfigDict(from_attributes=True)


class UnassignedJobExplanation(BaseModel):
    """Detailed explanation of why an unassigned job could not be scheduled."""
    job_id: str
    title: str
    customer_name: str
    zone_id: Optional[str] = None
    priority: int
    priority_label: str
    duration_minutes: int
    classification: str = Field(..., description="'currently_infeasible' or 'permanently_impossible'")
    primary_category: str = Field(..., description="Root failure category")
    rejection_summary: str
    actionable_recommendation: str
    required_skills: List[str] = Field(default_factory=list)
    required_equipment: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ScheduleGenerateResponse(BaseModel):
    """Complete response from schedule generation API."""
    run_id: str
    as_of: datetime
    total_jobs: int
    assigned_count: int
    unassigned_count: int
    technicians_count: int
    technicians_utilized: int
    persisted: bool
    existing_assignments_preserved: bool
    assignments: List[ScheduleAssignmentItem] = Field(default_factory=list)
    unassigned_jobs: List[UnassignedJobExplanation] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ScheduleCurrentResponse(BaseModel):
    """Current operational schedule in the system."""
    as_of: datetime
    total_jobs: int
    assigned_count: int
    unassigned_count: int
    technicians_count: int
    technicians_utilized: int
    assignments: List[ScheduleAssignmentItem] = Field(default_factory=list)
    unassigned_jobs: List[UnassignedJobExplanation] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class JobAssignmentResponse(BaseModel):
    """Individual job assignment lookup and status response."""
    job_id: str
    is_assigned: bool
    status: str
    assignment: Optional[ScheduleAssignmentItem] = None
    feasibility: Optional[JobFeasibilityReport] = None

    model_config = ConfigDict(from_attributes=True)


class TechnicianItineraryItem(BaseModel):
    """Sequential stop item in a technician's route schedule."""
    assignment_id: Optional[int] = None
    job_id: str
    job_title: str
    customer_name: str
    zone_id: Optional[str] = None
    lat: float
    lng: float
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    travel_from_previous_minutes: float = 0.0
    distance_from_previous_km: float = 0.0
    status: str
    is_existing: bool = False

    model_config = ConfigDict(from_attributes=True)


class TechnicianScheduleResponse(BaseModel):
    """Full operational route and assignment schedule for an individual technician."""
    technician_id: str
    technician_name: str
    home_zone_id: Optional[str] = None
    home_lat: float
    home_lng: float
    eligible_zones: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    equipment: List[str] = Field(default_factory=list)
    total_assigned_jobs: int
    total_working_minutes: int
    total_travel_minutes: float
    itinerary: List[TechnicianItineraryItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# =========================================================================
# PHASE 23 – Objective Function & Scoring Engine Schemas
# =========================================================================

class ObjectiveWeightsConfig(BaseModel):
    """Configurable weights for the multi-criteria schedule objective function."""
    w_sla_lateness: float = Field(default=2.0, ge=0.0, description="Cost per minute of service completion past soft SLA deadline")
    w_travel_time: float = Field(default=1.0, ge=0.0, description="Cost per minute of technician transit travel time")
    w_overtime: float = Field(default=3.0, ge=0.0, description="Cost per minute of permitted overtime worked outside standard shifts")
    w_churn: float = Field(default=250.0, ge=0.0, description="Penalty per modified or reassigned pre-existing baseline assignment")
    w_unassigned_p1: float = Field(default=1000.0, ge=0.0, description="Penalty for leaving an Urgent (Priority 1) job unassigned")
    w_unassigned_p2: float = Field(default=500.0, ge=0.0, description="Penalty for leaving a High (Priority 2) job unassigned")
    w_unassigned_p3: float = Field(default=200.0, ge=0.0, description="Penalty for leaving a Medium (Priority 3) job unassigned")
    w_unassigned_p4: float = Field(default=100.0, ge=0.0, description="Penalty for leaving a Low (Priority 4) job unassigned")

    model_config = ConfigDict(from_attributes=True)


class JobLatenessDetail(BaseModel):
    """Detailed lateness record for a specific job."""
    job_id: str
    completion_time: datetime
    sla_deadline: datetime
    lateness_minutes: int
    penalty: float

    model_config = ConfigDict(from_attributes=True)


class SLALatenessBreakdown(BaseModel):
    """Component score for SLA target lateness."""
    total_delayed_jobs: int = 0
    total_lateness_minutes: int = 0
    total_penalty: float = 0.0
    weight: float = 2.0
    delayed_jobs: List[JobLatenessDetail] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TechnicianTravelDetail(BaseModel):
    """Travel breakdown for an individual technician route."""
    technician_id: str
    technician_name: Optional[str] = None
    legs_count: int = 0
    total_distance_km: float = 0.0
    total_travel_minutes: float = 0.0
    penalty: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class TravelTimeBreakdown(BaseModel):
    """Component score for technician transit times."""
    total_travel_minutes: float = 0.0
    total_distance_km: float = 0.0
    total_penalty: float = 0.0
    weight: float = 1.0
    technician_travel: List[TechnicianTravelDetail] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UnassignedPriorityBreakdown(BaseModel):
    """Component score for unassigned jobs stratified by priority."""
    unassigned_p1_count: int = 0
    unassigned_p2_count: int = 0
    unassigned_p3_count: int = 0
    unassigned_p4_count: int = 0
    total_unassigned_count: int = 0
    p1_penalty: float = 0.0
    p2_penalty: float = 0.0
    p3_penalty: float = 0.0
    p4_penalty: float = 0.0
    total_penalty: float = 0.0
    unassigned_job_ids: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TechnicianOvertimeDetail(BaseModel):
    """Overtime details for a technician."""
    technician_id: str
    technician_name: Optional[str] = None
    overtime_minutes: int = 0
    penalty: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class OvertimeBreakdown(BaseModel):
    """Component score for authorized overtime work."""
    total_overtime_minutes: int = 0
    technicians_with_overtime_count: int = 0
    total_penalty: float = 0.0
    weight: float = 3.0
    technician_overtime: List[TechnicianOvertimeDetail] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AssignmentChurnDetail(BaseModel):
    """Detailed record of a disrupted or modified baseline assignment."""
    job_id: str
    baseline_technician_id: str
    new_technician_id: str
    change_type: str = "reassigned"
    penalty: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class AssignmentChurnBreakdown(BaseModel):
    """Component score for unnecessary assignment changes / schedule churn."""
    total_disrupted_jobs: int = 0
    total_penalty: float = 0.0
    weight: float = 250.0
    churn_details: List[AssignmentChurnDetail] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class HardConstraintViolation(BaseModel):
    """Specific hard operational constraint violation that invalidates schedule feasibility."""
    violation_type: str = Field(..., description="'DOUBLE_BOOKING', 'SKILL_MISMATCH', 'EQUIPMENT_MISMATCH', 'ZONE_VIOLATION', 'TIME_WINDOW_BREACH', 'UNAUTHORIZED_OVERTIME', 'BUFFER_VIOLATION'")
    job_id: Optional[str] = None
    technician_id: Optional[str] = None
    description: str

    model_config = ConfigDict(from_attributes=True)


class ScheduleScoreResult(BaseModel):
    """Comprehensive, traceable evaluation of a schedule's objective cost and feasibility."""
    total_score: float = Field(..., description="Aggregate objective penalty cost (lower is superior)")
    is_feasible: bool = Field(..., description="Strictly True only if zero hard constraint violations exist")
    hard_violations_count: int = Field(0, description="Count of hard constraint violations detected")
    hard_violations: List[HardConstraintViolation] = Field(default_factory=list, description="List of hard constraint breaches")
    sla_component: SLALatenessBreakdown
    travel_component: TravelTimeBreakdown
    unassigned_component: UnassignedPriorityBreakdown
    overtime_component: OvertimeBreakdown
    churn_component: AssignmentChurnBreakdown
    weights_used: ObjectiveWeightsConfig
    units: Dict[str, str] = Field(default_factory=dict, description="Units and scales for each metric")
    assumptions: List[str] = Field(default_factory=list, description="Mathematical model assumptions")

    model_config = ConfigDict(from_attributes=True)


class ScoreEvaluationRequest(BaseModel):
    """Request payload for evaluating schedule objective score with custom weights."""
    weights: Optional[ObjectiveWeightsConfig] = None
    as_of: Optional[datetime] = None
    respect_existing_assignments: bool = True


# =========================================================================
# PHASE 24 – Priority-Aware Optimisation Schemas
# =========================================================================

class JobPriorityProfile(BaseModel):
    """Multi-dimensional priority and scarcity profile for dispatch scheduling."""
    job_id: str
    priority: int = Field(..., description="1=Urgent, 2=High, 3=Medium, 4=Low")
    priority_label: str
    qualified_technicians_count: int = Field(..., description="Technician scarcity: count of qualified candidates in fleet")
    qualified_technician_ids: List[str] = Field(default_factory=list)
    window_duration_ratio: float = Field(..., description="Tightness ratio: duration_minutes / window_minutes (near 1.0 = zero flexibility)")
    window_slack_minutes: float = Field(..., description="Available slack buffer: window_minutes - duration_minutes")
    sla_deadline: datetime
    time_window_start: datetime
    time_window_end: datetime
    tie_breaker_key: str

    model_config = ConfigDict(from_attributes=True)


class CompetingJobResolution(BaseModel):
    """Deterministic resolution and explanation for competing high-priority jobs."""
    winner_job_id: str
    loser_job_id: str
    deciding_factor: str = Field(..., description="'PRIORITY_LEVEL', 'TECHNICIAN_SCARCITY', 'WINDOW_TIGHTNESS', 'SLA_DEADLINE', 'HARD_WINDOW_END', 'WINDOW_START', 'DETERMINISTIC_ID'")
    explanation: str
    job_a_profile: JobPriorityProfile
    job_b_profile: JobPriorityProfile

    model_config = ConfigDict(from_attributes=True)


class ConflictPairEvaluationRequest(BaseModel):
    """Request payload to analyze priority arbitration between two competing jobs."""
    job_id_a: str
    job_id_b: str


# =========================================================================
# PHASE 25 – Travel-Time Optimisation Schemas
# =========================================================================

class TravelLegDetail(BaseModel):
    """Granular trace of an individual transit leg in a technician's itinerary."""
    leg_index: int
    origin_type: str = Field(..., description="'home' or 'job'")
    origin_id: str
    origin_zone: Optional[str] = None
    origin_lat: float
    origin_lng: float
    destination_job_id: str
    destination_zone: Optional[str] = None
    destination_lat: float
    destination_lng: float
    distance_km: float
    travel_minutes: float
    is_zone_switch: bool = Field(False, description="True if crossing between distinct operational zones")

    model_config = ConfigDict(from_attributes=True)


class TechnicianTravelSummary(BaseModel):
    """Total travel time, transit distance, and zone switching metrics for a technician."""
    technician_id: str
    technician_name: str
    home_zone_id: Optional[str] = None
    total_travel_minutes: float
    total_distance_km: float
    home_to_first_minutes: float
    home_to_first_distance_km: float
    inter_job_minutes: float
    inter_job_distance_km: float
    job_count: int
    zone_switches_count: int
    legs: List[TravelLegDetail] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TravelMetricsComparison(BaseModel):
    """Measured, traceable comparison between initial and travel-optimized schedules."""
    initial_travel_minutes: float
    optimized_travel_minutes: float
    travel_minutes_saved: float
    travel_time_reduction_percent: float
    initial_distance_km: float
    optimized_distance_km: float
    distance_km_saved: float
    initial_zone_switches: int
    optimized_zone_switches: int
    zone_switches_avoided: int
    average_travel_per_job_initial: float
    average_travel_per_job_optimized: float
    technicians_evaluated: int
    technicians_improved: int

    model_config = ConfigDict(from_attributes=True)


class TravelOptimizationAction(BaseModel):
    """Explainable operational improvement applied to reduce unnecessary travel."""
    action_type: str = Field(..., description="'ROUTE_REORDER', 'TECHNICIAN_SWAP', or 'ZONE_CLUSTERING'")
    technician_ids: List[str] = Field(default_factory=list)
    job_ids: List[str] = Field(default_factory=list)
    travel_minutes_saved: float
    zone_switches_reduced: int = 0
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class TravelOptimizationResult(BaseModel):
    """Complete results of travel-time schedule optimization pass."""
    run_id: str
    as_of: datetime
    is_feasible: bool = Field(..., description="Strictly True if zero hard operational constraints are violated")
    hard_violations_count: int = 0
    hard_violations: List[HardConstraintViolation] = Field(default_factory=list)
    metrics_comparison: TravelMetricsComparison
    technician_travel_initial: List[TechnicianTravelSummary] = Field(default_factory=list)
    technician_travel_optimized: List[TechnicianTravelSummary] = Field(default_factory=list)
    optimizations_applied: List[TravelOptimizationAction] = Field(default_factory=list)
    assignments: List[AssignedJobPlan] = Field(default_factory=list)
    total_assigned_count: int = 0
    persisted: bool = False

    model_config = ConfigDict(from_attributes=True)


class TravelOptimizationRequest(BaseModel):
    """Request payload for travel-time schedule optimization."""
    run_id: Optional[str] = None
    persist: bool = Field(False, description="Persist improved assignments to the database")
    max_iterations: int = Field(10, ge=1, le=50)


# =========================================================================
# PHASE 26 – SLA Optimisation Schemas
# =========================================================================

class JobSLADetail(BaseModel):
    """Detailed SLA timeliness status, lateness metrics, and customer window alignment."""
    job_id: str
    title: str
    priority: int
    priority_label: str
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    expected_completion: Optional[datetime] = None
    sla_deadline: Optional[datetime] = None
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    sla_status: str = Field(..., description="'ON_TIME', 'AT_RISK', 'BREACHED', or 'UNASSIGNED'")
    is_already_breached_at_as_of: bool = Field(False, description="True if SLA deadline had already expired before simulation clock")
    is_within_hard_window: bool = Field(True, description="True if completion finishes within customer hard window_end")
    lateness_minutes: float = Field(0.0, description="Positive delay minutes past SLA target; 0.0 if on-time")
    slack_buffer_minutes: float = Field(0.0, description="Available buffer before SLA breach (sla_deadline - expected_completion)")
    lateness_penalty: float = Field(0.0, description="Financial/objective penalty cost based on configurable rate")
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class FleetSLAMetrics(BaseModel):
    """Fleet-wide aggregate SLA performance, timeliness percentages, and delay penalties."""
    as_of: datetime
    total_jobs_evaluated: int
    assigned_jobs_count: int
    on_time_count: int
    on_time_percentage: float
    at_risk_count: int
    at_risk_percentage: float
    breached_count: int
    breached_percentage: float
    already_breached_assigned_count: int
    total_lateness_minutes: float
    average_lateness_minutes: float
    max_lateness_minutes: float
    total_sla_penalty: float
    lateness_penalty_weight: float = 2.0
    at_risk_threshold_minutes: int = 30

    model_config = ConfigDict(from_attributes=True)


class SLAOptimizationAction(BaseModel):
    """Explainable scheduling action taken to protect an approaching deadline or reduce lateness."""
    action_type: str = Field(..., description="'SCHEDULE_EARLIER', 'SLA_DEADLINE_ARBITRATION', or 'AT_RISK_PROTECTION'")
    job_id: str
    technician_id: str
    previous_completion: Optional[datetime] = None
    new_completion: Optional[datetime] = None
    lateness_minutes_saved: float = 0.0
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class SLAOptimizationComparison(BaseModel):
    """Measured comparison of initial vs SLA-optimized schedule quality."""
    initial_metrics: FleetSLAMetrics
    optimized_metrics: FleetSLAMetrics
    lateness_minutes_saved: float
    penalty_saved: float
    breaches_prevented: int
    at_risk_rescued: int

    model_config = ConfigDict(from_attributes=True)


class SLAOptimizationResult(BaseModel):
    """Complete results of SLA optimization pass."""
    run_id: str
    as_of: datetime
    is_feasible: bool = Field(..., description="Strictly True if zero hard constraints are violated")
    hard_violations_count: int = 0
    hard_violations: List[HardConstraintViolation] = Field(default_factory=list)
    comparison: SLAOptimizationComparison
    job_sla_details: List[JobSLADetail] = Field(default_factory=list)
    optimizations_applied: List[SLAOptimizationAction] = Field(default_factory=list)
    assignments: List[AssignedJobPlan] = Field(default_factory=list)
    persisted: bool = False

    model_config = ConfigDict(from_attributes=True)


class SLAOptimizationRequest(BaseModel):
    """Request payload for SLA schedule optimization."""
    run_id: Optional[str] = None
    lateness_weight: float = Field(2.0, ge=0.1, le=100.0)
    at_risk_threshold_minutes: int = Field(30, ge=5, le=240)
    persist: bool = Field(False, description="Persist improved schedule to database")


class CompetingSLARequest(BaseModel):
    """Request payload to arbitrate between multiple competing SLA deadlines."""
    job_id_a: str
    job_id_b: str


class CompetingSLAResolution(BaseModel):
    """Deterministic resolution and explanation between two competing SLA target deadlines."""
    job_id_a: str
    job_id_b: str
    winner_job_id: str
    loser_job_id: str
    sla_a: datetime
    sla_b: datetime
    slack_a_minutes: float
    slack_b_minutes: float
    deciding_factor: str = Field(..., description="'SLA_DEADLINE_IMMINENCE', 'SLACK_BUFFER_TIGHTNESS', 'PRIORITY_LEVEL', or 'DETERMINISTIC_ID'")
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class AssignmentChangeDetail(BaseModel):
    """Detailed diff and stability impact for a single job assignment."""
    job_id: str = Field(..., description="Target job identifier")
    change_type: str = Field(..., description="Classification: UNCHANGED, TIME_SHIFTED, REASSIGNED, DROPPED_TO_UNASSIGNED, NEWLY_ASSIGNED")
    old_technician_id: Optional[str] = Field(None, description="Baseline assigned technician ID")
    new_technician_id: Optional[str] = Field(None, description="New assigned technician ID")
    old_start: Optional[datetime] = Field(None, description="Baseline scheduled start")
    new_start: Optional[datetime] = Field(None, description="New scheduled start")
    old_end: Optional[datetime] = Field(None, description="Baseline scheduled end")
    new_end: Optional[datetime] = Field(None, description="New scheduled end")
    time_shift_minutes: float = Field(0.0, description="Absolute start time displacement in minutes")
    is_protected: bool = Field(False, description="Whether this assignment represents completed or in-progress work")
    is_valid: bool = Field(True, description="Whether the new assignment satisfies all hard constraints")
    penalty: float = Field(0.0, description="Churn penalty incurred by this modification")
    reason: str = Field(..., description="Explanation of why change was made or why assignment was preserved")


class ScheduleStabilityMetrics(BaseModel):
    """Aggregate fleet assignment stability metrics and protection compliance."""
    total_baseline_assignments: int = Field(0, description="Total assignments present in baseline schedule")
    total_candidate_assignments: int = Field(0, description="Total assignments present in candidate schedule")
    unchanged_count: int = Field(0, description="Number of assignments preserved with zero technician or time change")
    unchanged_percentage: float = Field(100.0, description="Percentage of baseline assignments remaining completely unchanged")
    time_shifted_count: int = Field(0, description="Number of assignments retaining same technician but shifted in time")
    average_time_shift_minutes: float = Field(0.0, description="Average time shift among shifted jobs in minutes")
    reassigned_count: int = Field(0, description="Number of jobs switched to a different technician")
    dropped_to_unassigned_count: int = Field(0, description="Number of baseline assigned jobs that became unassigned")
    newly_assigned_count: int = Field(0, description="Number of previously unassigned jobs newly dispatched")
    completed_protected_count: int = Field(0, description="Number of completed jobs in baseline")
    completed_preserved_count: int = Field(0, description="Number of completed jobs strictly preserved")
    in_progress_protected_count: int = Field(0, description="Number of in-progress jobs in baseline")
    in_progress_preserved_count: int = Field(0, description="Number of in-progress jobs strictly preserved")
    total_churn_penalty: float = Field(0.0, description="Aggregate penalty assessed for schedule churn")
    stability_score: float = Field(100.0, description="Normalized schedule stability score (0.0 to 100.0%)")
    is_protection_violated: bool = Field(False, description="True if any completed or in-progress job was illegally altered")
    violations: List[str] = Field(default_factory=list, description="Descriptions of any illegal protection violations")


class StabilityComparisonRequest(BaseModel):
    """Request payload for evaluating stability between two schedules."""
    w_reassign: float = Field(250.0, description="Penalty points per technician reassignment")
    w_shift_per_hour: float = Field(30.0, description="Penalty points per hour of time displacement")
    w_unassign: float = Field(500.0, description="Penalty points per previously assigned job dropped")


class StabilityRecalculationRequest(BaseModel):
    """Request payload for minimal-churn schedule recalculation upon disruption or change."""
    disrupted_technician_id: Optional[str] = Field(None, description="Optional technician experiencing delay or unavailability")
    disrupted_job_id: Optional[str] = Field(None, description="Optional job experiencing delay or cancellation")
    delay_minutes: int = Field(0, description="Delay magnitude in minutes")
    reassign_weight: float = Field(250.0, description="Penalty weight for reassignment")
    shift_weight: float = Field(30.0, description="Penalty weight per hour of time displacement")
    persist: bool = Field(False, description="Whether to persist the recalculated schedule to the database")


class StabilityRecalculationResult(BaseModel):
    """Comprehensive result of minimal-churn schedule recalculation."""
    run_id: str = Field(..., description="Recalculation run ID")
    as_of: datetime = Field(..., description="Simulation clock timestamp")
    is_feasible: bool = Field(..., description="Whether schedule satisfies all hard constraints")
    hard_violations_count: int = Field(0, description="Number of hard constraint violations (must be 0)")
    hard_violations: List[HardConstraintViolation] = Field(default_factory=list, description="List of any violations")
    affected_jobs: List[str] = Field(default_factory=list, description="Job IDs that required rescheduling or reassignment")
    preserved_jobs: List[str] = Field(default_factory=list, description="Job IDs whose assignments were strictly preserved")
    stability_metrics: ScheduleStabilityMetrics = Field(..., description="Stability metrics comparing before vs after")
    assignment_changes: List[AssignmentChangeDetail] = Field(default_factory=list, description="Detailed change log")
    assignments: List[AssignedJobPlan] = Field(default_factory=list, description="Final recalculated assignment plans")
    persisted: bool = Field(False, description="Whether changes were persisted to database")


class MetricComparisonItem(BaseModel):
    """Granular comparison of a single performance metric between initial and optimized schedules."""
    metric_name: str = Field(..., description="Human-readable identifier of the metric")
    dimension: str = Field(..., description="Optimization dimension: travel, sla, unassigned, overtime, churn, total_score")
    unit: str = Field(..., description="Measurement unit: minutes, penalty points, count, percent")
    initial_value: float = Field(..., description="Measured value in the initial schedule")
    optimized_value: float = Field(..., description="Measured value in the optimized schedule")
    absolute_delta: float = Field(..., description="initial_value - optimized_value (positive indicates improvement for cost/penalty)")
    improvement_percentage: float = Field(..., description="Calculated percentage improvement using documented formula")
    formula: str = Field(..., description="Explicit formula used to calculate improvement")
    direction: str = Field(..., description="Direction: IMPROVED, REGRESSED, UNCHANGED")
    trade_off_explanation: str = Field(..., description="Explainable description of what changed and why")


class ScheduleSnapshotMetrics(BaseModel):
    """Consolidated KPI snapshot of a schedule at a specific optimization stage."""
    schedule_label: str = Field(..., description="Stage label: INITIAL, OPTIMIZED, or INTERMEDIATE")
    run_id: str = Field(..., description="Scheduling run ID")
    as_of: datetime = Field(..., description="Simulation reference clock timestamp")
    is_feasible: bool = Field(True, description="Whether the schedule satisfies 100% of hard constraints")
    hard_violations_count: int = Field(0, description="Count of hard constraint violations (must be 0 for feasible)")
    total_jobs: int = Field(..., description="Total jobs in planning scope")
    assigned_jobs_count: int = Field(..., description="Count of dispatched jobs")
    unassigned_jobs_count: int = Field(..., description="Count of unassigned jobs")
    total_travel_minutes: float = Field(..., description="Total fleet transit duration in minutes")
    average_travel_minutes: float = Field(..., description="Average transit duration per assigned job in minutes")
    total_sla_lateness_minutes: float = Field(..., description="Total lateness beyond soft SLA deadlines in minutes")
    average_sla_lateness_minutes: float = Field(..., description="Average lateness per breached job in minutes")
    on_time_jobs_count: int = Field(..., description="Count of jobs completing on or before SLA deadline")
    at_risk_jobs_count: int = Field(..., description="Count of jobs completing within risk buffer of SLA deadline")
    breached_jobs_count: int = Field(..., description="Count of jobs completing past soft SLA deadline")
    unassigned_p1_urgent: int = Field(0, description="Count of unassigned P1 Urgent jobs")
    unassigned_p2_high: int = Field(0, description="Count of unassigned P2 High jobs")
    unassigned_p3_medium: int = Field(0, description="Count of unassigned P3 Medium jobs")
    unassigned_p4_low: int = Field(0, description="Count of unassigned P4 Low jobs")
    total_overtime_minutes: float = Field(0.0, description="Total authorized overtime across all shifts in minutes")
    overtime_technicians_count: int = Field(0, description="Count of technicians working overtime")
    total_churn_penalty: float = Field(0.0, description="Assignment disruption/churn penalty points")
    objective_total_score: float = Field(..., description="Aggregate multi-objective cost score J(S)")
    component_sla_penalty: float = Field(..., description="SLA lateness penalty component C_sla")
    component_travel_penalty: float = Field(..., description="Transit travel penalty component C_travel")
    component_unassigned_penalty: float = Field(..., description="Unassigned jobs penalty component C_unassigned")
    component_overtime_penalty: float = Field(..., description="Overtime work penalty component C_overtime")
    component_churn_penalty: float = Field(..., description="Schedule churn penalty component C_churn")


class TradeOffNarrative(BaseModel):
    """Structured narrative explaining where improvements occurred and where trade-offs were made."""
    dimension: str = Field(..., description="Optimization dimension: travel, sla, unassigned, overtime, stability, overall")
    impact: str = Field(..., description="Impact category: POSITIVE, NEUTRAL, NEGATIVE")
    summary: str = Field(..., description="Concise 1-sentence headline of the outcome")
    details: str = Field(..., description="Detailed explanation of the causal mechanism and trade-off rationale")


class OptimizationReport(BaseModel):
    """Complete, persistent optimization comparison report between initial and optimized schedules."""
    report_id: str = Field(..., description="Unique report identifier: REP-OPT-YYYYMMDD-HHMMSS-<hex>")
    generated_at: datetime = Field(..., description="Timestamp when report was generated")
    as_of: datetime = Field(..., description="Simulation clock timestamp")
    initial_schedule_metrics: ScheduleSnapshotMetrics = Field(..., description="Baseline metrics before optimization")
    optimized_schedule_metrics: ScheduleSnapshotMetrics = Field(..., description="Optimized metrics after travel & SLA optimization")
    metric_comparisons: List[MetricComparisonItem] = Field(..., description="Itemized comparisons across all dimensions")
    trade_off_analysis: List[TradeOffNarrative] = Field(..., description="Structured trade-off narratives")
    overall_score_improvement_percentage: float = Field(..., description="Percentage improvement in aggregate objective score")
    overall_travel_saved_minutes: float = Field(..., description="Net transit travel minutes eliminated")
    overall_sla_penalty_saved: float = Field(..., description="Net SLA lateness penalties eliminated")
    executive_summary: str = Field(..., description="Executive briefing highlighting key findings and trade-offs")
    is_feasible: bool = Field(True, description="Whether optimized schedule satisfies all hard constraints")
    hard_constraints_preserved: bool = Field(True, description="Strict confirmation of 0 hard constraint violations")


class OptimizationReportSummary(BaseModel):
    """Lightweight summary of an optimization report for listing endpoints."""
    report_id: str = Field(..., description="Unique report identifier")
    generated_at: datetime = Field(..., description="Report generation timestamp")
    as_of: datetime = Field(..., description="Simulation clock timestamp")
    overall_score_improvement_percentage: float = Field(..., description="Objective score improvement percentage")
    overall_travel_saved_minutes: float = Field(..., description="Transit travel minutes saved")
    overall_sla_penalty_saved: float = Field(..., description="SLA penalties saved")
    is_feasible: bool = Field(..., description="Whether schedule is feasible")
    summary: str = Field(..., description="Short overview text")


class OptimizationReportGenerateRequest(BaseModel):
    """Request payload to generate, compare, and persist an optimization report."""
    lateness_weight: float = Field(2.0, ge=0.1, le=100.0, description="Weight per minute of SLA lateness")
    speed_kmh: float = Field(30.0, ge=5.0, le=120.0, description="Transit speed in km/h")
    w_churn: float = Field(250.0, ge=0.0, le=1000.0, description="Weight per disrupted baseline assignment")
    persist_optimized_schedule: bool = Field(False, description="Whether to persist the optimized assignments to the database")












