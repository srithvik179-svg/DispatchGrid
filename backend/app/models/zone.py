from sqlalchemy import Column, String, Float, JSON
from app.db.base_class import Base


class Zone(Base):
    __tablename__ = "zones"

    id = Column(String(20), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    adjacent_zones = Column(JSON, default=list, nullable=False)

    def __repr__(self) -> str:
        return f"<Zone {self.id} ({self.name})>"
