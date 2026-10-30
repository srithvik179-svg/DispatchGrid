from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AssignmentSummary(BaseModel):
    id: int
    job_id: str
    technician_id: str
    start_time: datetime
    end_time: datetime
    actual_start: Optional[datetime] = None
    status: str
    is_existing: bool = True
    job_title: Optional[str] = None
    technician_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AssignmentCreateRequest(BaseModel):
    job_id: str
    technician_id: str
    start_time: datetime
    end_time: Optional[datetime] = None

