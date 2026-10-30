"""
Phase 25: Travel-Time Optimisation and Geographical Route Refinement Tests.

Verifies:
1. Consistent travel calculations for each technician (home to first job + consecutive inter-job).
2. Zone switch detection and tracking across different operational zones.
3. Travel-time reduction is measured rather than assumed (initial vs optimized metrics).
4. Travel optimization never violates hard operational constraints (zero violations).
5. Pre-existing assignments remain strictly protected.
6. All optimization decisions remain explainable with action rationales.
7. REST API endpoints for travel optimization and fleet metrics.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.technician import Technician
from app.models.job import Job
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.service import SchedulingService
from app.scheduling.algorithm import run_deterministic_initial_scheduler
from app.scheduling.travel_opt import (
    calculate_technician_travel_summary,
    calculate_fleet_travel_breakdown,
    optimize_technician_routes,
    optimize_schedule_travel,
)
from app.scheduling.schemas import (
    AssignedJobPlan,
    TravelLegDetail,
    TechnicianTravelSummary,
    TravelMetricsComparison,
    TravelOptimizationResult,
)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client():
    return TestClient(app)


def test_technician_travel_summary_calculation(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Travel calculations are consistent.
    - Includes travel from home to the first job.
    - Includes travel between consecutive jobs.
    """
    service = SchedulingService(db_session)
    inputs = service.load_inputs()
    res = run_deterministic_initial_scheduler(inputs)

    jobs_lookup = {j.id: JobResponse.model_validate(j) for j in db_session.query(Job).all()}
    t01 = next(t for t in inputs.technicians if t.id == "T01")

    summary = calculate_technician_travel_summary(
        technician=t01,
        assignments=res.assignments,
        jobs_lookup=jobs_lookup,
    )

    assert summary.technician_id == "T01"
    assert summary.job_count == 2
    assert summary.home_to_first_minutes > 0.0
    assert summary.home_to_first_distance_km > 0.0
    assert summary.total_travel_minutes == round(summary.home_to_first_minutes + summary.inter_job_minutes, 2)
    assert len(summary.legs) == 2

    # Leg 1 must be from home
    leg1 = summary.legs[0]
    assert leg1.leg_index == 1
    assert leg1.origin_type == "home"
    assert leg1.origin_id == "T01"
    assert leg1.travel_minutes == summary.home_to_first_minutes

    # Leg 2 must be from job to job
    leg2 = summary.legs[1]
    assert leg2.leg_index == 2
    assert leg2.origin_type == "job"
    assert leg2.travel_minutes == summary.inter_job_minutes


def test_zone_switch_detection(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Reduce unnecessary zone switching.
    - Detect and track transitions across distinct operational zones.
    """
    service = SchedulingService(db_session)
    inputs = service.load_inputs()
    res = run_deterministic_initial_scheduler(inputs)

    jobs_lookup = {j.id: JobResponse.model_validate(j) for j in db_session.query(Job).all()}
    t11 = next(t for t in inputs.technicians if t.id == "T11")

    summary = calculate_technician_travel_summary(
        technician=t11,
        assignments=res.assignments,
        jobs_lookup=jobs_lookup,
    )

    # T11 traverses multiple zones in the initial schedule
    assert summary.zone_switches_count > 0
    switches_found = [leg for leg in summary.legs if leg.is_zone_switch]
    assert len(switches_found) == summary.zone_switches_count
    for leg in switches_found:
        assert leg.origin_zone != leg.destination_zone


def test_travel_optimization_measured_improvement(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Improvement is measured rather than assumed.
    - Compare initial and improved schedules.
    - Travel time reduction is strictly positive.
    """
    service = SchedulingService(db_session)
    opt_result = service.optimize_travel(persist=False)

    comp = opt_result.metrics_comparison
    # Measured reduction
    assert comp.initial_travel_minutes > comp.optimized_travel_minutes
    assert comp.travel_minutes_saved > 0.0
    assert comp.travel_time_reduction_percent > 0.0
    assert comp.distance_km_saved > 0.0
    assert comp.average_travel_per_job_optimized < comp.average_travel_per_job_initial
    assert comp.technicians_improved > 0

    # Concrete check on reduction amount (approx 45+ minutes saved across fleet)
    assert comp.travel_minutes_saved >= 30.0


def test_travel_optimization_hard_constraints_intact(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Travel optimisation never violates hard constraints.
    - Feasibility is strictly preserved (zero violations).
    """
    service = SchedulingService(db_session)
    opt_result = service.optimize_travel(persist=False)

    assert opt_result.is_feasible is True
    assert opt_result.hard_violations_count == 0
    assert len(opt_result.hard_violations) == 0


def test_existing_assignments_protected(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Existing assignments are strictly preserved.
    """
    service = SchedulingService(db_session)
    inputs = service.load_inputs()
    opt_result = service.optimize_travel(persist=False)

    # All 7 existing assignments must be present and unmodified
    existing_in_opt = [p for p in opt_result.assignments if p.is_existing]
    assert len(existing_in_opt) == len(inputs.existing_assignments) == 7

    for base in inputs.existing_assignments:
        match = next((p for p in existing_in_opt if p.job_id == base.job_id), None)
        assert match is not None
        assert match.technician_id == base.technician_id
        assert match.scheduled_start == base.start_time
        assert match.scheduled_end == base.end_time


def test_optimizations_applied_explainable(db_session):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - All decisions remain explainable.
    """
    service = SchedulingService(db_session)
    opt_result = service.optimize_travel(persist=False)

    assert len(opt_result.optimizations_applied) > 0
    for action in opt_result.optimizations_applied:
        assert action.action_type in ["ROUTE_REORDER", "TECHNICIAN_SWAP", "ZONE_CLUSTERING"]
        assert len(action.technician_ids) > 0
        assert len(action.job_ids) > 0
        assert action.travel_minutes_saved > 0.0
        assert len(action.explanation) > 10
        # Verify explanation contains specifics
        assert any(tid in action.explanation for tid in action.technician_ids)


def test_travel_optimization_api_endpoints(test_client):
    """Verify REST API endpoints for travel optimization and fleet metrics."""
    # 1. POST /schedule/optimize/travel
    resp_opt = test_client.post("/api/v1/schedule/optimize/travel", json={"persist": False})
    assert resp_opt.status_code == 200
    opt_data = resp_opt.json()

    assert opt_data["is_feasible"] is True
    assert opt_data["hard_violations_count"] == 0
    assert opt_data["metrics_comparison"]["travel_minutes_saved"] > 0
    assert len(opt_data["optimizations_applied"]) > 0

    # 2. GET /schedule/travel-metrics
    resp_met = test_client.get("/api/v1/schedule/travel-metrics")
    assert resp_met.status_code == 200
    met_data = resp_met.json()

    assert "fleet_metrics" in met_data
    assert "technician_travel" in met_data
    assert met_data["fleet_metrics"]["total_travel_minutes"] > 0
    assert len(met_data["technician_travel"]) == 20
