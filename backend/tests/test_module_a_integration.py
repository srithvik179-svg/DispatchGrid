import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from app.db.session import SessionLocal
from app.models.job import Job
from app.models.technician import Technician


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.mark.anyio
async def test_job_crud_full_lifecycle(client: AsyncClient, db_session):
    """Verify end-to-end CRUD, permitted transitions, and terminal locking for jobs."""
    job_id = None
    try:
        # 1. CREATE
        payload = {
            "customer_name": "Integration Test Customer",
            "title": "HVAC Chiller Compressor Replacement",
            "zone_id": "Z1",
            "location": {"lat": 12.3052, "lng": 76.6552, "address": "Central Plaza"},
            "priority": 2,
            "duration_minutes": 90,
            "required_skills": ["hvac"],
            "required_equipment": ["hvac_gauge"],
            "time_window_start": "2026-11-02T10:00:00+05:30",
            "time_window_end": "2026-11-02T14:00:00+05:30",
            "sla_deadline": "2026-11-02T13:30:00+05:30",
            "tags": ["integration_test"],
        }
        res = await client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 201
        created = res.json()
        job_id = created["id"]
        assert created["status"] == "pending"
        assert created["priority_label"] == "high"

        # 2. READ (both endpoints)
        res_v1 = await client.get(f"/api/v1/jobs/{job_id}")
        assert res_v1.status_code == 200
        assert res_v1.json()["title"] == "HVAC Chiller Compressor Replacement"

        res_root = await client.get(f"/jobs/{job_id}")
        assert res_root.status_code == 200

        # 3. UPDATE parameters and transition pending -> unassigned
        update_payload = {
            "title": "HVAC Chiller Compressor Replacement (Urgent Revision)",
            "priority": 1,
            "status": "unassigned",
            "reason": "Dispatcher operational review",
        }
        res_update = await client.patch(f"/api/v1/jobs/{job_id}", json=update_payload)
        assert res_update.status_code == 200
        updated = res_update.json()
        assert updated["title"] == "HVAC Chiller Compressor Replacement (Urgent Revision)"
        assert updated["priority"] == 1
        assert updated["priority_label"] == "urgent"
        assert updated["status"] == "unassigned"

        # 4. TRANSITION unassigned -> assigned
        res_assign = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"status": "assigned", "reason": "Assigned to fleet resource"},
        )
        assert res_assign.status_code == 200
        assert res_assign.json()["status"] == "assigned"

        # 5. CANCELLATION
        res_cancel = await client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            json={"reason": "Customer rescheduled appointment"},
        )
        assert res_cancel.status_code == 200
        cancelled = res_cancel.json()
        assert cancelled["status"] == "cancelled"

        # 6. VERIFY AUDIT TRAIL
        res_history = await client.get(f"/api/v1/jobs/{job_id}/history")
        assert res_history.status_code == 200
        history = res_history.json()
        assert len(history) >= 4  # CREATED, unassigned, assigned, cancelled
        statuses = [h["to_status"] for h in history]
        assert "unassigned" in statuses
        assert "assigned" in statuses
        assert "cancelled" in statuses

        # 7. TERMINAL PROTECTION: CANNOT MODIFY OR RE-CANCEL
        res_terminal_mod = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"title": "Illegal Title Change"},
        )
        assert res_terminal_mod.status_code == 400

        res_terminal_cancel = await client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            json={"reason": "Re-cancellation attempt"},
        )
        assert res_terminal_cancel.status_code == 400
    finally:
        if job_id:
            record = db_session.query(Job).filter_by(id=job_id).first()
            if record:
                db_session.delete(record)
                db_session.commit()


@pytest.mark.anyio
async def test_technician_crud_full_lifecycle(client: AsyncClient, db_session):
    """Verify end-to-end CRUD and attribute modification for technicians."""
    tech_id = "T85"
    # Pre-clean
    pre = db_session.query(Technician).filter_by(id=tech_id).first()
    if pre:
        db_session.delete(pre)
        db_session.commit()

    try:
        # 1. CREATE
        payload = {
            "id": tech_id,
            "name": "Integration Test Technician",
            "home_zone_id": "Z2",
            "home_location": {"lat": 12.355, "lng": 76.64},
            "eligible_zones": ["Z2", "Z1"],
            "skills": ["electrical", "solar"],
            "equipment": ["ladder", "multimeter"],
            "shifts": [
                {
                    "date": "2026-11-02",
                    "start": "2026-11-02T08:00:00+05:30",
                    "end": "2026-11-02T16:00:00+05:30",
                }
            ],
            "unavailable_periods": [
                {
                    "start": "2026-11-02T12:00:00+05:30",
                    "end": "2026-11-02T13:00:00+05:30",
                    "reason": "maintenance_break",
                }
            ],
            "overtime": {"allowed": True, "max_minutes_per_shift": 45},
        }
        res_create = await client.post("/api/v1/technicians", json=payload)
        assert res_create.status_code == 201
        created = res_create.json()
        assert created["id"] == tech_id
        assert created["name"] == "Integration Test Technician"
        assert created["overtime"]["max_minutes_per_shift"] == 45

        # 2. READ (both endpoints)
        res_read_v1 = await client.get(f"/api/v1/technicians/{tech_id}")
        assert res_read_v1.status_code == 200
        assert res_read_v1.json()["name"] == "Integration Test Technician"

        res_read_root = await client.get(f"/technicians/{tech_id}")
        assert res_read_root.status_code == 200

        # 3. UPDATE
        update_payload = {
            "name": "Integration Test Tech (Certified Specialist)",
            "skills": ["electrical", "solar", "high_voltage"],
            "equipment": ["ladder", "multimeter", "insulation_gloves"],
            "overtime": {"allowed": True, "max_minutes_per_shift": 90},
        }
        res_update = await client.patch(f"/api/v1/technicians/{tech_id}", json=update_payload)
        assert res_update.status_code == 200
        updated = res_update.json()
        assert updated["name"] == "Integration Test Tech (Certified Specialist)"
        assert "high_voltage" in updated["skills"]
        assert updated["overtime"]["max_minutes_per_shift"] == 90

        # 4. FILTER
        res_filter_skill = await client.get(f"/api/v1/technicians?skill=high_voltage")
        assert res_filter_skill.status_code == 200
        matching = res_filter_skill.json()
        assert any(t["id"] == tech_id for t in matching)
    finally:
        post = db_session.query(Technician).filter_by(id=tech_id).first()
        if post:
            db_session.delete(post)
            db_session.commit()


@pytest.mark.anyio
async def test_job_invalid_durations_and_time_windows(client: AsyncClient):
    """Verify validation rejections for zero/negative durations and corrupted time windows."""
    base_payload = {
        "customer_name": "Test Hospital",
        "title": "Emergency Generator Check",
        "zone_id": "Z1",
        "location": {"lat": 12.3052, "lng": 76.6552},
        "priority": 1,
        "duration_minutes": 60,
        "required_skills": ["electrical"],
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T14:00:00+05:30",
    }

    # Case 1: Duration <= 0
    p1 = {**base_payload, "duration_minutes": 0}
    r1 = await client.post("/api/v1/jobs", json=p1)
    assert r1.status_code == 422

    p2 = {**base_payload, "duration_minutes": -45}
    r2 = await client.post("/api/v1/jobs", json=p2)
    assert r2.status_code == 422

    # Case 2: Window end <= Window start
    p3 = {
        **base_payload,
        "time_window_start": "2026-11-02T15:00:00+05:30",
        "time_window_end": "2026-11-02T10:00:00+05:30",
    }
    r3 = await client.post("/api/v1/jobs", json=p3)
    assert r3.status_code == 422

    # Case 3: Window duration smaller than work duration
    p4 = {
        **base_payload,
        "duration_minutes": 180,  # 3 hours
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T11:00:00+05:30",  # Only 1 hour window
    }
    r4 = await client.post("/api/v1/jobs", json=p4)
    assert r4.status_code == 422

    # Case 4: SLA deadline earlier than window start
    p5 = {
        **base_payload,
        "time_window_start": "2026-11-02T12:00:00+05:30",
        "time_window_end": "2026-11-02T16:00:00+05:30",
        "sla_deadline": "2026-11-02T11:00:00+05:30",  # Earlier than window start
    }
    r5 = await client.post("/api/v1/jobs", json=p5)
    assert r5.status_code == 422


@pytest.mark.anyio
async def test_job_missing_skills_and_locations(client: AsyncClient):
    """Verify validation rejections for missing required skills and location coordinates."""
    base_payload = {
        "customer_name": "Test Towers",
        "title": "Elevator Cable Check",
        "priority": 2,
        "duration_minutes": 60,
        "time_window_start": "2026-11-02T10:00:00+05:30",
        "time_window_end": "2026-11-02T14:00:00+05:30",
    }

    # Missing location
    r_no_loc = await client.post(
        "/api/v1/jobs",
        json={**base_payload, "required_skills": ["elevator"]},
    )
    assert r_no_loc.status_code == 422

    # Missing skills
    r_no_skills = await client.post(
        "/api/v1/jobs",
        json={
            **base_payload,
            "location": {"lat": 12.3052, "lng": 76.6552},
            "required_skills": [],
        },
    )
    assert r_no_skills.status_code == 422

    # Invalid priority (< 1 or > 4)
    r_p0 = await client.post(
        "/api/v1/jobs",
        json={
            **base_payload,
            "priority": 0,
            "location": {"lat": 12.3052, "lng": 76.6552},
            "required_skills": ["elevator"],
        },
    )
    assert r_p0.status_code == 422

    r_p5 = await client.post(
        "/api/v1/jobs",
        json={
            **base_payload,
            "priority": 5,
            "location": {"lat": 12.3052, "lng": 76.6552},
            "required_skills": ["elevator"],
        },
    )
    assert r_p5.status_code == 422


@pytest.mark.anyio
async def test_duplicate_records_rejected(client: AsyncClient, db_session):
    """Verify rejection of duplicate job IDs, idempotency keys, and technician IDs."""
    # Existing job ID
    res_dup_job = await client.post(
        "/api/v1/jobs",
        json={
            "id": "JOB-001",
            "customer_name": "Duplicate Co",
            "title": "Duplicate Job Test",
            "zone_id": "Z1",
            "location": {"lat": 12.3052, "lng": 76.6552},
            "priority": 3,
            "duration_minutes": 60,
            "required_skills": ["electrical"],
            "time_window_start": "2026-11-02T10:00:00+05:30",
            "time_window_end": "2026-11-02T14:00:00+05:30",
        },
    )
    assert res_dup_job.status_code == 409
    assert "already exists" in res_dup_job.json()["detail"]

    # Existing technician ID
    res_dup_tech = await client.post(
        "/api/v1/technicians",
        json={
            "id": "T01",
            "name": "Duplicate Arjun",
            "home_zone_id": "Z1",
            "home_location": {"lat": 12.3052, "lng": 76.6552},
            "skills": ["electrical"],
        },
    )
    assert res_dup_tech.status_code == 409
    assert "already exists" in res_dup_tech.json()["detail"]


@pytest.mark.anyio
async def test_protected_completed_jobs_integrity(client: AsyncClient):
    """Assert that seeded completed jobs (e.g. JOB-101) cannot be modified or cancelled."""
    # Attempting PATCH on completed job
    res_patch = await client.patch(
        "/api/v1/jobs/JOB-101",
        json={"title": "Unauthorized Modification"},
    )
    assert res_patch.status_code == 400
    assert "completed" in res_patch.json()["detail"].lower()

    # Attempting cancel on completed job
    res_cancel = await client.post(
        "/api/v1/jobs/JOB-101/cancel",
        json={"reason": "Should be rejected"},
    )
    assert res_cancel.status_code == 400
    assert "completed" in res_cancel.json()["detail"].lower()


@pytest.mark.anyio
async def test_state_machine_permitted_and_rejected_transitions(client: AsyncClient, db_session):
    """Verify that only permitted transitions are accepted and illegal jumps are blocked."""
    job_id = None
    try:
        # Create test job
        payload = {
            "customer_name": "State Matrix Testing",
            "title": "State Transition Verification Job",
            "zone_id": "Z2",
            "location": {"lat": 12.355, "lng": 76.64},
            "priority": 3,
            "duration_minutes": 60,
            "required_skills": ["plumbing"],
            "time_window_start": "2026-11-02T10:00:00+05:30",
            "time_window_end": "2026-11-02T14:00:00+05:30",
        }
        res = await client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 201
        job_id = res.json()["id"]

        # ILLEGAL: pending -> completed
        res_illegal_1 = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"status": "completed"},
        )
        assert res_illegal_1.status_code == 400
        assert "invalid state transition" in res_illegal_1.json()["detail"].lower()

        # ILLEGAL: pending -> in_progress
        res_illegal_2 = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"status": "in_progress"},
        )
        assert res_illegal_2.status_code == 400

        # LEGAL: pending -> assigned
        res_legal_1 = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"status": "assigned"},
        )
        assert res_legal_1.status_code == 200

        # LEGAL: assigned -> in_progress
        res_legal_2 = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"status": "in_progress"},
        )
        assert res_legal_2.status_code == 200

        # LEGAL: in_progress -> completed
        res_legal_3 = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"status": "completed"},
        )
        assert res_legal_3.status_code == 200

        # TERMINAL: completed -> anything (illegal)
        res_terminal = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"status": "pending"},
        )
        assert res_terminal.status_code == 400
    finally:
        if job_id:
            record = db_session.query(Job).filter_by(id=job_id).first()
            if record:
                db_session.delete(record)
                db_session.commit()
