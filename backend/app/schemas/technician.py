from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator


class LocationSchema(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude between -90 and 90")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude between -180 and 180")
    address: Optional[str] = Field(None, max_length=255)


class ShiftSchema(BaseModel):
    date: str = Field(..., description="Date formatted as YYYY-MM-DD")
    start: datetime = Field(..., description="Shift starting timestamp with timezone")
    end: datetime = Field(..., description="Shift ending timestamp with timezone")

    @model_validator(mode="after")
    def validate_shift_times(self) -> "ShiftSchema":
        if self.end <= self.start:
            raise ValueError("Shift end must be strictly after shift start")
        return self


class UnavailablePeriodSchema(BaseModel):
    start: datetime = Field(..., description="Unavailable start timestamp")
    end: datetime = Field(..., description="Unavailable end timestamp")
    reason: Optional[str] = Field(None, max_length=100)

    @model_validator(mode="after")
    def validate_period_times(self) -> "UnavailablePeriodSchema":
        if self.end <= self.start:
            raise ValueError("Unavailable period end must be strictly after start")
        return self


class OvertimeSchema(BaseModel):
    allowed: bool = Field(default=False, description="Whether overtime work is permitted")
    max_minutes_per_shift: int = Field(default=0, ge=0, description="Maximum permitted overtime minutes")


class TechnicianCreate(BaseModel):
    id: Optional[str] = Field(None, max_length=20, description="Optional unique technician ID (e.g. T21)")
    name: str = Field(..., min_length=1, max_length=100, description="Full name of technician")
    home_zone_id: Optional[str] = Field(None, max_length=20, description="Primary home zone ID (e.g. Z1)")
    home_location: Optional[LocationSchema] = Field(None, description="Home geographic coordinates")
    home_lat: Optional[float] = Field(None, ge=-90.0, le=90.0)
    home_lng: Optional[float] = Field(None, ge=-180.0, le=180.0)
    eligible_zones: List[str] = Field(default_factory=list, description="Zones technician is certified to operate in")
    skills: List[str] = Field(default_factory=list, description="List of certified skills")
    equipment: List[str] = Field(default_factory=list, description="List of onboard tools/equipment")
    shifts: List[ShiftSchema] = Field(default_factory=list, description="Scheduled working shifts")
    unavailable_periods: List[UnavailablePeriodSchema] = Field(default_factory=list, description="Pre-scheduled unavailability")
    overtime: Optional[OvertimeSchema] = Field(None, description="Overtime configuration object")
    overtime_allowed: Optional[bool] = Field(None, description="Flat overtime allowed flag")
    max_overtime_minutes: Optional[int] = Field(None, ge=0, description="Flat max overtime minutes")

    @model_validator(mode="after")
    def validate_technician_payload(self) -> "TechnicianCreate":
        # Validate name
        if not self.name or not self.name.strip():
            raise ValueError("Technician name cannot be blank or whitespace")

        # Resolve location coordinates
        if self.home_location is not None:
            self.home_lat = self.home_location.lat
            self.home_lng = self.home_location.lng
        elif self.home_lat is not None and self.home_lng is not None:
            self.home_location = LocationSchema(lat=self.home_lat, lng=self.home_lng)
        else:
            raise ValueError("Home location coordinates (home_location or home_lat/home_lng) are required")

        # Resolve overtime
        if self.overtime is not None:
            self.overtime_allowed = self.overtime.allowed
            self.max_overtime_minutes = self.overtime.max_minutes_per_shift
        else:
            is_allowed = bool(self.overtime_allowed)
            max_mins = int(self.max_overtime_minutes or 0)
            self.overtime = OvertimeSchema(allowed=is_allowed, max_minutes_per_shift=max_mins)
            self.overtime_allowed = is_allowed
            self.max_overtime_minutes = max_mins

        # Ensure home_zone_id is in eligible_zones
        if self.home_zone_id and self.home_zone_id not in self.eligible_zones:
            self.eligible_zones.append(self.home_zone_id)

        return self


class TechnicianUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    home_zone_id: Optional[str] = Field(None, max_length=20)
    home_location: Optional[LocationSchema] = None
    home_lat: Optional[float] = Field(None, ge=-90.0, le=90.0)
    home_lng: Optional[float] = Field(None, ge=-180.0, le=180.0)
    eligible_zones: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    equipment: Optional[List[str]] = None
    shifts: Optional[List[ShiftSchema]] = None
    unavailable_periods: Optional[List[UnavailablePeriodSchema]] = None
    overtime: Optional[OvertimeSchema] = None
    overtime_allowed: Optional[bool] = None
    max_overtime_minutes: Optional[int] = Field(None, ge=0)

    @model_validator(mode="after")
    def validate_update_payload(self) -> "TechnicianUpdate":
        if self.name is not None and not self.name.strip():
            raise ValueError("Technician name cannot be blank or whitespace")

        if self.home_location is not None:
            self.home_lat = self.home_location.lat
            self.home_lng = self.home_location.lng
        elif self.home_lat is not None and self.home_lng is not None:
            self.home_location = LocationSchema(lat=self.home_lat, lng=self.home_lng)

        if self.overtime is not None:
            self.overtime_allowed = self.overtime.allowed
            self.max_overtime_minutes = self.overtime.max_minutes_per_shift

        return self


class TechnicianResponse(BaseModel):
    id: str
    name: str
    home_zone_id: Optional[str] = None
    home_lat: float
    home_lng: float
    home_location: LocationSchema
    eligible_zones: List[str] = []
    skills: List[str] = []
    equipment: List[str] = []
    shifts: List[Dict[str, Any]] = []
    unavailable_periods: List[Dict[str, Any]] = []
    overtime_allowed: bool = False
    max_overtime_minutes: int = 0
    overtime: OvertimeSchema

    model_config = ConfigDict(from_attributes=True)
