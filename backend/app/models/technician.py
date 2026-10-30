from sqlalchemy import Column, String, Float, Boolean, Integer, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Technician(Base):
    __tablename__ = "technicians"

    id = Column(String(20), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    home_zone_id = Column(String(20), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    home_lat = Column(Float, nullable=False)
    home_lng = Column(Float, nullable=False)
    eligible_zones = Column(JSON, default=list, nullable=False)
    skills = Column(JSON, default=list, nullable=False)
    equipment = Column(JSON, default=list, nullable=False)
    shifts = Column(JSON, default=list, nullable=False)
    unavailable_periods = Column(JSON, default=list, nullable=False)
    overtime_allowed = Column(Boolean, default=False, nullable=False)
    max_overtime_minutes = Column(Integer, default=0, nullable=False)

    home_zone = relationship("Zone")

    @property
    def home_location(self) -> dict:
        return {"lat": self.home_lat, "lng": self.home_lng}

    @property
    def overtime(self) -> dict:
        return {
            "allowed": bool(self.overtime_allowed),
            "max_minutes_per_shift": int(self.max_overtime_minutes or 0),
        }

    def __repr__(self) -> str:
        return f"<Technician {self.id} ({self.name})>"
