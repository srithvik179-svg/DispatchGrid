from sqlalchemy import Column, String, Float, Integer, JSON, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(50), primary_key=True, index=True)
    idempotency_key = Column(String(100), unique=True, index=True, nullable=True)
    customer_name = Column(String(200), nullable=False)
    title = Column(String(200), nullable=False)
    zone_id = Column(String(20), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True, index=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    address = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False, index=True)
    priority_label = Column(String(50), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    required_skills = Column(JSON, default=list, nullable=False)
    required_equipment = Column(JSON, default=list, nullable=False)
    time_window_start = Column(DateTime(timezone=True), nullable=False, index=True)
    time_window_end = Column(DateTime(timezone=True), nullable=False, index=True)
    sla_deadline = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(50), default="pending", nullable=False, index=True)
    assigned_technician_id = Column(String(20), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True, index=True)
    scheduled_start = Column(DateTime(timezone=True), nullable=True)
    scheduled_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    tags = Column(JSON, default=list, nullable=False)

    zone = relationship("Zone")
    assigned_technician = relationship("Technician")

    def __repr__(self) -> str:
        return f"<Job {self.id}: {self.title} ({self.status})>"
