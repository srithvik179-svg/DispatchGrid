import pytest
from httpx import AsyncClient
from app.db.session import SessionLocal
from app.models.technician import Technician


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.mark.anyio
async def test_get_technicians_list(client: AsyncClient):
    """Verify that seeded technicians can be retrieved via both API routes."""
    # Test versioned endpoint
    response = await client.get("/api/v1/technicians")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 20

    # Test root endpoint
    root_res = await client.get("/technicians")
    assert root_res.status_code == 200
    assert len(root_res.json()) >= 20

    # Verify technician profile structure
    first_tech = data[0]
    assert "id" in first_tech
    assert "name" in first_tech
    assert "skills" in first_tech
    assert "equipment" in first_tech
    assert "shifts" in first_tech
    assert "home_location" in first_tech
    assert "overtime" in first_tech


@pytest.mark.anyio
async def test_get_technician_by_id(client: AsyncClient):
    """Verify retrieving a single technician profile with operational data."""
    response = await client.get("/api/v1/technicians/T01")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == "T01"
    assert data["name"] == "Arjun Rao"
    assert data["home_zone_id"] == "Z1"
    assert data["home_location"]["lat"] == 12.3052
    assert data["home_location"]["lng"] == 76.6552
    assert "electrical" in data["skills"]
    assert "ladder" in data["equipment"]
    assert "Z1" in data["eligible_zones"]
    assert len(data["shifts"]) == 2
    assert data["overtime"]["allowed"] is True
    assert data["overtime"]["max_minutes_per_shift"] == 60


@pytest.mark.anyio
async def test_get_technician_not_found(client: AsyncClient):
    """Verify 404 response when querying a non-existent technician ID."""
    response = await client.get("/api/v1/technicians/T999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.anyio
async def test_create_technician_success(client: AsyncClient, db_session):
    """Verify registering a new technician with full operational parameters."""
    payload = {
        "name": "Kavita Krishnan",
        "home_zone_id": "Z3",
        "home_location": {
            "lat": 12.2535,
            "lng": 76.6514,
        },
        "eligible_zones": ["Z3", "Z4"],
        "skills": ["networking", "security_hardware"],
        "equipment": ["fiber_splicer", "multimeter"],
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
                "reason": "lunch_break",
            }
        ],
        "overtime": {
            "allowed": True,
            "max_minutes_per_shift": 90,
        },
    }

    created_id = None
    try:
        response = await client.post("/api/v1/technicians", json=payload)
        assert response.status_code == 201
        created = response.json()
        created_id = created["id"]

        assert created["name"] == "Kavita Krishnan"
        assert created["id"].startswith("T")
        assert created["home_zone_id"] == "Z3"
        assert created["skills"] == ["networking", "security_hardware"]
        assert created["equipment"] == ["fiber_splicer", "multimeter"]
        assert len(created["shifts"]) == 1
        assert len(created["unavailable_periods"]) == 1
        assert created["overtime"]["allowed"] is True
        assert created["overtime"]["max_minutes_per_shift"] == 90

        # Verify technician persists and can be retrieved directly
        get_res = await client.get(f"/api/v1/technicians/{created_id}")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Kavita Krishnan"
    finally:
        if created_id:
            record = db_session.query(Technician).filter_by(id=created_id).first()
            if record:
                db_session.delete(record)
                db_session.commit()


@pytest.mark.anyio
async def test_create_technician_with_custom_id(client: AsyncClient, db_session):
    """Verify registering a technician with an explicitly specified unique ID."""
    custom_id = "T77"

    # Pre-clean just in case
    existing = db_session.query(Technician).filter_by(id=custom_id).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    payload = {
        "id": custom_id,
        "name": "Sunil Shetty",
        "home_zone_id": "Z2",
        "home_lat": 12.355,
        "home_lng": 76.64,
        "eligible_zones": ["Z2"],
        "skills": ["plumbing"],
        "equipment": ["pipe_wrench"],
        "shifts": [
            {
                "date": "2026-11-02",
                "start": "2026-11-02T09:00:00+05:30",
                "end": "2026-11-02T17:00:00+05:30",
            }
        ],
    }

    try:
        response = await client.post("/technicians", json=payload)
        assert response.status_code == 201
        assert response.json()["id"] == custom_id
    finally:
        record = db_session.query(Technician).filter_by(id=custom_id).first()
        if record:
            db_session.delete(record)
            db_session.commit()


@pytest.mark.anyio
async def test_create_technician_duplicate_id_prevented(client: AsyncClient):
    """Verify duplicate technician IDs are rejected with HTTP 409 Conflict."""
    payload = {
        "id": "T01",  # Existing seeded technician
        "name": "Duplicate Arjun",
        "home_zone_id": "Z1",
        "home_location": {"lat": 12.3052, "lng": 76.6552},
        "skills": ["electrical"],
    }

    response = await client.post("/api/v1/technicians", json=payload)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.anyio
async def test_create_technician_invalid_shift_rejected(client: AsyncClient):
    """Verify invalid shift where end <= start is rejected."""
    payload = {
        "name": "Invalid Shift Tech",
        "home_zone_id": "Z1",
        "home_location": {"lat": 12.3052, "lng": 76.6552},
        "shifts": [
            {
                "date": "2026-11-02",
                "start": "2026-11-02T18:00:00+05:30",
                "end": "2026-11-02T09:00:00+05:30",  # End before start
            }
        ],
    }

    response = await client.post("/api/v1/technicians", json=payload)
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_technician_missing_location_rejected(client: AsyncClient):
    """Verify registering technician without home location coordinates is rejected."""
    payload = {
        "name": "No Coordinates Tech",
        "skills": ["electrical"],
    }

    response = await client.post("/api/v1/technicians", json=payload)
    assert response.status_code == 422


@pytest.mark.anyio
async def test_filter_technicians_by_zone_and_skill(client: AsyncClient):
    """Verify filtering technician fleet by zone and skill."""
    # Filter by zone Z1
    z_res = await client.get("/api/v1/technicians?zone=Z1")
    assert z_res.status_code == 200
    z_techs = z_res.json()
    assert len(z_techs) > 0
    for t in z_techs:
        assert t["home_zone_id"] == "Z1" or "Z1" in t["eligible_zones"]

    # Filter by skill electrical
    s_res = await client.get("/api/v1/technicians?skill=electrical")
    assert s_res.status_code == 200
    s_techs = s_res.json()
    assert len(s_techs) > 0
    for t in s_techs:
        assert any(sk.lower() == "electrical" for sk in t["skills"])


@pytest.mark.anyio
async def test_update_technician_success(client: AsyncClient, db_session):
    """Verify modifying technician skills, equipment, and overtime policy."""
    # Create temporary technician to update
    custom_id = "T89"
    pre = db_session.query(Technician).filter_by(id=custom_id).first()
    if pre:
        db_session.delete(pre)
        db_session.commit()

    create_payload = {
        "id": custom_id,
        "name": "Original Name",
        "home_zone_id": "Z1",
        "home_lat": 12.3052,
        "home_lng": 76.6552,
        "skills": ["electrical"],
        "equipment": ["ladder"],
    }
    await client.post("/api/v1/technicians", json=create_payload)

    try:
        update_payload = {
            "name": "Updated Name",
            "skills": ["electrical", "solar", "hvac"],
            "equipment": ["ladder", "multimeter", "hvac_gauge"],
            "overtime": {
                "allowed": True,
                "max_minutes_per_shift": 120,
            },
        }
        res = await client.patch(f"/api/v1/technicians/{custom_id}", json=update_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Updated Name"
        assert set(data["skills"]) == {"electrical", "solar", "hvac"}
        assert set(data["equipment"]) == {"ladder", "multimeter", "hvac_gauge"}
        assert data["overtime"]["allowed"] is True
        assert data["overtime"]["max_minutes_per_shift"] == 120
    finally:
        post = db_session.query(Technician).filter_by(id=custom_id).first()
        if post:
            db_session.delete(post)
            db_session.commit()


@pytest.mark.anyio
async def test_update_technician_not_found(client: AsyncClient):
    """Verify 404 response when updating non-existent technician."""
    res = await client.patch("/api/v1/technicians/T999", json={"name": "Ghost Tech"})
    assert res.status_code == 404

