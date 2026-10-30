import pytest
from app.db.session import SessionLocal
from app.services.dataset_loader import DatasetLoaderService
from app.models.technician import Technician
from app.models.job import Job
from app.models.assignment import Assignment
from app.models.disruption import DisruptionScenario
from app.models.zone import Zone
from app.models.system import SystemMetadata


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_dataset_loader_full_import(db_session):
    """Verify that DatasetLoaderService imports all authoritative entities accurately."""
    loader = DatasetLoaderService(db_session)
    stats = loader.load_all()

    assert stats.technicians_imported == 20
    assert stats.jobs_imported == 108
    assert stats.existing_assignments_imported == 7
    assert stats.disruptions_imported == 12
    assert stats.zones_imported == 6
    assert stats.simulation_clock == "2026-11-02T10:00:00+05:30"
    assert len(stats.errors) == 0


def test_technician_records_preserved(db_session):
    """Verify technician count, attributes, skills, equipment, and coordinates."""
    tech_count = db_session.query(Technician).count()
    assert tech_count == 20

    t1 = db_session.query(Technician).filter_by(id="T01").first()
    assert t1 is not None
    assert t1.name == "Arjun Rao"
    assert t1.home_zone_id == "Z1"
    assert t1.home_lat == 12.3052
    assert t1.home_lng == 76.6552
    assert "electrical" in t1.skills
    assert "multimeter" in t1.equipment
    assert len(t1.shifts) == 2
    assert t1.overtime_allowed is True


def test_job_records_and_status_distribution(db_session):
    """Verify job counts and exact lifecycle statuses (100 pending, 4 completed, 3 in progress, 1 cancelled)."""
    jobs = db_session.query(Job).all()
    assert len(jobs) == 108

    pending = [j for j in jobs if j.status == "pending"]
    completed = [j for j in jobs if j.status == "completed"]
    in_progress = [j for j in jobs if j.status == "in_progress"]
    cancelled = [j for j in jobs if j.status == "cancelled"]

    assert len(pending) == 100
    assert len(completed) == 4
    assert len(in_progress) == 3
    assert len(cancelled) == 1

    # Check sample job attributes
    j1 = db_session.query(Job).filter_by(id="JOB-001").first()
    assert j1 is not None
    assert j1.customer_name == "Pioneer Apartments"
    assert j1.priority == 3
    assert j1.priority_label == "medium"
    assert j1.duration_minutes == 45
    assert "networking" in j1.required_skills
    assert "fiber_splicer" in j1.required_equipment


def test_existing_assignments_preserved(db_session):
    """Verify all 7 existing assignments are preserved with their assigned statuses."""
    assignments = db_session.query(Assignment).filter_by(is_existing=True).all()
    assert len(assignments) == 7

    job_ids = {a.job_id for a in assignments}
    assert job_ids == {"JOB-101", "JOB-102", "JOB-103", "JOB-104", "JOB-105", "JOB-106", "JOB-107"}

    # Verify assignments reflect accurately on the job model
    for a in assignments:
        job = db_session.query(Job).filter_by(id=a.job_id).first()
        assert job.assigned_technician_id == a.technician_id
        assert job.status == a.status


def test_disruption_scenarios_available(db_session):
    """Verify all 12 disruption/reliability scenarios are loaded."""
    disruptions = db_session.query(DisruptionScenario).all()
    assert len(disruptions) == 12

    d1 = db_session.query(DisruptionScenario).filter_by(id="D01").first()
    assert d1 is not None
    assert d1.type == "technician_unavailable"
    assert "T11" in d1.payload.get("technician_id", "")


def test_seed_command_idempotency_no_duplicates(db_session):
    """Verify re-running the loader updates in place without duplicating records."""
    initial_jobs = db_session.query(Job).count()
    initial_techs = db_session.query(Technician).count()
    initial_assignments = db_session.query(Assignment).count()
    initial_disruptions = db_session.query(DisruptionScenario).count()

    loader = DatasetLoaderService(db_session)
    stats = loader.load_all()

    assert stats.jobs_imported == 108
    assert stats.records_skipped_or_updated > 0
    assert len(stats.errors) == 0

    assert db_session.query(Job).count() == initial_jobs
    assert db_session.query(Technician).count() == initial_techs
    assert db_session.query(Assignment).count() == initial_assignments
    assert db_session.query(DisruptionScenario).count() == initial_disruptions


def test_system_metadata_clock_synced(db_session):
    """Verify simulation clock is stored in system_metadata."""
    clock_record = db_session.query(SystemMetadata).filter_by(key="as_of").first()
    assert clock_record is not None
    assert clock_record.value == "2026-11-02T10:00:00+05:30"
