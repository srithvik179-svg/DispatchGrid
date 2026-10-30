from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


PRIORITY_MAP = {
    1: "urgent",
    2: "high",
    3: "medium",
    4: "low",
}


class LocationInput(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude between -90 and 90")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude between -180 and 180")
    address: Optional[str] = Field(None, max_length=500)


class JobCreate(BaseModel):
    id: Optional[str] = Field(None, max_length=50, description="Optional custom job ID. Auto-generated if omitted.")
    idempotency_key: Optional[str] = Field(None, max_length=100, description="Unique key for retry protection.")
    customer_name: str = Field(..., min_length=1, max_length=200, description="Customer or organization name.")
    title: str = Field(..., min_length=1, max_length=200, description="Summary title of the service request.")
    zone_id: Optional[str] = Field(None, max_length=20, description="Service zone (Z1-Z6).")
    location: Optional[LocationInput] = None
    lat: Optional[float] = Field(None, ge=-90.0, le=90.0)
    lng: Optional[float] = Field(None, ge=-180.0, le=180.0)
    address: Optional[str] = Field(None, max_length=500)
    priority: int = Field(..., ge=1, le=4, description="Priority: 1=urgent, 2=high, 3=medium, 4=low.")
    duration_minutes: int = Field(..., gt=0, description="Estimated work duration in minutes.")
    required_skills: List[str] = Field(..., min_length=1, description="Certified skills needed for this job.")
    required_equipment: List[str] = Field(default_factory=list, description="Specialized equipment items needed.")
    time_window_start: datetime = Field(..., description="Earliest permissible start time (hard constraint).")
    time_window_end: datetime = Field(..., description="Latest permissible completion time (hard constraint).")
    sla_deadline: Optional[datetime] = Field(None, description="Soft SLA deadline target (defaults to window end).")
    tags: List[str] = Field(default_factory=list, description="Diagnostic and testing tags.")

    @model_validator(mode="after")
    def validate_job_fields(self) -> "JobCreate":
        # 1. Clean strings
        self.customer_name = self.customer_name.strip()
        self.title = self.title.strip()
        if not self.customer_name:
            raise ValueError("customer_name cannot be empty or whitespace only")
        if not self.title:
            raise ValueError("title cannot be empty or whitespace only")

        # 2. Location consolidation
        if self.location:
            self.lat = self.location.lat
            self.lng = self.location.lng
            if self.location.address:
                self.address = self.location.address
        elif self.lat is None or self.lng is None:
            raise ValueError("Geographical location is required: provide either 'location' object or 'lat' and 'lng'")
        
        if not self.address:
            self.address = f"Coordinates ({self.lat:.4f}, {self.lng:.4f})"

        # 3. Time window validations
        if self.time_window_start >= self.time_window_end:
            raise ValueError("time_window_start must be strictly earlier than time_window_end")

        window_duration_minutes = (self.time_window_end - self.time_window_start).total_seconds() / 60.0
        if window_duration_minutes < self.duration_minutes:
            raise ValueError(
                f"Time window ({window_duration_minutes:.0f} mins) is shorter than job duration ({self.duration_minutes} mins)"
            )

        # 4. Default SLA deadline if not provided
        if not self.sla_deadline:
            self.sla_deadline = self.time_window_end
        elif self.sla_deadline < self.time_window_start:
            raise ValueError("sla_deadline cannot be earlier than time_window_start")

        # 5. Clean skill names
        self.required_skills = [s.strip().lower() for s in self.required_skills if s.strip()]
        if not self.required_skills:
            raise ValueError("At least one required skill must be specified")

        return self


class JobResponse(BaseModel):
    id: str
    idempotency_key: Optional[str] = None
    customer_name: str
    title: str
    zone_id: Optional[str] = None
    lat: float
    lng: float
    address: str
    priority: int
    priority_label: str
    duration_minutes: int
    required_skills: List[str]
    required_equipment: List[str]
    time_window_start: datetime
    time_window_end: datetime
    sla_deadline: datetime
    status: str
    assigned_technician_id: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    created_at: datetime
    tags: List[str] = []

    model_config = {"from_attributes": True}
