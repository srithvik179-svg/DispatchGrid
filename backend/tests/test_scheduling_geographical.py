import math
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.assignment import Assignment
from app.scheduling.geo import (
    validate_coordinates,
    haversine_distance,
    calculate_travel_minutes,
    check_zone_eligibility,
    calculate_home_to_job_travel,
    calculate_inter_job_travel,
    evaluate_geographic_eligibility,
    EARTH_RADIUS_KM,
)
from app.scheduling.service import SchedulingService


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


def test_validate_coordinates_valid():
    """Verify valid coordinates pass within bounds."""
    lat, lng = validate_coordinates(12.3052, 76.6552)
    assert lat == 12.3052
    assert lng == 76.6552

    lat_edge, lng_edge = validate_coordinates(-90.0, 180.0)
    assert lat_edge == -90.0
    assert lng_edge == 180.0


def test_validate_coordinates_invalid():
    """Verify invalid, non-numeric, or out-of-range coordinates are rejected."""
    with pytest.raises(ValueError, match="latitude must be between -90.0 and 90.0"):
        validate_coordinates(95.0, 76.0)

    with pytest.raises(ValueError, match="latitude must be between -90.0 and 90.0"):
        validate_coordinates(-100.0, 76.0)

    with pytest.raises(ValueError, match="longitude must be between -180.0 and 180.0"):
        validate_coordinates(12.0, 190.0)

    with pytest.raises(ValueError, match="cannot be None"):
        validate_coordinates(None, 76.0)

    with pytest.raises(ValueError, match="cannot be NaN or Infinite"):
        validate_coordinates(float("nan"), 76.0)


def test_haversine_distance_deterministic():
    """Verify deterministic Haversine calculations and symmetry."""
    # Same point distance must be 0
    assert haversine_distance(12.3052, 76.6552, 12.3052, 76.6552) == 0.0

    # Symmetry: d(A, B) == d(B, A)
    p1 = (12.3052, 76.6552)
    p2 = (12.25354, 76.65143)
    d1 = haversine_distance(p1[0], p1[1], p2[0], p2[1])
    d2 = haversine_distance(p2[0], p2[1], p1[0], p1[1])
    assert d1 == d2
    assert 5.75 <= d1 <= 5.77


def test_calculate_travel_minutes():
    """Verify transit duration estimation at 30 km/h assumption."""
    # 30 km at 30 km/h = 1 hour = 60 minutes
    assert calculate_travel_minutes(30.0, speed_kmh=30.0) == 60.0
    # 15 km at 30 km/h = 30 minutes
    assert calculate_travel_minutes(15.0, speed_kmh=30.0) == 30.0
    # 0 km = 0 minutes
    assert calculate_travel_minutes(0.0, speed_kmh=30.0) == 0.0

    with pytest.raises(ValueError, match="Distance cannot be negative"):
        calculate_travel_minutes(-5.0)

    with pytest.raises(ValueError, match="speed must be strictly positive"):
        calculate_travel_minutes(10.0, speed_kmh=0.0)


def test_check_zone_eligibility():
    """Verify zone eligibility enforcement with home zone inclusion."""
    # Certified zone match
    res_match = check_zone_eligibility(
        job_zone_id="Z1",
        eligible_zones=["Z1", "Z2"],
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert res_match.is_eligible is True
    assert res_match.rejection_reason is None

    # Home zone match
    res_home_match = check_zone_eligibility(
        job_zone_id="Z3",
        eligible_zones=["Z1"],
        technician_id="T05",
        home_zone_id="Z3",
    )
    assert res_home_match.is_eligible is True

    # Ineligible zone rejection
    res_ineligible = check_zone_eligibility(
        job_zone_id="Z6",
        eligible_zones=["Z1", "Z2"],
        technician_id="T01",
        technician_name="Arjun Rao",
    )
    assert res_ineligible.is_eligible is False
    assert "Arjun Rao is not certified for job zone 'Z6'" in res_ineligible.rejection_reason


def test_calculate_home_to_job_travel(db_session):
    """Verify first-job transit travel calculation from technician home base."""
    service = SchedulingService(db_session)
    estimate = service.calculate_home_travel("T13", "JOB-001")

    assert estimate.origin_type == "home"
    assert estimate.origin_id == "T13"
    assert estimate.destination_job_id == "JOB-001"
    assert estimate.speed_kmh == 30.0
    assert 5.75 <= estimate.distance_km <= 5.77
    assert 11.5 <= estimate.travel_minutes <= 11.6


def test_calculate_inter_job_travel(db_session):
    """Verify transit travel calculation between consecutive jobs."""
    service = SchedulingService(db_session)
    estimate = service.calculate_inter_job_travel("JOB-001", "JOB-002")

    assert estimate.origin_type == "job"
    assert estimate.origin_id == "JOB-001"
    assert estimate.destination_job_id == "JOB-002"
    assert estimate.speed_kmh == 30.0
    assert 1.0 <= estimate.distance_km <= 1.2
    assert 2.0 <= estimate.travel_minutes <= 2.3


def test_evaluate_geographic_eligibility(db_session):
    """Verify combined zone check and travel estimation for compliant vs non-compliant technicians."""
    service = SchedulingService(db_session)

    # T01 has eligible_zones=['Z1', 'Z2'] -> Ineligible for JOB-001 (in Z3)
    geo_t01 = service.get_geo_eligibility("JOB-001", "T01")
    assert geo_t01.is_eligible is False
    assert geo_t01.zone_match.is_eligible is False
    assert "is not certified for job zone 'Z3'" in geo_t01.rejection_reason

    # T13 has eligible_zones=['Z3', 'Z1'] -> Eligible for JOB-001 (in Z3)
    geo_t13 = service.get_geo_eligibility("JOB-001", "T13")
    assert geo_t13.is_eligible is True
    assert geo_t13.zone_match.is_eligible is True
    assert geo_t13.distance_km is not None
    assert geo_t13.travel_minutes is not None
    assert geo_t13.rejection_reason is None


def test_api_travel_estimate(test_client):
    """Test POST /api/v1/scheduling/travel/estimate endpoint."""
    payload = {
        "origin_lat": 12.3052,
        "origin_lng": 76.6552,
        "destination_lat": 12.25354,
        "destination_lng": 76.65143,
        "speed_kmh": 30.0,
    }
    resp = test_client.post("/api/v1/scheduling/travel/estimate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert 5.75 <= data["distance_km"] <= 5.77
    assert 11.5 <= data["travel_minutes"] <= 11.6
    assert data["speed_kmh"] == 30.0

    # Invalid coordinates payload
    bad_payload = {
        "origin_lat": 95.0,
        "origin_lng": 76.6552,
        "destination_lat": 12.25354,
        "destination_lng": 76.65143,
    }
    resp_bad = test_client.post("/api/v1/scheduling/travel/estimate", json=bad_payload)
    assert resp_bad.status_code == 422


def test_api_home_to_job_travel(test_client):
    """Test GET /api/v1/scheduling/travel/home-to-job endpoint."""
    resp = test_client.get("/api/v1/scheduling/travel/home-to-job?technician_id=T13&job_id=JOB-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["origin_type"] == "home"
    assert data["origin_id"] == "T13"
    assert data["destination_job_id"] == "JOB-001"
    assert 5.75 <= data["distance_km"] <= 5.77

    # Non-existent technician
    resp_404 = test_client.get("/api/v1/scheduling/travel/home-to-job?technician_id=T99&job_id=JOB-001")
    assert resp_404.status_code == 404


def test_api_inter_job_travel(test_client):
    """Test GET /api/v1/scheduling/travel/inter-job endpoint."""
    resp = test_client.get("/api/v1/scheduling/travel/inter-job?from_job_id=JOB-001&to_job_id=JOB-002")
    assert resp.status_code == 200
    data = resp.json()
    assert data["origin_type"] == "job"
    assert data["origin_id"] == "JOB-001"
    assert data["destination_job_id"] == "JOB-002"
    assert data["distance_km"] > 0


def test_api_geo_eligibility(test_client):
    """Test GET /api/v1/scheduling/geo-eligibility endpoint."""
    resp_ineligible = test_client.get("/api/v1/scheduling/geo-eligibility?technician_id=T01&job_id=JOB-001")
    assert resp_ineligible.status_code == 200
    data_ineligible = resp_ineligible.json()
    assert data_ineligible["is_eligible"] is False
    assert "is not certified for job zone 'Z3'" in data_ineligible["rejection_reason"]

    resp_eligible = test_client.get("/api/v1/scheduling/geo-eligibility?technician_id=T13&job_id=JOB-001")
    assert resp_eligible.status_code == 200
    data_eligible = resp_eligible.json()
    assert data_eligible["is_eligible"] is True
    assert data_eligible["distance_km"] is not None
    assert data_eligible["travel_minutes"] is not None


def test_existing_scheduling_features_unaffected(test_client, db_session):
    """Verify pre-existing assignments and run initialization remain completely intact."""
    initial_assignment_count = db_session.query(Assignment).count()
    assert initial_assignment_count == 7

    resp = test_client.post("/api/v1/scheduling/runs/init")
    assert resp.status_code == 201
    data = resp.json()
    assert data["existing_assignments_preserved"] is True
    assert data["assigned_jobs_count"] == 7
    assert "travel_model" in data["metrics"]
    assert data["metrics"]["travel_model"]["speed_kmh"] == 30

    post_count = db_session.query(Assignment).count()
    assert post_count == initial_assignment_count
