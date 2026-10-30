from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(50), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    technician_id = Column(String(20), ForeignKey("technicians.id", ondelete="CASCADE"), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    actual_start = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="scheduled", nullable=False)
    is_existing = Column(Boolean, default=False, nullable=False)

    job = relationship("Job")
    technician = relationship("Technician")

    def __repr__(self) -> str:
        return f"<Assignment job={self.job_id} tech={self.technician_id} status={self.status}>"
