import math
from typing import Optional, Sequence, Union, Dict, Any, Tuple

from app.models.job import Job
from app.models.technician import Technician
from app.schemas.job import JobResponse
from app.schemas.technician import TechnicianResponse
from app.scheduling.schemas import (
    TravelEstimate,
    ZoneMatchResult,
    GeoEligibilityResult,
)

EARTH_RADIUS_KM = 6371.0
DEFAULT_TRANSIT_SPEED_KMH = 30.0


def validate_coordinates(lat: Any, lng: Any, point_name: str = "Coordinate") -> Tuple[float, float]:
    """
    Validates geographical coordinates within physical limits.
    Latitude must be in [-90.0, 90.0], Longitude in [-180.0, 180.0].
    Raises ValueError on non-numeric, NaN, or out-of-range values.
    """
    if lat is None or lng is None:
        raise ValueError(f"{point_name} latitude and longitude cannot be None.")

    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        raise ValueError(f"{point_name} coordinates must be valid floating point numbers: got ({lat}, {lng}).")

    if math.isnan(lat_f) or math.isnan(lng_f) or math.isinf(lat_f) or math.isinf(lng_f):
        raise ValueError(f"{point_name} coordinates cannot be NaN or Infinite: got ({lat}, {lng}).")

    if not (-90.0 <= lat_f <= 90.0):
        raise ValueError(f"{point_name} latitude must be between -90.0 and 90.0 degrees: got {lat_f}.")

    if not (-180.0 <= lng_f <= 180.0):
        raise ValueError(f"{point_name} longitude must be between -180.0 and 180.0 degrees: got {lng_f}.")

    return lat_f, lng_f


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Computes deterministic great-circle distance between two geographic points using Haversine formula.
    Radius of Earth R = 6371.0 km.
    Returns distance in kilometers.
    """
    lat1_f, lng1_f = validate_coordinates(lat1, lng1, "Origin")
    lat2_f, lng2_f = validate_coordinates(lat2, lng2, "Destination")

    phi1 = math.radians(lat1_f)
    phi2 = math.radians(lat2_f)
    delta_phi = math.radians(lat2_f - lat1_f)
    delta_lambda = math.radians(lng2_f - lng1_f)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    # Numerical clamp to prevent domain errors
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance_km = EARTH_RADIUS_KM * c
    return round(distance_km, 4)


def calculate_travel_minutes(distance_km: float, speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH) -> float:
    """
    Estimates transit duration in minutes at assumed average velocity.
    Formula: travel_minutes = (distance_km / speed_kmh) * 60.0.
    """
    if distance_km < 0:
        raise ValueError(f"Distance cannot be negative: got {distance_km} km.")
    if speed_kmh <= 0:
        raise ValueError(f"Transit speed must be strictly positive: got {speed_kmh} km/h.")

    minutes = (distance_km / speed_kmh) * 60.0
    return round(minutes, 2)


def check_zone_eligibility(
    job_zone_id: Optional[str],
    eligible_zones: Sequence[str],
    technician_id: str = "",
    technician_name: Optional[str] = None,
    home_zone_id: Optional[str] = None,
) -> ZoneMatchResult:
    """
    Validates whether the job zone falls within technician's certified operational territory.
    Home zone is inherently permissible if specified.
    """
    if not job_zone_id or not job_zone_id.strip():
        return ZoneMatchResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_eligible=True,
            job_zone_id=job_zone_id,
            eligible_zones=list(eligible_zones or []),
            home_zone_id=home_zone_id,
            rejection_reason=None,
        )

    target_zone = job_zone_id.strip().upper()
    tech_zones = {z.strip().upper() for z in (eligible_zones or []) if z and z.strip()}
    if home_zone_id and home_zone_id.strip():
        tech_zones.add(home_zone_id.strip().upper())

    tech_display = f"Technician {technician_name or technician_id}"

    if target_zone not in tech_zones:
        reason = (
            f"{tech_display} is not certified for job zone '{job_zone_id}'. "
            f"Eligible operational zones: {list(eligible_zones or [])} (Home zone: {home_zone_id or 'none'})."
        )
        return ZoneMatchResult(
            technician_id=technician_id,
            technician_name=technician_name,
            is_eligible=False,
            job_zone_id=job_zone_id,
            eligible_zones=list(eligible_zones or []),
            home_zone_id=home_zone_id,
            rejection_reason=reason,
        )

    return ZoneMatchResult(
        technician_id=technician_id,
        technician_name=technician_name,
        is_eligible=True,
        job_zone_id=job_zone_id,
        eligible_zones=list(eligible_zones or []),
        home_zone_id=home_zone_id,
        rejection_reason=None,
    )


def calculate_home_to_job_travel(
    technician: Union[Technician, TechnicianResponse, Dict[str, Any]],
    job: Union[Job, JobResponse, Dict[str, Any]],
    speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH,
) -> TravelEstimate:
    """
    Calculates deterministic Haversine distance and transit duration for technician's first job
    originating from their home base coordinates.
    """
    if isinstance(technician, dict):
        t_id = technician.get("id", "")
        t_lat = technician.get("home_lat")
        t_lng = technician.get("home_lng")
        if t_lat is None or t_lng is None:
            home_loc = technician.get("home_location") or {}
            t_lat = home_loc.get("lat")
            t_lng = home_loc.get("lng")
    else:
        t_id = getattr(technician, "id", "")
        t_lat = getattr(technician, "home_lat", None)
        t_lng = getattr(technician, "home_lng", None)
        if t_lat is None or t_lng is None:
            home_loc = getattr(technician, "home_location", None)
            if home_loc:
                t_lat = getattr(home_loc, "lat", None)
                t_lng = getattr(home_loc, "lng", None)

    if isinstance(job, dict):
        j_id = job.get("id", "")
        j_lat = job.get("lat")
        j_lng = job.get("lng")
    else:
        j_id = getattr(job, "id", "")
        j_lat = getattr(job, "lat", None)
        j_lng = getattr(job, "lng", None)

    dist_km = haversine_distance(t_lat, t_lng, j_lat, j_lng)
    travel_mins = calculate_travel_minutes(dist_km, speed_kmh=speed_kmh)

    return TravelEstimate(
        origin_type="home",
        origin_id=t_id,
        origin_lat=t_lat,
        origin_lng=t_lng,
        destination_job_id=j_id,
        destination_lat=j_lat,
        destination_lng=j_lng,
        distance_km=dist_km,
        travel_minutes=travel_mins,
        speed_kmh=speed_kmh,
    )


def calculate_inter_job_travel(
    from_job: Union[Job, JobResponse, Dict[str, Any]],
    to_job: Union[Job, JobResponse, Dict[str, Any]],
    speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH,
) -> TravelEstimate:
    """
    Calculates deterministic transit distance and travel duration between two consecutive jobs.
    """
    if isinstance(from_job, dict):
        from_id = from_job.get("id", "")
        from_lat = from_job.get("lat")
        from_lng = from_job.get("lng")
    else:
        from_id = getattr(from_job, "id", "")
        from_lat = getattr(from_job, "lat", None)
        from_lng = getattr(from_job, "lng", None)

    if isinstance(to_job, dict):
        to_id = to_job.get("id", "")
        to_lat = to_job.get("lat")
        to_lng = to_job.get("lng")
    else:
        to_id = getattr(to_job, "id", "")
        to_lat = getattr(to_job, "lat", None)
        to_lng = getattr(to_job, "lng", None)

    dist_km = haversine_distance(from_lat, from_lng, to_lat, to_lng)
    travel_mins = calculate_travel_minutes(dist_km, speed_kmh=speed_kmh)

    return TravelEstimate(
        origin_type="job",
        origin_id=from_id,
        origin_lat=from_lat,
        origin_lng=from_lng,
        destination_job_id=to_id,
        destination_lat=to_lat,
        destination_lng=to_lng,
        distance_km=dist_km,
        travel_minutes=travel_mins,
        speed_kmh=speed_kmh,
    )


def evaluate_geographic_eligibility(
    technician: Union[Technician, TechnicianResponse, Dict[str, Any]],
    job: Union[Job, JobResponse, Dict[str, Any]],
    previous_job: Optional[Union[Job, JobResponse, Dict[str, Any]]] = None,
    speed_kmh: float = DEFAULT_TRANSIT_SPEED_KMH,
) -> GeoEligibilityResult:
    """
    Evaluates both zone eligibility and travel metrics.
    If previous_job is provided, computes consecutive inter-job travel; otherwise computes home-to-job transit.
    """
    if isinstance(technician, dict):
        t_id = technician.get("id", "")
        t_name = technician.get("name", t_id)
        t_zones = technician.get("eligible_zones", [])
        t_home_zone = technician.get("home_zone_id")
    else:
        t_id = getattr(technician, "id", "")
        t_name = getattr(technician, "name", t_id)
        t_zones = getattr(technician, "eligible_zones", []) or []
        t_home_zone = getattr(technician, "home_zone_id", None)

    if isinstance(job, dict):
        j_id = job.get("id", "")
        j_zone = job.get("zone_id")
    else:
        j_id = getattr(job, "id", "")
        j_zone = getattr(job, "zone_id", None)

    # 1. Zone Certification Check
    zone_match = check_zone_eligibility(
        job_zone_id=j_zone,
        eligible_zones=t_zones,
        technician_id=t_id,
        technician_name=t_name,
        home_zone_id=t_home_zone,
    )

    # 2. Transit Travel Calculation
    travel_est: Optional[TravelEstimate] = None
    dist_km: Optional[float] = None
    travel_mins: Optional[float] = None

    try:
        if previous_job is not None:
            travel_est = calculate_inter_job_travel(from_job=previous_job, to_job=job, speed_kmh=speed_kmh)
        else:
            travel_est = calculate_home_to_job_travel(technician=technician, job=job, speed_kmh=speed_kmh)

        dist_km = travel_est.distance_km
        travel_mins = travel_est.travel_minutes
    except Exception as e:
        # If coordinates are invalid, record failure
        return GeoEligibilityResult(
            technician_id=t_id,
            technician_name=t_name,
            job_id=j_id,
            is_eligible=False,
            zone_match=zone_match,
            travel_estimate=None,
            distance_km=None,
            travel_minutes=None,
            rejection_reason=f"Geographical calculation error: {str(e)}",
        )

    is_eligible = zone_match.is_eligible
    rejection = zone_match.rejection_reason if not is_eligible else None

    return GeoEligibilityResult(
        technician_id=t_id,
        technician_name=t_name,
        job_id=j_id,
        is_eligible=is_eligible,
        zone_match=zone_match,
        travel_estimate=travel_est,
        distance_km=dist_km,
        travel_minutes=travel_mins,
        rejection_reason=rejection,
    )
