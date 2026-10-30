"""
Phase 28: Optimization Comparison and Reporting Tests.

Verifies:
1. Accurate calculation and storage of initial schedule metrics.
2. Accurate calculation and storage of optimized schedule metrics.
3. Total travel time comparison and measured savings.
4. SLA penalty and lateness comparison.
5. Unassigned high-priority job comparison (zero fabricated improvements).
6. Overtime work comparison and assignment churn protection.
7. Improvement percentages calculated using clearly defined, documented formulas.
8. Generation and persistent retrieval of optimization reports.
9. Explainable trade-off analysis describing where gains and trade-offs occurred.
10. REST API endpoints for generating, listing, and retrieving reports.
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.technician import Technician
from app.models.job import Job
from app.models.system import SystemMetadata
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.service import SchedulingService
from app.scheduling.algorithm import run_deterministic_initial_scheduler
from app.scheduling.travel_opt import optimize_schedule_travel
from app.scheduling.sla_opt import optimize_schedule_sla
from app.scheduling.reporting import (
    compute_schedule_snapshot,
    calculate_improvement_ratio,
    compare_schedule_metrics,
    generate_optimization_report,
    save_report_to_db,
    load_report_from_db,
    list_reports_from_db,
)
from app.scheduling.schemas import (
    AssignedJobPlan,
    ScheduleSnapshotMetrics,
    MetricComparisonItem,
    TradeOffNarrative,
    OptimizationReport,
    OptimizationReportSummary,
    ObjectiveWeightsConfig,
)

IST = timezone(timedelta(hours=5, minutes=30))


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


def test_unfabricated_improvement_percentages_and_formulas():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    - Calculate improvement percentages using clearly defined formulas.
    - No fabricated improvements: zero delta is strictly UNCHANGED; regression is REGRESSED.
    """
    # 1. Genuine positive improvement (cost reduced)
    pct_imp, dir_imp = calculate_improvement_ratio(initial=100.0, optimized=80.0)
    assert pct_imp == 20.0
    assert dir_imp == "IMPROVED"

    # 2. Zero delta (no improvement fabricated)
    pct_zero, dir_zero = calculate_improvement_ratio(initial=50.0, optimized=50.0)
    assert pct_zero == 0.0
    assert dir_zero == "UNCHANGED"

    # 3. Regression / trade-off (cost increased)
    pct_reg, dir_reg = calculate_improvement_ratio(initial=40.0, optimized=50.0)
    assert pct_reg == -25.0
    assert dir_reg == "REGRESSED"

    # 4. Both zero
    pct_both_zero, dir_both_zero = calculate_improvement_ratio(initial=0.0, optimized=0.0)
    assert pct_both_zero == 0.0
    assert dir_both_zero == "UNCHANGED"

    # 5. Zero baseline to positive value
    pct_zero_base, dir_zero_base = calculate_improvement_ratio(initial=0.0, optimized=10.0)
    assert pct_zero_base == -100.0
    assert dir_zero_base == "REGRESSED"


def test_compute_schedule_snapshot_metrics(db_session):
    """
    TASKS:
    - Store initial schedule metrics.
    - Store optimised schedule metrics.
    """
    service = SchedulingService(db_session)
    as_of = service.get_clock()
    inputs = service.load_inputs()
    initial_res = run_deterministic_initial_scheduler(inputs)

    jobs = [JobResponse.model_validate(j) for j in db_session.query(Job).all()]
    techs = [TechnicianResponse.model_validate(t) for t in db_session.query(Technician).all()]

    snapshot = compute_schedule_snapshot(
        schedule_label="INITIAL",
        run_id="TEST-SNAPSHOT",
        as_of=as_of,
        jobs=jobs,
        technicians=techs,
        assignments=initial_res.assignments,
        baseline_assignments=inputs.existing_assignments,
    )

    assert snapshot.schedule_label == "INITIAL"
    assert snapshot.total_jobs == 108
    assert snapshot.assigned_jobs_count == 88
    assert snapshot.unassigned_jobs_count == 20
    assert snapshot.total_travel_minutes > 800.0
    assert snapshot.average_travel_minutes > 0.0
    assert snapshot.component_sla_penalty >= 0.0
    assert snapshot.objective_total_score > 0.0
    assert snapshot.unassigned_p1_urgent == 3  # 3 unassigned P1 jobs (JOB-014, JOB-035, JOB-093)


def test_compare_all_optimization_metrics(db_session):
    """
    TASKS:
    - Compare total travel time.
    - Compare SLA penalties.
    - Compare unassigned high-priority jobs.
    - Compare overtime.
    - Compare assignment changes.
    """
    service = SchedulingService(db_session)
    as_of = service.get_clock()
    inputs = service.load_inputs()
    jobs = [JobResponse.model_validate(j) for j in db_session.query(Job).all()]
    techs = [TechnicianResponse.model_validate(t) for t in db_session.query(Technician).all()]

    # Initial Schedule
    initial_res = run_deterministic_initial_scheduler(inputs)
    initial_snapshot = compute_schedule_snapshot(
        schedule_label="INITIAL",
        run_id="INIT-RUN",
        as_of=as_of,
        jobs=jobs,
        technicians=techs,
        assignments=initial_res.assignments,
        baseline_assignments=inputs.existing_assignments,
    )

    # Multi-pass Optimized Schedule (Travel 2-opt + SLA pass)
    travel_opt = optimize_schedule_travel(
        initial_assignments=initial_res.assignments,
        technicians=techs,
        jobs=jobs,
        baseline_assignments=inputs.existing_assignments,
        as_of=as_of,
    )
    sla_opt = optimize_schedule_sla(
        initial_assignments=travel_opt.assignments,
        technicians=techs,
        jobs=jobs,
        as_of=as_of,
    )
    optimized_snapshot = compute_schedule_snapshot(
        schedule_label="OPTIMIZED",
        run_id="OPT-RUN",
        as_of=as_of,
        jobs=jobs,
        technicians=techs,
        assignments=sla_opt.assignments,
        baseline_assignments=inputs.existing_assignments,
    )

    comparisons, trade_offs = compare_schedule_metrics(initial_snapshot, optimized_snapshot)
    comp_map = {c.metric_name: c for c in comparisons}

    # 1. Compare total travel time (genuine measured savings)
    travel_comp = comp_map["Total Transit Travel Time"]
    assert travel_comp.initial_value > travel_comp.optimized_value
    assert travel_comp.absolute_delta >= 40.0  # Approx 46+ minutes saved
    assert travel_comp.improvement_percentage > 5.0  # ~5.26%
    assert travel_comp.direction == "IMPROVED"
    assert travel_comp.formula == "((initial_travel - optimized_travel) / initial_travel) * 100%"

    # 2. Compare SLA penalties (transparent trade-off tracking)
    sla_comp = comp_map["SLA Lateness Penalty"]
    assert sla_comp.direction in ["IMPROVED", "UNCHANGED", "REGRESSED"]
    if sla_comp.direction == "REGRESSED":
        assert "deliberate trade-off" in sla_comp.trade_off_explanation

    # 3. Compare unassigned high-priority jobs (no fabricated changes)
    p1_comp = comp_map["Unassigned P1 Urgent Jobs"]
    assert p1_comp.initial_value == 3.0
    assert p1_comp.optimized_value == 3.0
    assert p1_comp.direction == "UNCHANGED"

    # 4. Compare overtime
    ot_comp = comp_map["Total Fleet Overtime"]
    assert ot_comp.dimension == "overtime"

    # 5. Compare assignment changes / churn
    churn_comp = comp_map["Schedule Churn Penalty"]
    assert churn_comp.initial_value == 0.0
    assert churn_comp.optimized_value == 0.0  # Zero baseline locked assignments disrupted

    # 6. Overall Objective Score
    score_comp = comp_map["Total Objective Cost Score J(S)"]
    assert score_comp.initial_value > score_comp.optimized_value
    assert score_comp.direction == "IMPROVED"
    assert score_comp.improvement_percentage > 0.0

    # 7. Trade-off narratives
    assert len(trade_offs) >= 4
    narrative_dims = {t.dimension for t in trade_offs}
    assert "travel" in narrative_dims
    assert "sla" in narrative_dims
    assert "stability" in narrative_dims
    assert "overall" in narrative_dims


def test_generate_and_retrieve_persistent_report(db_session):
    """
    ACCEPTANCE CRITERIA:
    - Generate an optimisation report.
    - Reports are retrievable.
    - Before-and-after metrics are accurate.
    """
    report = generate_optimization_report(
        db=db_session,
        lateness_weight=2.0,
        speed_kmh=30.0,
        persist_optimized_schedule=False,
    )

    assert report.report_id.startswith("REP-OPT-")
    assert report.is_feasible is True
    assert report.hard_constraints_preserved is True
    assert report.overall_travel_saved_minutes >= 40.0
    assert report.overall_score_improvement_percentage > 0.0
    assert len(report.metric_comparisons) >= 8
    assert len(report.trade_off_analysis) >= 4
    assert "Optimization pass completed successfully" in report.executive_summary

    # Retrieval from Database
    retrieved = load_report_from_db(db_session, report.report_id)
    assert retrieved is not None
    assert retrieved.report_id == report.report_id
    assert retrieved.overall_travel_saved_minutes == report.overall_travel_saved_minutes
    assert retrieved.overall_score_improvement_percentage == report.overall_score_improvement_percentage
    assert retrieved.is_feasible == report.is_feasible

    # List reports
    summaries = list_reports_from_db(db_session)
    assert len(summaries) >= 1
    assert any(s.report_id == report.report_id for s in summaries)


def test_optimization_reporting_rest_api_endpoints(test_client):
    """
    ACCEPTANCE CRITERIA:
    - Endpoints respond with valid schemas and accurate report data.
    """
    # 1. POST /api/v1/schedule/reports/generate
    resp_gen = test_client.post(
        "/api/v1/schedule/reports/generate",
        json={"lateness_weight": 2.0, "speed_kmh": 30.0, "persist_optimized_schedule": False},
    )
    assert resp_gen.status_code == 200
    report_data = resp_gen.json()
    report_id = report_data["report_id"]
    assert report_id.startswith("REP-OPT-")
    assert report_data["is_feasible"] is True
    assert report_data["overall_travel_saved_minutes"] > 0.0
    assert "metric_comparisons" in report_data
    assert "trade_off_analysis" in report_data

    # 2. GET /api/v1/schedule/reports
    resp_list = test_client.get("/api/v1/schedule/reports")
    assert resp_list.status_code == 200
    summaries = resp_list.json()
    assert isinstance(summaries, list)
    assert len(summaries) >= 1
    assert any(s["report_id"] == report_id for s in summaries)

    # 3. GET /api/v1/schedule/reports/{report_id}
    resp_get = test_client.get(f"/api/v1/schedule/reports/{report_id}")
    assert resp_get.status_code == 200
    retrieved_data = resp_get.json()
    assert retrieved_data["report_id"] == report_id
    assert retrieved_data["is_feasible"] is True
    assert retrieved_data["overall_travel_saved_minutes"] == report_data["overall_travel_saved_minutes"]

    # 4. GET invalid report returns 404
    resp_invalid = test_client.get("/api/v1/schedule/reports/REP-NONEXISTENT")
    assert resp_invalid.status_code == 404
